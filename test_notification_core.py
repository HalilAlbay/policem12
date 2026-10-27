import unittest
from datetime import date
from notification_core import due_notifications

TODAY = date(2026, 10, 27)

def policy(**changes):
    p = dict(id=4, end_date="2026-11-11", owner_user_id=8,
             tracking=True, renewal_status="bekliyor")
    p.update(changes)
    return p

class NotificationTests(unittest.TestCase):
    def test_due_for_owner(self):
        x = due_notifications([policy()], TODAY)
        self.assertEqual(len(x), 1)
        self.assertEqual(x[0]["recipient_user_id"], 8)
        self.assertEqual(x[0]["days_before"], 15)
        self.assertNotIn("customer_name", str(x))

    def test_deduplication(self):
        self.assertEqual(due_notifications([policy()], TODAY, {(4, 15)}), [])

    def test_no_owner_never_broadcast(self):
        self.assertEqual(due_notifications([policy(owner_user_id=None)], TODAY), [])

    def test_closed_policy_not_notified(self):
        self.assertEqual(due_notifications([policy(renewal_status="policelestirildi")], TODAY), [])

    def test_not_due(self):
        self.assertEqual(due_notifications([policy(end_date="2026-12-01")], TODAY), [])

    def test_all_milestones(self):
        for n in (30, 15, 7, 1):
            from datetime import timedelta
            p = policy(end_date=(TODAY + timedelta(days=n)).isoformat())
            self.assertEqual(due_notifications([p], TODAY)[0]["days_before"], n)

if __name__ == "__main__":
    unittest.main()
