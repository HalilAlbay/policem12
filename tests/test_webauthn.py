"""Fail-closed and server-issued WebAuthn ceremony tests."""
import base64
import hashlib
import json
import os
import tempfile
from pathlib import Path

import pytest
import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature


@pytest.fixture
def webauthn_client(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("POLICEM_DATA", tmp)
        monkeypatch.setenv("POLICEM_PUBLIC_ORIGIN", "https://login.example.test")
        monkeypatch.setenv("WEBAUTHN_RP_ID", "example.test")
        monkeypatch.delenv("POLICEM_DEV_MODE", raising=False)
        import app
        from fastapi.testclient import TestClient
        app.DATA = Path(tmp)
        app.DB = Path(tmp) / "webauthn.sqlite3"
        app.init()
        with app.tx() as c:
            c.execute("INSERT INTO users(username,display_name,role,password_hash,branch_id,job_title) VALUES (?,?,?,?,1,?)",
                      ("owner", "Owner", "partner", app.password_hash("Password12345"), "agency_authority"))
        with TestClient(app.app) as http:
            yield http


def login(http):
    result = http.post("/api/login", json={"username": "owner", "password": "Password12345"})
    assert result.status_code == 200
    return {"Authorization": "Bearer " + result.json()["token"]}


INSTALLATION_ID = "test-installation-identifier-001"


def test_options_issue_server_challenge_and_enforce_platform_uv(webauthn_client):
    headers = login(webauthn_client)
    result = webauthn_client.post("/api/security/webauthn/register/options", headers=headers,
                                  json={"label": "iPhone", "password": "Password12345", "installation_id": INSTALLATION_ID})
    assert result.status_code == 200, result.text
    public_key = result.json()["publicKey"]
    assert public_key["authenticatorSelection"]["authenticatorAttachment"] == "platform"
    assert public_key["authenticatorSelection"]["residentKey"] == "required"
    assert public_key["authenticatorSelection"]["userVerification"] == "required"
    assert public_key["attestation"] == "none"
    assert len(public_key["challenge"]) >= 40


def test_registration_options_require_password_step_up(webauthn_client):
    result = webauthn_client.post("/api/security/webauthn/register/options", headers=login(webauthn_client),
                                  json={"label": "iPhone", "password": "wrong", "installation_id": INSTALLATION_ID})
    assert result.status_code == 403
    assert result.json()["detail"]["code"] == "STEP_UP_REQUIRED"


def test_discoverable_login_options_do_not_name_accounts(webauthn_client):
    result = webauthn_client.post("/api/security/webauthn/login/options", json={"installation_id": INSTALLATION_ID})
    assert result.status_code == 401, result.text
    assert result.json()["detail"]["code"] == "AUTH_FAILED"
    assert "owner" not in result.text


def test_missing_or_mismatched_rp_configuration_fails_closed(webauthn_client, monkeypatch):
    monkeypatch.setenv("WEBAUTHN_RP_ID", "other.test")
    result = webauthn_client.post("/api/security/webauthn/login/options", json={"installation_id": INSTALLATION_ID})
    assert result.status_code == 503
    assert result.json()["detail"]["code"] == "METHOD_UNAVAILABLE"


def test_invalid_and_replayed_challenges_cannot_be_consumed(webauthn_client):
    import app
    with app.tx() as c:
        c.execute("INSERT INTO webauthn_challenges(id,purpose,challenge,created_at,expires_at,installation_id) VALUES ('ceremony-example-123456','login',?,?,?,?)",
                  (b"challenge-bytes", 100, 9999999999, INSTALLATION_ID))
    invalid = webauthn_client.post("/api/security/webauthn/login/verify", json={
        "ceremony_id": "ceremony-example-123456", "installation_id": INSTALLATION_ID,
        "credential": {"id": "eA", "rawId": "eA", "type": "public-key", "response": {}},
    })
    assert invalid.status_code == 401
    with app.tx() as c:
        assert c.execute("SELECT consumed_at FROM webauthn_challenges WHERE id='ceremony-example-123456'").fetchone()[0] is not None


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def client_data(kind, challenge):
    return json.dumps({"type": kind, "challenge": challenge,
                       "origin": "https://login.example.test", "crossOrigin": False},
                      separators=(",", ":")).encode()


def test_generated_platform_credential_registers_and_authenticates(webauthn_client):
    """Exercises the real verifier with an EC2/ES256 authenticator vector."""
    import app
    headers = login(webauthn_client)
    options_response = webauthn_client.post("/api/security/webauthn/register/options", headers=headers,
                                            json={"label": "Test iPhone", "password": "Password12345", "installation_id": INSTALLATION_ID})
    assert options_response.status_code == 200, options_response.text
    options = options_response.json()
    challenge = options["publicKey"]["challenge"]
    user_id = app.base64url_to_bytes(options["publicKey"]["user"]["id"])
    credential_id = os.urandom(32)
    private_key = ec.generate_private_key(ec.SECP256R1())
    numbers = private_key.public_key().public_numbers()
    cose_key = {1: 2, 3: -7, -1: 1,
                -2: numbers.x.to_bytes(32, "big"), -3: numbers.y.to_bytes(32, "big")}
    rp_hash = hashlib.sha256(b"example.test").digest()
    registration_data = (rp_hash + bytes([0x45]) + (0).to_bytes(4, "big") + bytes(16)
                         + len(credential_id).to_bytes(2, "big") + credential_id + cbor2.dumps(cose_key))
    attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": registration_data})
    credential = {"id": b64url(credential_id), "rawId": b64url(credential_id), "type": "public-key",
                   "response": {"attestationObject": b64url(attestation),
                                "clientDataJSON": b64url(client_data("webauthn.create", challenge))}}
    try:
        from webauthn import verify_registration_response
        verify_registration_response(credential=credential, expected_challenge=app.base64url_to_bytes(challenge),
                                    expected_rp_id="example.test", expected_origin="https://login.example.test",
                                    require_user_verification=True)
    except Exception as exc:
        pytest.fail(f"Generated registration vector is invalid: {type(exc).__name__}: {exc}")
    registered = webauthn_client.post("/api/security/webauthn/register/verify", headers=headers,
                                      json={"ceremony_id": options["ceremony_id"], "installation_id": INSTALLATION_ID, "credential": credential})
    assert registered.status_code == 200, registered.text
    assert registered.json()["device"]["method"] == "webauthn"
    assert webauthn_client.get('/api/security/login-method', params={'installation_id': INSTALLATION_ID}).json()['method'] == 'webauthn'
    inventory = webauthn_client.get('/api/security/devices', headers=headers).json()['devices']
    assert sum(bool(x['selected']) for x in inventory) == 1

    login_options = webauthn_client.post("/api/security/webauthn/login/options", json={"installation_id": INSTALLATION_ID})
    assert login_options.status_code == 200, login_options.text
    assert len(login_options.json()["publicKey"]["allowCredentials"]) == 1
    auth_challenge = login_options.json()["publicKey"]["challenge"]
    authenticator_data = rp_hash + bytes([0x05]) + (1).to_bytes(4, "big")
    auth_client_data = client_data("webauthn.get", auth_challenge)
    signature = private_key.sign(authenticator_data + hashlib.sha256(auth_client_data).digest(),
                                 ec.ECDSA(hashes.SHA256()))
    assertion = {"id": b64url(credential_id), "rawId": b64url(credential_id), "type": "public-key",
                 "response": {"authenticatorData": b64url(authenticator_data),
                              "clientDataJSON": b64url(auth_client_data), "signature": b64url(signature),
                              "userHandle": b64url(user_id)}}
    authenticated = webauthn_client.post("/api/security/webauthn/login/verify", json={
        "ceremony_id": login_options.json()["ceremony_id"], "installation_id": INSTALLATION_ID, "credential": assertion})
    assert authenticated.status_code == 200, authenticated.text
    assert authenticated.json()["user"]["username"] == "owner"
    assert webauthn_client.get("/api/me", headers={"Authorization": "Bearer " + authenticated.json()["token"]}).status_code == 200


def test_successful_method_change_replaces_the_previous_device_grant(webauthn_client):
    import app
    headers = login(webauthn_client)
    pin_private, pin_public = pin_key_material()
    old_device = enroll_pin(webauthn_client, headers, pin_private, pin_public)
    begin_response = webauthn_client.post('/api/security/webauthn/register/options', headers=headers, json={
        'label': 'Face ID device', 'password': 'Password12345', 'installation_id': INSTALLATION_ID})
    assert begin_response.status_code == 200, begin_response.text
    begin = begin_response.json(); public = begin['publicKey']
    credential_id = os.urandom(32); private = ec.generate_private_key(ec.SECP256R1())
    n = private.public_key().public_numbers()
    cose = {1:2,3:-7,-1:1,-2:n.x.to_bytes(32,'big'),-3:n.y.to_bytes(32,'big')}
    auth_data = hashlib.sha256(b'example.test').digest()+bytes([0x45])+(0).to_bytes(4,'big')+bytes(16)+len(credential_id).to_bytes(2,'big')+credential_id+cbor2.dumps(cose)
    attestation = cbor2.dumps({'fmt':'none','attStmt':{},'authData':auth_data})
    credential = {'id':b64url(credential_id),'rawId':b64url(credential_id),'type':'public-key','response':{
        'attestationObject':b64url(attestation),'clientDataJSON':b64url(client_data('webauthn.create',public['challenge']))}}
    finished = webauthn_client.post('/api/security/webauthn/register/verify',headers=headers,json={
        'ceremony_id':begin['ceremony_id'],'installation_id':INSTALLATION_ID,'credential':credential})
    assert finished.status_code == 200, finished.text
    assert webauthn_client.get('/api/security/login-method',params={'installation_id':INSTALLATION_ID}).json()['method']=='webauthn'
    with app.tx() as c:
        old=c.execute('SELECT revoked_at FROM trusted_devices WHERE id=?',(old_device,)).fetchone()
        assert old['revoked_at'] is not None
        assert c.execute('SELECT 1 FROM pin_device_keys WHERE device_id=? AND revoked_at IS NULL',(old_device,)).fetchone() is None
        active=c.execute('SELECT device_id FROM device_login_settings WHERE installation_id=?',(INSTALLATION_ID,)).fetchone()
        assert active['device_id'] != old_device
    assert webauthn_client.post('/api/security/pin/login/options',json={'installation_id':INSTALLATION_ID}).status_code==401


def pin_key_material():
    private = ec.generate_private_key(ec.SECP256R1())
    n = private.public_key().public_numbers()
    public = {"kty": "EC", "crv": "P-256", "x": b64url(n.x.to_bytes(32, "big")),
              "y": b64url(n.y.to_bytes(32, "big")), "ext": True, "key_ops": ["verify"]}
    return private, public


def pin_signature(private, purpose, ceremony_id, device_id, challenge):
    message = (b"policem-pin-v1\0" + purpose.encode() + b"\0" + ceremony_id.encode() + b"\0"
               + device_id.encode() + b"\0" + app_base64url_decode(challenge))
    der = private.sign(message, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    return b64url(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


def app_base64url_decode(value):
    return base64.urlsafe_b64decode(value + "=" * ((4 - len(value) % 4) % 4))


def enroll_pin(http, headers, private, public, pin="2468"):
    options = http.post("/api/security/pin/enroll/options", headers=headers,
                        json={"label": "PIN test device", "password": "Password12345", "installation_id": INSTALLATION_ID})
    assert options.status_code == 200, options.text
    begin = options.json()
    signature = pin_signature(private, "enroll", begin["ceremony_id"], begin["device_id"], begin["challenge"])
    result = http.post("/api/security/pin/enroll/verify", headers=headers, json={
        "ceremony_id": begin["ceremony_id"], "device_id": begin["device_id"],
        "installation_id": INSTALLATION_ID,
        "public_key": public, "pin": pin, "pin_confirm": pin, "signature": signature})
    assert result.status_code == 200, result.text
    return begin["device_id"]


def test_pin_requires_device_signature_and_locks_after_five_wrong_pins(webauthn_client):
    import app
    private, public = pin_key_material()
    owner_headers = login(webauthn_client)
    device_id = enroll_pin(webauthn_client, owner_headers, private, public)
    assert webauthn_client.get('/api/security/login-method', params={'installation_id': INSTALLATION_ID}).json()['method'] == 'pin'
    assert webauthn_client.post('/api/security/webauthn/login/options', json={'installation_id': INSTALLATION_ID}).status_code == 401
    pending = webauthn_client.post('/api/security/webauthn/register/options', headers=owner_headers,
                                   json={'label': 'replacement', 'password': 'Password12345', 'installation_id': INSTALLATION_ID})
    assert pending.status_code == 200
    failed = webauthn_client.post('/api/security/webauthn/register/verify', headers=owner_headers, json={
        'ceremony_id': pending.json()['ceremony_id'], 'installation_id': INSTALLATION_ID,
        'credential': {'id': 'eA', 'rawId': 'eA', 'type': 'public-key', 'response': {}}})
    assert failed.status_code == 400
    assert webauthn_client.get('/api/security/login-method', params={'installation_id': INSTALLATION_ID}).json()['method'] == 'pin'
    wrong_key, _ = pin_key_material()
    first = webauthn_client.post("/api/security/pin/login/options", json={"installation_id": INSTALLATION_ID}).json()
    bad_proof = pin_signature(wrong_key, "login", first["ceremony_id"], device_id, first["challenge"])
    denied = webauthn_client.post("/api/security/pin/login/verify", json={
        "device_id": device_id, "installation_id": INSTALLATION_ID, "ceremony_id": first["ceremony_id"], "pin": "2468", "signature": bad_proof})
    assert denied.status_code == 401
    with app.tx() as c:
        assert c.execute("SELECT failures FROM device_pin WHERE device_id=?", (device_id,)).fetchone()[0] == 0

    for _ in range(5):
        challenge = webauthn_client.post("/api/security/pin/login/options", json={"installation_id": INSTALLATION_ID}).json()
        signature = pin_signature(private, "login", challenge["ceremony_id"], device_id, challenge["challenge"])
        denied = webauthn_client.post("/api/security/pin/login/verify", json={
            "device_id": device_id, "installation_id": INSTALLATION_ID, "ceremony_id": challenge["ceremony_id"], "pin": "1111", "signature": signature})
        assert denied.status_code == 401
    with app.tx() as c:
        pin_row = c.execute("SELECT failures,locked_at FROM device_pin WHERE device_id=?", (device_id,)).fetchone()
        assert pin_row["failures"] == 5 and pin_row["locked_at"] is not None
    locked = webauthn_client.post("/api/security/pin/login/options", json={"installation_id": INSTALLATION_ID})
    assert locked.status_code == 401


def test_pin_success_creates_device_bound_session(webauthn_client):
    private, public = pin_key_material()
    device_id = enroll_pin(webauthn_client, login(webauthn_client), private, public)
    challenge = webauthn_client.post("/api/security/pin/login/options", json={"installation_id": INSTALLATION_ID}).json()
    signature = pin_signature(private, "login", challenge["ceremony_id"], device_id, challenge["challenge"])
    response = webauthn_client.post("/api/security/pin/login/verify", json={
        "device_id": device_id, "installation_id": INSTALLATION_ID, "ceremony_id": challenge["ceremony_id"], "pin": "2468", "signature": signature})
    assert response.status_code == 200, response.text
    bearer = {"Authorization": "Bearer " + response.json()["token"]}
    assert webauthn_client.get("/api/me", headers=bearer).status_code == 200
    owner_headers = login(webauthn_client)
    assert webauthn_client.post(f"/api/security/devices/{device_id}/revoke", headers=owner_headers,
                                json={"password": "Password12345"}).status_code == 200
    assert webauthn_client.get("/api/me", headers=bearer).status_code == 401

