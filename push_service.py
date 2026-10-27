"""Opt-in Web Push endpoints. Not mounted in production until security review.

Requires pywebpush and VAPID env configuration. Subscription endpoints are bound
to the authenticated user ID supplied by the existing app's current() dependency.
"""
import json
import os
import sqlite3
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, HTTPException
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
        endpoint TEXT NOT NULL UNIQUE,
        p256dh TEXT NOT NULL,
        auth TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

def build_router(tx, current):
    router = APIRouter(prefix="/api/push", tags=["notifications"])

    @router.get("/config")
    def config(user=Depends(current)):
        public_key = os.getenv("POLICEM_VAPID_PUBLIC_KEY", "")
        return {"enabled": bool(public_key), "public_key": public_key}

    @router.post("/subscribe")
    def subscribe(subscription: Subscription, user=Depends(current)):
        if not valid_endpoint(subscription.endpoint):
            raise HTTPException(400, "Geçersiz push adresi")
        if not os.getenv("POLICEM_VAPID_PUBLIC_KEY"):
            raise HTTPException(503, "Bildirim sistemi yapılandırılmadı")
        with tx() as c:
            ensure_schema(c)
            existing = c.execute('SELECT user_id FROM push_subscriptions WHERE endpoint=?',
                                 (subscription.endpoint,)).fetchone()
            if existing and existing['user_id'] != user['id']:
                raise HTTPException(409, 'Bu cihaz başka kullanıcıya kayıtlı; önce çıkış yapın')
            c.execute("""INSERT INTO push_subscriptions(user_id,endpoint,p256dh,auth)
                VALUES (?,?,?,?)
                ON CONFLICT(endpoint) DO UPDATE SET
                p256dh=excluded.p256dh,auth=excluded.auth""",
                (user["id"], subscription.endpoint,
                 subscription.keys.p256dh, subscription.keys.auth))
        return {"ok": True}

    @router.post("/unsubscribe")
    def unsubscribe(subscription: Subscription, user=Depends(current)):
        with tx() as c:
            ensure_schema(c)
            c.execute("DELETE FROM push_subscriptions WHERE endpoint=? AND user_id=?",
                      (subscription.endpoint, user["id"]))
        return {"ok": True}

    return router

def send_push(subscription: dict, payload: dict):
    """Transport; caller must handle retries and 404/410 stale endpoints."""
    from pywebpush import webpush
    key = os.environ["POLICEM_VAPID_PRIVATE_KEY"]
    subject = os.environ["POLICEM_VAPID_SUBJECT"]
    if not subject.startswith(("mailto:", "https:")):
        raise ValueError("VAPID subject must be mailto: or https:")
    return webpush(
        subscription_info={"endpoint": subscription["endpoint"],
                           "keys": {"p256dh": subscription["p256dh"],
                                    "auth": subscription["auth"]}},
        data=json.dumps(payload, ensure_ascii=False),
        vapid_private_key=key,
        vapid_claims={"sub": subject},
        ttl=3600,
    )
