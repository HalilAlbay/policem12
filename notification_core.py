"""Poliçem notification planning core (isolated; no production side effects).

Delivery to iOS/Android requires a separate Web Push transport, subscriptions,
permission UI and a durable retryable outbox. This module does not send pushes.
"""
from datetime import date
from typing import Iterable

DEFAULT_DAYS = (30, 15, 7, 1)
CLOSED_STATUSES = frozenset(("policelestirildi", "kaybedildi"))

def due_notifications(policies: Iterable[dict], today: date,
                      already_queued: set[tuple[int, int]] | None = None,
                      days: tuple[int, ...] = DEFAULT_DAYS) -> list[dict]:
    """Plan idempotent, recipient-scoped reminders without exposing policy PII.

    Each policy needs id, end_date, owner_user_id, tracking and renewal_status.
    Caller must persist/deduplicate atomically; already_queued is only a hint.
    """
    queued = already_queued or set()
    result = []
    for policy in policies:
        if not policy.get("tracking") or policy.get("renewal_status") in CLOSED_STATUSES:
            continue
        owner = policy.get("owner_user_id")
        if not isinstance(owner, int) or owner <= 0:
            continue  # never broadcast unassigned customer records
        try:
            end = date.fromisoformat(str(policy["end_date"]))
            pid = int(policy["id"])
        except (ValueError, TypeError, KeyError):
            continue
        remaining = (end - today).days
        if remaining not in days or (pid, remaining) in queued:
            continue
        result.append({
            "policy_id": pid,
            "recipient_user_id": owner,
            "days_before": remaining,
            "title": "Poliçem • Yenileme hatırlatması",
            "body": f"Takibinizdeki bir poliçenin bitişine {remaining} gün kaldı.",
        })
    return result
