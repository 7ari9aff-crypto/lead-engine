"""Event backbone: transactional outbox + dispatch to idempotent consumers.

Flow: domain code calls emit() right after a state change (at-least-once);
the event-worker dispatches pending events to consumers — outbound webhooks
(signed HMAC, retried, dead-lettered), in-app notifications, audit trail.
Every consumer deduplicates through engine.event_consumptions keyed by
(event_id, consumer), so retries never double-apply side effects.

Event types (versioned, tenant-scoped, immutable payloads):
  job.started | job.completed | job.failed | job.paused
  lead.verified | usage.threshold | platform.org_provisioned
"""
import json
import os
import time
import uuid
import hashlib
import hmac as _hmac

import requests

from .db import utcnow
from .secrets import decrypt_secret

MAX_ATTEMPTS = 5


def _t(db, name: str) -> str:
    """SQLite tests use bare names; Postgres resolves public.* explicitly
    (the engine connection pins search_path=engine)."""
    return name if getattr(db, "dialect", "sqlite") == "sqlite" else f"public.{name}"
BACKOFF_BASE_SECONDS = 30


def emit(db, org_id: str | None, event_type: str, aggregate_type: str,
         aggregate_id: str | None, payload: dict | None = None,
         event_id: str | None = None) -> str:
    """Append an event to the outbox. Safe to call twice with the same
    event_id — the second emit is a no-op (idempotent producers)."""
    event_id = event_id or f"evt_{uuid.uuid4().hex}"
    db.execute(
        "INSERT INTO outbox (event_id, organization_id, aggregate_type,"
        " aggregate_id, event_type, payload, created_at)"
        " VALUES (?,?,?,?,?,?,?)"
        " ON CONFLICT (event_id) DO NOTHING",
        (event_id, org_id, aggregate_type, aggregate_id, event_type,
         json.dumps(payload or {}, ensure_ascii=False, default=str), utcnow()))
    return event_id


def _mark(db, event_id: str, status: str, error: str | None = None) -> None:
    if status == "dispatched":
        db.execute(
            "UPDATE outbox SET status='dispatched', published_at=?, last_error=NULL"
            " WHERE event_id=?", (utcnow(), event_id))
    else:
        db.execute(
            "UPDATE outbox SET attempts = attempts + 1, last_error=? WHERE event_id=?",
            (error, event_id))
        row = db.one("SELECT attempts FROM outbox WHERE event_id=?", (event_id,))
        if row and (row["attempts"] or 0) >= MAX_ATTEMPTS:
            db.execute("UPDATE outbox SET status='dead' WHERE event_id=?", (event_id,))


def _consumed(db, event_id: str, consumer: str) -> bool:
    """Read-only check. The consumption row is recorded AFTER the side
    effect succeeds — a failed delivery must never consume its event."""
    return bool(db.one(
        "SELECT 1 AS ok FROM event_consumptions WHERE event_id=? AND consumer=?",
        (event_id, consumer)))


def _record_consumption(db, event_id: str, consumer: str) -> None:
    db.execute(
        "INSERT INTO event_consumptions (event_id, consumer) VALUES (?,?)"
        " ON CONFLICT (event_id, consumer) DO NOTHING", (event_id, consumer))


def dispatch_pending(db, limit: int = 50) -> dict:
    """Dispatch up to `limit` pending events to all consumers. Returns counts."""
    events = db.query(
        "SELECT * FROM outbox WHERE status='pending' ORDER BY created_at LIMIT ?",
        (limit,))
    counts = {"dispatched": 0, "retried": 0, "dead": 0}
    for event in events:
        org_id = event.get("organization_id")
        try:
            _consume_webhooks(db, event, org_id)
            _consume_notifications(db, event, org_id)
            _mark(db, event["event_id"], "dispatched")
            counts["dispatched"] += 1
        except Exception as exc:
            _mark(db, event["event_id"], "retry", f"{type(exc).__name__}: {exc}")
            counts["retried"] += 1
            if (event.get("attempts") or 0) + 1 >= MAX_ATTEMPTS:
                counts["dead"] += 1
    return counts


# ---------------------------------------------------------------- consumers
def _consume_webhooks(db, event: dict, org_id: str | None) -> None:
    """Signed delivery to every org webhook subscribed to this event type."""
    if not org_id:
        return
    event_type = event["event_type"]
    hooks = db.query(
        "SELECT id, url, secret_enc, events FROM " + _t(db, "webhooks") +
        " WHERE organization_id = ? AND status = 'active'", (org_id,))
    for hook in hooks:
        subscribed = hook.get("events") or ["*"]
        if "*" not in subscribed and event_type not in subscribed:
            continue
        try:
            secret = decrypt_secret(hook["secret_enc"])
        except Exception:
            continue  # undecryptable secret: skip, never crash dispatch
        _deliver_signed(db, hook, event, secret)


def _deliver_signed(db, hook: dict, event: dict, secret: str) -> None:
    """HMAC-signed webhook POST with retries + delivery log."""
    event_id = event["event_id"]
    consumer = f"webhook:{hook['id']}"
    if _consumed(db, event_id, consumer):
        return
    timestamp = str(int(time.time()))
    body = json.dumps({
        "event_id": event_id,
        "type": event["event_type"],
        "version": event.get("event_version", 1),
        "organization_id": str(event.get("organization_id") or ""),
        "payload": event.get("payload") or {},
        "timestamp": timestamp,
    }, ensure_ascii=False, default=str)
    signature = _hmac.new(secret.encode(), f"{timestamp}.{body}".encode(),
                          hashlib.sha256).hexdigest()
    last_error = None
    status_code = None
    for attempt in range(1, 4):  # 3 attempts per dispatch round
        try:
            resp = requests.post(
                hook["url"], data=body.encode(), timeout=10,
                headers={"Content-Type": "application/json",
                         "X-LeadEngine-Signature": f"v1={signature}",
                         "X-LeadEngine-Timestamp": timestamp,
                         "X-LeadEngine-Event": event["event_type"]})
            status_code = resp.status_code
            if resp.status_code < 300:
                success = True
                error = None
            else:
                success = False
                error = f"HTTP {resp.status_code}"
        except Exception as exc:
            success = False
            error = f"{type(exc).__name__}: {exc}"
        db.execute(
            "INSERT INTO webhook_deliveries (webhook_id, event_id, url, attempt,"
            " status_code, success, error) VALUES (?,?,?,?,?,?,?)",
            (hook["id"], event_id, hook["url"], attempt, status_code,
             success, error))
        if success:
            _record_consumption(db, event_id, consumer)
            return
        last_error = error
        time.sleep(min(5, attempt))  # polite backoff inside the round
    raise RuntimeError(f"webhook delivery failed: {hook['url']}: {last_error}")


def _consume_notifications(db, event: dict, org_id: str | None) -> None:
    """In-app notification for user-visible events; email when SMTP configured."""
    notable = {
        "job.completed": "اكتملت مهمة توليد الـleads",
        "job.failed": "فشلت مهمة توليد الـleads",
        "job.paused": "توقفت مهمة مؤقتًا — انتهت الحصص",
        "usage.threshold": "اقتربت من حد الاستهلاك",
    }
    title = notable.get(event["event_type"])
    if not title or not org_id:
        return
    if _consumed(db, event["event_id"], "notifications"):
        return
    db.execute(
        "INSERT INTO notifications (organization_id, kind, title, body, created_at)"
        " VALUES (?,?,?,?,?)",
        (org_id, event["event_type"], title, event.get("payload") or {}, utcnow()))
    _record_consumption(db, event["event_id"], "notifications")
    _maybe_email(db, org_id, title, event)


def _maybe_email(db, org_id: str, title: str, event: dict) -> None:
    """Email channel: only when SMTP is fully configured. Never raises."""
    host = os.environ.get("SMTP_HOST")
    to = os.environ.get("SMTP_NOTIFY_TO")
    if not host or not to:
        return
    try:
        import smtplib
        from email.mime.text import MIMEText

        msg = MIMEText(json.dumps(event.get("payload") or {}, ensure_ascii=False,
                                  default=str), "plain", "utf-8")
        msg["Subject"] = f"[Lead Engine] {title}"
        msg["From"] = os.environ.get("SMTP_FROM", "lead-engine@localhost")
        msg["To"] = to
        with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "25")),
                          timeout=10) as smtp:
            smtp.send_message(msg)
    except Exception:
        pass


def verify_webhook_signature(secret: str, timestamp: str, body: str,
                             signature_header: str) -> bool:
    """Receiver-side helper (documented for customers): v1=<hex> over
    '{timestamp}.{body}' — constant-time compare, 5-minute freshness."""
    expected = _hmac.new(secret.encode(), f"{timestamp}.{body}".encode(),
                         hashlib.sha256).hexdigest()
    provided = (signature_header or "").removeprefix("v1=").strip()
    if not _hmac.compare_digest(expected, provided):
        return False
    try:
        return abs(time.time() - int(timestamp)) <= 300
    except ValueError:
        return False
