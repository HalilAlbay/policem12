"""Scheduled Web Push delivery; invoke from Windows Task Scheduler once daily.

Retries failed sends on subsequent runs; 404/410 endpoints are removed.
"""
from datetime import date
from app import init, tx
from notification_core import due_notifications
from push_service import ensure_schema, send_push
import os

def ensure_delivery_schema(c):
    ensure_schema(c)
    c.execute("""CREATE TABLE IF NOT EXISTS push_deliveries(
      policy_id INTEGER NOT NULL,
      days_before INTEGER NOT NULL,
      subscription_id INTEGER NOT NULL,
      delivered_at TEXT,
      attempts INTEGER NOT NULL DEFAULT 0,
      last_error TEXT,
      PRIMARY KEY(policy_id,days_before,subscription_id)
    )""")

def tick(today=None):
    today = today or date.today()
    if not all(os.getenv(k) for k in ('POLICEM_VAPID_PUBLIC_KEY',
                                      'POLICEM_VAPID_PRIVATE_KEY',
                                      'POLICEM_VAPID_SUBJECT')):
        return {'status':'not_configured', 'sent':0}
    init()
    with tx() as c:
        ensure_delivery_schema(c)
        rows=c.execute("""SELECT p.id,p.end_date,p.owner_user_id,p.tracking,
                  COALESCE(r.status,'bekliyor') renewal_status
                  FROM policies p LEFT JOIN renewals r ON r.policy_id=p.id
                  WHERE p.tracking=1""").fetchall()
        due=due_notifications([dict(r) for r in rows],today)
        for notice in due:
            subscriptions=c.execute("SELECT id FROM push_subscriptions WHERE user_id=?",
                                    (notice['recipient_user_id'],)).fetchall()
            for sub in subscriptions:
                c.execute("""INSERT OR IGNORE INTO push_deliveries
                    (policy_id,days_before,subscription_id) VALUES(?,?,?)""",
                    (notice['policy_id'],notice['days_before'],sub['id']))
        pending=c.execute("""SELECT d.policy_id,d.days_before,d.subscription_id,
                   s.endpoint,s.p256dh,s.auth
                   FROM push_deliveries d
                   JOIN push_subscriptions s ON s.id=d.subscription_id
                   JOIN policies p ON p.id=d.policy_id
                   LEFT JOIN renewals r ON r.policy_id=p.id
                   WHERE d.delivered_at IS NULL AND d.attempts<5
                   AND p.tracking=1 AND COALESCE(r.status,'bekliyor') NOT IN ('policelestirildi','kaybedildi')
                   ORDER BY d.attempts,d.policy_id LIMIT 100""").fetchall()
    sent=0; failed=0
    for item in pending:
        d=dict(item)
        try:
            send_push(d, {'notification_id':f"{d['policy_id']}-{d['days_before']}",
                          'days_before':d['days_before']})
            with tx() as c:
                c.execute("""UPDATE push_deliveries SET delivered_at=CURRENT_TIMESTAMP,
                    attempts=attempts+1,last_error=NULL
                    WHERE policy_id=? AND days_before=? AND subscription_id=?""",
                    (d['policy_id'],d['days_before'],d['subscription_id']))
            sent+=1
        except Exception as exc:
            status=getattr(getattr(exc,'response',None),'status_code',None)
            with tx() as c:
                if status in (404,410):
                    c.execute("DELETE FROM push_subscriptions WHERE id=?",
                              (d['subscription_id'],))
                else:
                    c.execute("""UPDATE push_deliveries SET attempts=attempts+1,
                      last_error=? WHERE policy_id=? AND days_before=? AND subscription_id=?""",
                      (type(exc).__name__,d['policy_id'],d['days_before'],d['subscription_id']))
            failed+=1
    return {'status':'ok','sent':sent,'failed':failed}

if __name__=='__main__':
    print(tick())
