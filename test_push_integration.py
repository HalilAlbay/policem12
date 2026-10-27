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
            c.execute("INSERT INTO users(username,display_name,role,password_hash,branch_id) VALUES ('u1','User 1','staff','test',1)")
            c.execute("INSERT INTO users(username,display_name,role,password_hash,branch_id) VALUES ('u2','User 2','staff','test',1)")
            self.user1 = c.execute("SELECT id FROM users WHERE username='u1'").fetchone()[0]
            self.user2 = c.execute("SELECT id FROM users WHERE username='u2'").fetchone()[0]
            for uid, token in [(self.user1, 'token1'), (self.user2, 'token2')]:
                c.execute("INSERT INTO sessions(token_hash,user_id,expires) VALUES(?,?,?)",
                          (hashlib.sha256(token.encode()).hexdigest(), uid, 4102444800))
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
