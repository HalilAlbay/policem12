"""End-to-end API + SQLite + mocked push transport tests; no real push sent."""
import hashlib
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import app
import push_job

ENDPOINT = "https://fcm.googleapis.com/fcm/send/test-device"
KEYS = {"p256dh": "A" * 64, "auth": "B" * 24}
TODAY = date(2026, 10, 27)

class PushIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = app.DB
        app.DB = Path(self.temp.name) / "test.sqlite3"
        app.init()
        with app.tx() as c:
            c.execute("INSERT INTO users(username,display_name,role,password_hash,branch_id) VALUES ('u1','User 1','staff',?,1)",(app.password_hash('Password12345'),))
            c.execute("INSERT INTO users(username,display_name,role,password_hash,branch_id) VALUES ('u2','User 2','staff',?,1)",(app.password_hash('Password12345'),))
            self.user1 = c.execute("SELECT id FROM users WHERE username='u1'").fetchone()[0]
            self.user2 = c.execute("SELECT id FROM users WHERE username='u2'").fetchone()[0]
            for uid, token in [(self.user1, 'token1'), (self.user2, 'token2')]:
                c.execute("INSERT INTO sessions(token_hash,user_id,expires) VALUES(?,?,?)",
                          (hashlib.sha256(token.encode()).hexdigest(), uid, 4102444800))
                device_id = 'device-' + str(uid)
                c.execute("INSERT INTO trusted_devices(id,user_id,label,created_at,last_seen,installation_id) VALUES (?,?,?,?,?,?)",
                          (device_id, uid, 'Test device', 1, 1, 'install-' + str(uid)))
                c.execute("INSERT INTO device_sessions(token_hash,device_id) VALUES (?,?)",
                          (hashlib.sha256(token.encode()).hexdigest(), device_id))
                c.execute("INSERT INTO device_login_settings(installation_id,user_id,device_id,method,updated_at) VALUES (?,?,?,?,?)",
                          ('install-' + str(uid), uid, device_id, 'pin', 1))
            c.execute("""INSERT INTO policies(agency_id,branch_id,owner_user_id,uploader_user_id,
                customer_name,policy_type,policy_number,insurer,premium,start_date,end_date,
                issued_date,tracking) VALUES (1,1,?,?, 'Test customer','Kasko','TEST-001',
                'Test insurer',100,'2026-01-01','2026-11-11','2026-01-01',1)""",
                (self.user1,self.user1))
            self.pid = c.execute("SELECT id FROM policies WHERE policy_number='TEST-001'").fetchone()[0]
        self.env = patch.dict(os.environ, {
            "POLICEM_VAPID_PUBLIC_KEY": "test-public-key",
            "POLICEM_VAPID_PRIVATE_KEY": "test-private-key",
            "POLICEM_VAPID_SUBJECT": "mailto:test@example.org"
        })
        self.env.start()
        self.client = TestClient(app.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None,None,None)
        self.env.stop()
        app.DB = self.old_db
        self.temp.cleanup()

    def request(self, method, path, user=1, **kwargs):
        return self.client.request(method, path, headers={
            "Authorization": "Bearer token" + str(user)}, **kwargs)

    def subscribe(self, user=1):
        return self.request("POST", "/api/push/subscribe", user,
                            json={"endpoint": ENDPOINT, "keys": KEYS})

    def test_requires_login(self):
        self.assertEqual(self.client.get("/api/push/config").status_code, 401)
        self.assertEqual(self.client.post("/api/push/subscribe",
                         json={"endpoint":ENDPOINT,"keys":KEYS}).status_code, 401)

    def test_subscription_is_stored_for_owner(self):
        self.assertEqual(self.subscribe().status_code, 200)
        with app.tx() as c:
            row=c.execute("SELECT user_id FROM push_subscriptions").fetchone()
        self.assertEqual(row[0],self.user1)

    def test_password_only_session_cannot_activate_push(self):
        token='password-only-session'
        with app.tx() as c:
            c.execute('INSERT INTO sessions(token_hash,user_id,expires) VALUES(?,?,?)',
                      (hashlib.sha256(token.encode()).hexdigest(),self.user1,4102444800))
        response=self.client.post('/api/push/subscribe',headers={'Authorization':'Bearer '+token},
                                  json={'endpoint':ENDPOINT,'keys':KEYS})
        self.assertEqual(response.status_code,403,response.text)
        with app.tx() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM push_subscriptions').fetchone()[0],0)

    def test_legacy_subscription_is_inactive_until_device_reactivation(self):
        with app.tx() as c:
            c.execute('''CREATE TABLE push_subscriptions (
                id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),
                endpoint TEXT NOT NULL UNIQUE,p256dh TEXT NOT NULL,auth TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
            c.execute('INSERT INTO push_subscriptions(user_id,endpoint,p256dh,auth) VALUES(?,?,?,?)',
                      (self.user1,ENDPOINT,KEYS['p256dh'],KEYS['auth']))
        with app.tx() as c:
            from push_service import ensure_schema
            ensure_schema(c)
            row=c.execute('SELECT device_id,active FROM push_subscriptions').fetchone()
        self.assertIsNone(row['device_id'])
        self.assertEqual(row['active'],0)

    def test_other_user_cannot_claim_existing_device(self):
        self.assertEqual(self.subscribe().status_code,200)
        self.assertEqual(self.subscribe(user=2).status_code,409)
        with app.tx() as c:
            self.assertEqual(c.execute('SELECT user_id FROM push_subscriptions').fetchone()[0],self.user1)

    def test_unsubscribe_other_user_does_not_delete(self):
        self.subscribe()
        self.assertEqual(self.request("POST","/api/push/unsubscribe",2,
            json={"endpoint":ENDPOINT,"keys":KEYS}).status_code,200)
        with app.tx() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM push_subscriptions").fetchone()[0],1)

    def test_mocked_delivery_idempotent(self):
        self.subscribe()
        with patch.object(push_job,"send_push") as send:
            self.assertEqual(push_job.tick(TODAY)["sent"],1)
            self.assertEqual(push_job.tick(TODAY)["sent"],0)
            self.assertEqual(send.call_count,1)
            self.assertNotIn("Test customer",str(send.call_args))

    def test_logout_suppresses_the_device_subscription(self):
        self.subscribe()
        response=self.request('POST','/api/logout')
        self.assertEqual(response.status_code,200,response.text)
        with patch.object(push_job,"send_push") as send:
            self.assertEqual(push_job.tick(TODAY)["sent"],0)
            send.assert_not_called()

    def test_revoked_device_subscription_is_not_delivered(self):
        self.subscribe()
        did='device-' + str(self.user1)
        response=self.request('POST',f'/api/security/devices/{did}/revoke',json={'password':'Password12345'})
        self.assertEqual(response.status_code,200,response.text)
        with patch.object(push_job,"send_push") as send:
            self.assertEqual(push_job.tick(TODAY)["sent"],0)
            send.assert_not_called()

    def test_one_logged_out_device_does_not_suppress_another_active_device(self):
        self.subscribe()
        token='second-device-session'
        token_hash=hashlib.sha256(token.encode()).hexdigest()
        with app.tx() as c:
            c.execute('INSERT INTO sessions(token_hash,user_id,expires) VALUES(?,?,?)',(token_hash,self.user1,4102444800))
            c.execute("INSERT INTO trusted_devices(id,user_id,label,created_at,last_seen,installation_id) VALUES ('device-u1-second',?,'Second',1,1,'install-u1-second')",(self.user1,))
            c.execute("INSERT INTO device_sessions(token_hash,device_id) VALUES (?,'device-u1-second')",(token_hash,))
            c.execute("INSERT INTO device_login_settings(installation_id,user_id,device_id,method,updated_at) VALUES ('install-u1-second',?,'device-u1-second','pin',1)",(self.user1,))
        second={'Authorization':'Bearer '+token}
        response=self.client.post('/api/push/subscribe',headers=second,json={'endpoint':ENDPOINT+'-second','keys':KEYS})
        self.assertEqual(response.status_code,200,response.text)
        self.request('POST','/api/logout')
        with patch.object(push_job,"send_push") as send:
            self.assertEqual(push_job.tick(TODAY)["sent"],1)
            self.assertEqual(send.call_count,1)

    def test_closed_renewal_not_sent(self):
        self.subscribe()
        with app.tx() as c:
            c.execute("INSERT INTO renewals(policy_id,status) VALUES(?,'policelestirildi')",(self.pid,))
        with patch.object(push_job,"send_push") as send:
            self.assertEqual(push_job.tick(TODAY)["sent"],0)
            send.assert_not_called()

    def test_owner_transfer_cancels_pending(self):
        self.subscribe()
        with patch.object(push_job,"send_push",side_effect=RuntimeError("offline")):
            self.assertEqual(push_job.tick(TODAY)["failed"],1)
        with app.tx() as c:
            c.execute("UPDATE policies SET owner_user_id=? WHERE id=?",(self.user2,self.pid))
        with patch.object(push_job,"send_push") as send:
            self.assertEqual(push_job.tick(TODAY)["sent"],0)
            send.assert_not_called()

    def test_failed_delivery_retries(self):
        self.subscribe()
        with patch.object(push_job,"send_push",side_effect=RuntimeError("offline")):
            self.assertEqual(push_job.tick(TODAY)["failed"],1)
        with patch.object(push_job,"send_push") as send:
            self.assertEqual(push_job.tick(TODAY)["sent"],1)
            self.assertEqual(send.call_count,1)

if __name__ == "__main__":
    unittest.main()
