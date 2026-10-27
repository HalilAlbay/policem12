"""Device session regression tests. Run: python -m pytest -q tests/test_device_sessions.py"""
import tempfile
from pathlib import Path
import pytest

@pytest.fixture
def client(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("POLICEM_DATA",tmp)
        import app
        from fastapi.testclient import TestClient
        app.DATA=Path(tmp)
        app.DB=Path(tmp)/"devices.sqlite3"
        app.init()
        with app.tx() as c:
            c.execute("INSERT INTO users(username,display_name,role,password_hash,branch_id,job_title) VALUES (?,?,?,?,1,?)",
                      ("owner","Owner","partner",app.password_hash("Password12345"),"agency_authority"))
        with TestClient(app.app) as http:
            yield http

def auth(http):
    r=http.post("/api/login",json={"username":"owner","password":"Password12345"})
    assert r.status_code==200,r.text
    return {"Authorization":"Bearer "+r.json()["token"]}

def test_device_revoke_invalidates_bound_session_only(client):
    first=auth(client)
    second=auth(client)
    device=client.post("/api/security/devices",headers=first,json={"label":"iPhone","password":"Password12345"})
    assert device.status_code==200,device.text
    did=device.json()["id"]
    bound=client.post(f"/api/security/devices/{did}/bind",headers=first,json={"password":"Password12345"})
    assert bound.status_code==200,bound.text
    assert client.get("/api/me",headers=first).status_code==200
    revoked=client.post(f"/api/security/devices/{did}/revoke",headers=second,json={"password":"Password12345"})
    assert revoked.status_code==200,revoked.text
    assert client.get("/api/me",headers=first).status_code==401
    assert client.get("/api/me",headers=second).status_code==200

def test_cross_user_cannot_bind_other_device(client):
    owner=auth(client)
    device=client.post("/api/security/devices",headers=owner,json={"label":"iPhone","password":"Password12345"}).json()["id"]
    import app
    with app.tx() as c:
        c.execute("INSERT INTO users(username,display_name,role,password_hash,branch_id,job_title) VALUES (?,?,?,?,1,?)",
                  ("other","Other","staff",app.password_hash("AnotherPassword123"),"technical"))
    other=client.post("/api/login",json={"username":"other","password":"AnotherPassword123"}).json()["token"]
    resp=client.post(f"/api/security/devices/{device}/bind",headers={"Authorization":"Bearer "+other},json={"password":"AnotherPassword123"})
    assert resp.status_code==404

def test_wrong_password_cannot_register_device(client):
    owner=auth(client)
    r=client.post("/api/security/devices",headers=owner,json={"label":"Phone","password":"wrong"})
    assert r.status_code==403
