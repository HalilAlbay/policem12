"""Opt-in Web Push endpoints. Not mounted in production until security review.

Requires pywebpush and VAPID env configuration. Subscription endpoints are bound
to the authenticated user ID supplied by the existing app's current() dependency.
"""
import json
import logging
import traceback
import base64
import binascii
import os
import sqlite3
import hashlib
import time
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

class SubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=20, max_length=256)
    auth: str = Field(min_length=8, max_length=128)

class Subscription(BaseModel):
    endpoint: str = Field(min_length=20, max_length=2048)
    keys: SubscriptionKeys

PUSH_HOSTS = frozenset(('fcm.googleapis.com', 'updates.push.services.mozilla.com', 'web.push.apple.com', 'push.services.mozilla.com'))

def _trusted_push_host(hostname: str) -> bool:
    host = hostname.lower().rstrip('.')
    return host in PUSH_HOSTS or host.endswith('.push.apple.com')

def valid_endpoint(endpoint: str) -> bool:
    try:
        parsed = urlsplit(endpoint)
        return (parsed.scheme == "https" and bool(parsed.hostname)
                and _trusted_push_host(parsed.hostname)
                and not parsed.username and not parsed.password
                and parsed.port in (None, 443)
                and not parsed.fragment)
    except ValueError:
        return False

def ensure_schema(c: sqlite3.Connection):
    c.execute("""CREATE TABLE IF NOT EXISTS push_subscriptions (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        device_id TEXT REFERENCES trusted_devices(id),
        endpoint TEXT NOT NULL UNIQUE,
        p256dh TEXT NOT NULL,
        auth TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    columns = {row['name'] for row in c.execute('PRAGMA table_info(push_subscriptions)')}
    if 'device_id' not in columns:
        c.execute('ALTER TABLE push_subscriptions ADD COLUMN device_id TEXT REFERENCES trusted_devices(id)')
    if 'active' not in columns:
        # Legacy subscriptions have no trustworthy device/session binding.
        c.execute('ALTER TABLE push_subscriptions ADD COLUMN active INTEGER NOT NULL DEFAULT 0')
    c.execute('CREATE INDEX IF NOT EXISTS idx_push_user_device_active ON push_subscriptions(user_id,device_id,active)')

def vapid_diagnostic():
    """Safe, non-secret diagnostics of VAPID configuration."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    pub = os.getenv("POLICEM_VAPID_PUBLIC_KEY", "").strip()
    key = os.getenv("POLICEM_VAPID_PRIVATE_KEY", "").strip().replace("\\n", "\n")
    subject = os.getenv("POLICEM_VAPID_SUBJECT", "").strip()
    result = {"subject_valid": subject.startswith(("mailto:", "https://")),
              "public_valid": False, "private_valid": False, "keys_match": False,
              "key_format": "pem" if "BEGIN" in key else "base64url"}
    try:
        b = base64.urlsafe_b64decode(pub + "=" * (-len(pub) % 4))
        public_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), b)
        result["public_valid"] = True
    except Exception:
        public_key = None
    try:
        if "BEGIN" in key:
            private_key = serialization.load_pem_private_key(key.encode(), password=None)
        else:
            raw = base64.urlsafe_b64decode("".join(key.split()) + "=" * (-len("".join(key.split())) % 4))
            if len(raw) != 32:
                result["private_error"] = "length"
                return result
            private_key = ec.derive_private_key(int.from_bytes(raw, "big"), ec.SECP256R1())
        result["private_valid"] = True
        if public_key is not None:
            result["keys_match"] = (
                private_key.public_key().public_numbers() == public_key.public_numbers())
    except Exception:
        result["private_error"] = "decode"
    return result

def build_router(tx, current):
    router = APIRouter(prefix="/api/push", tags=["notifications"])

    @router.get("/config")
    def config(user=Depends(current)):
        public_key = os.getenv("POLICEM_VAPID_PUBLIC_KEY", "")
        test = os.getenv("RENDER_SERVICE_NAME") == "policem12-push-test"
        if test:
            logging.getLogger("uvicorn.error").warning("VAPID diagnostic: %s", vapid_diagnostic())
        return {"enabled": bool(public_key), "public_key": public_key, "test_enabled": test}

    @router.post("/test")
    def test_notification(user=Depends(current)):
        # Never expose this endpoint on the production service.
        if os.getenv("RENDER_SERVICE_NAME") != "policem12-push-test":
            raise HTTPException(404, "Bulunamadı")
        with tx() as c:
            ensure_schema(c)
            rows = [dict(row) for row in c.execute(
                """SELECT s.endpoint,s.p256dh,s.auth FROM push_subscriptions s
                JOIN trusted_devices d ON d.id=s.device_id AND d.user_id=s.user_id
                JOIN device_login_settings l ON l.device_id=d.id AND l.user_id=d.user_id
                WHERE s.user_id=? AND s.active=1 AND d.revoked_at IS NULL""",
                (user["id"],)).fetchall()]
        if not rows:
            raise HTTPException(409, "Önce bu cihazda bildirimleri açın")
        sent = 0
        failure_types = []
        for sub in rows:
            try:
                send_push(sub, {"notification_id": "test-" + str(user["id"]),
                                "message": "Poliçem TEST bildirimi"})
                sent += 1
            except Exception as exc:
                # Log only the exception type, never VAPID secrets or subscription endpoints.
                failure_types.append(type(exc).__name__)
                frames = traceback.extract_tb(exc.__traceback__)
                origin = [(os.path.basename(frame.filename), frame.name, frame.lineno)
                          for frame in frames[-4:]]
                logging.getLogger("uvicorn.error").error(
                    "Push test failed: type=%s origin=%s", type(exc).__name__, origin)
        if not sent:
            raise HTTPException(502, "Test bildirimi gönderilemedi (" +
                                ", ".join(sorted(set(failure_types))) + ")")
        return {"ok": True, "sent": sent}

    @router.post("/subscribe")
    def subscribe(subscription: Subscription, request: Request, user=Depends(current)):
        if not valid_endpoint(subscription.endpoint):
            raise HTTPException(400, "Geçersiz push adresi")
        if not os.getenv("POLICEM_VAPID_PUBLIC_KEY"):
            raise HTTPException(503, "Bildirim sistemi yapılandırılmadı")
        with tx() as c:
            ensure_schema(c)
            token = request.headers.get('Authorization', '')[7:]
            session_hash = hashlib.sha256(token.encode()).hexdigest()
            binding = c.execute('''SELECT d.id FROM device_sessions ds
                JOIN trusted_devices d ON d.id=ds.device_id
                JOIN device_login_settings l ON l.device_id=d.id AND l.user_id=d.user_id
                JOIN sessions s ON s.token_hash=ds.token_hash AND s.user_id=d.user_id
                WHERE ds.token_hash=? AND d.user_id=? AND d.revoked_at IS NULL
                AND s.expires>?''', (session_hash, user['id'], int(time.time()))).fetchone()
            if not binding:
                raise HTTPException(403, 'Bildirim için bu cihazda güvenli cihaz girişini etkinleştirin')
            existing = c.execute('SELECT user_id FROM push_subscriptions WHERE endpoint=?',
                                 (subscription.endpoint,)).fetchone()
            if existing and existing['user_id'] != user['id']:
                raise HTTPException(409, 'Bu cihaz başka kullanıcıya kayıtlı; önce çıkış yapın')
            c.execute("""INSERT INTO push_subscriptions(user_id,device_id,endpoint,p256dh,auth,active)
                VALUES (?,?,?,?,?,1)
                ON CONFLICT(endpoint) DO UPDATE SET
                device_id=excluded.device_id,p256dh=excluded.p256dh,auth=excluded.auth,active=1""",
                (user["id"], binding['id'], subscription.endpoint,
                 subscription.keys.p256dh, subscription.keys.auth))
        return {"ok": True}

    @router.post("/unsubscribe")
    def unsubscribe(subscription: Subscription, user=Depends(current)):
        with tx() as c:
            ensure_schema(c)
            c.execute("UPDATE push_subscriptions SET active=0 WHERE endpoint=? AND user_id=?",
                      (subscription.endpoint, user["id"]))
        return {"ok": True}

    return router

def send_push(subscription: dict, payload: dict):
    """Transport; caller must handle retries and 404/410 stale endpoints."""
    from pywebpush import webpush
    key = os.environ["POLICEM_VAPID_PRIVATE_KEY"].strip().replace("\\n", "\n")
    subject = os.environ.get("POLICEM_VAPID_SUBJECT", "").strip()
    if not subject.startswith(("mailto:", "https://")):
        subject = "https://policem12-push-test.onrender.com"
    if "BEGIN" not in key:
        key = "".join(key.split())
        try:
            raw = base64.urlsafe_b64decode(key + "=" * (-len(key) % 4))
        except (ValueError, binascii.Error) as exc:
            raise ValueError("VAPID_PRIVATE_KEY_ENCODING") from exc
        if len(raw) != 32:
            raise ValueError("VAPID_PRIVATE_KEY_LENGTH")
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
        private_key = ec.derive_private_key(int.from_bytes(raw, "big"), ec.SECP256R1())
        key = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode("ascii")
    if "BEGIN" in key:
        from cryptography.hazmat.primitives import serialization
        private_key = serialization.load_pem_private_key(key.encode(), password=None)
        key = base64.urlsafe_b64encode(private_key.private_bytes(
            serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption())).decode("ascii").rstrip("=")
    return webpush(
        subscription_info={"endpoint": subscription["endpoint"],
                           "keys": {"p256dh": subscription["p256dh"],
                                    "auth": subscription["auth"]}},
        data=json.dumps(payload, ensure_ascii=False),
        vapid_private_key=key,
        vapid_claims={"sub": subject},
        ttl=3600,
    )
