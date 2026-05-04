"""
Emergency alert orchestration.

Flow:
  trigger_emergency_alert()  ←── called by risk_engine on CLEAR_IMMEDIATE_RISK
      ↓  (idempotency check)
  EmergencyAlert created
      ↓  (background threads)
  _send_sms_with_retry()    _send_email_with_retry()
      ↓                             ↓
  send_guardian_sms()       send_guardian_email()
      ↓  (webhook)                  ↓  (webhook)
  handle_twilio_webhook()   handle_sendgrid_webhook()
      ↓                             ↓
               reconcile_alert_status()

TODO: Replace _run_in_background() with Celery tasks for production-grade
      reliability (threads do not survive process restarts).
"""

import logging
import threading
import time
from datetime import datetime, timezone

from models import db, EmergencyAlert

log = logging.getLogger(__name__)

MAX_ATTEMPTS  = 5
RETRY_DELAYS  = [0, 15, 60, 300, 900]   # seconds: immediate, 15s, 1m, 5m, 15m

# ── Custom exceptions ──────────────────────────────────────────────────────────

class RetriableError(Exception):
    """Transient failure — safe to retry (timeout, 5xx, rate-limit)."""

class NonRetriableError(Exception):
    """Permanent failure — do not retry (bad phone, auth error, 4xx)."""


# ── Public entry point ─────────────────────────────────────────────────────────

def trigger_emergency_alert(user, safety_alert, session_id) -> EmergencyAlert:
    """
    Create (or return existing) EmergencyAlert and dispatch background jobs.

    Idempotent: calling twice for the same (user, session, safety_alert) is safe.
    Returns immediately — sending happens off the request thread.
    """
    from flask import current_app
    ikey = _build_idempotency_key(user.id, session_id, safety_alert.id)

    existing = EmergencyAlert.query.filter_by(idempotency_key=ikey).first()
    if existing:
        log.info("emergency_alert already_exists id=%d key=%s status=%s",
                 existing.id, ikey, existing.status)
        return existing

    guardian     = getattr(user, "guardian", None)
    triggered_at = datetime.now(timezone.utc)

    payload = {
        "user_id":         user.id,
        "user_name":       getattr(user, "username", str(user.id)),
        "guardian_name":   guardian.name  if guardian else None,
        "guardian_email":  guardian.email if guardian else None,
        "guardian_phone":  guardian.phone if guardian else None,
        "safety_alert_id": safety_alert.id,
        "triggered_at":    triggered_at.isoformat(),
    }

    alert = EmergencyAlert(
        user_id            = user.id,
        session_id         = session_id,
        message_id         = str(safety_alert.id),
        idempotency_key    = ikey,
        status             = "DISPATCHING",
        sms_status         = "PENDING",
        email_status       = "PENDING",
        payload_snapshot   = payload,
        first_triggered_at = triggered_at,
    )
    db.session.add(alert)
    db.session.commit()

    log.info("emergency_alert created id=%d key=%s user=%d", alert.id, ikey, user.id)

    app = current_app._get_current_object()
    _run_in_background(app, _send_sms_with_retry,   alert.id)
    _run_in_background(app, _send_email_with_retry, alert.id)

    return alert


# ── Reconciliation ─────────────────────────────────────────────────────────────

def reconcile_alert_status(alert: EmergencyAlert) -> None:
    """
    Recompute alert.status from both channel statuses and persist.
    Called after every terminal channel event (DELIVERED / FAILED / SKIPPED).
    """
    sms   = alert.sms_status
    email = alert.email_status

    # Both channels had no contact info — treat as configuration failure
    if sms == "SKIPPED" and email == "SKIPPED":
        alert.status = "FAILED"
        alert.completed_at = alert.completed_at or datetime.now(timezone.utc)
        db.session.commit()
        log.warning("reconcile alert=%d FAILED (both channels skipped — no contact info)", alert.id)
        return

    # Active = channels where delivery was attempted or completed
    active = [s for s in (sms, email) if s not in ("PENDING", "SKIPPED")]

    if not active:
        alert.status = "DISPATCHING"
    elif any(s == "DELIVERED" for s in active) and any(s == "FAILED" for s in active):
        alert.status = "PARTIALLY_SENT"
    elif all(s == "DELIVERED" for s in active):
        alert.status = "SENT"
    elif all(s == "FAILED" for s in active):
        alert.status = "FAILED"
    else:
        alert.status = "DISPATCHING"   # at least one IN_FLIGHT

    if alert.status in ("SENT", "PARTIALLY_SENT", "FAILED"):
        alert.completed_at = alert.completed_at or datetime.now(timezone.utc)

    db.session.commit()
    log.info("reconcile alert=%d status=%s sms=%s email=%s",
             alert.id, alert.status, sms, email)


# ── Background execution ───────────────────────────────────────────────────────

def _run_in_background(app, fn, alert_id: int) -> None:
    """
    Run fn(alert_id) in a daemon thread with a pushed Flask app context.
    TODO: swap for `celery_app.send_task(fn.__name__, args=[alert_id])` in production.
    """
    def _wrapper():
        with app.app_context():
            fn(alert_id)

    t = threading.Thread(
        target=_wrapper,
        daemon=True,
        name=f"alert-{alert_id}-{fn.__name__}",
    )
    t.start()


def _send_sms_with_retry(alert_id: int) -> None:
    from services.notifications.twilio_sms import send_guardian_sms
    _channel_with_retry(alert_id, "sms", send_guardian_sms)


def _send_email_with_retry(alert_id: int) -> None:
    from services.notifications.sendgrid_email import send_guardian_email
    _channel_with_retry(alert_id, "email", send_guardian_email)


# ── Generic retry loop ─────────────────────────────────────────────────────────

def _channel_with_retry(alert_id: int, channel: str, send_fn) -> None:
    """
    Retry loop for one delivery channel.

    send_fn contract:
      - Returns None on success or skip (model already updated).
      - Raises RetriableError on transient failure.
      - Raises NonRetriableError on permanent failure.
    """
    status_field  = f"{channel}_status"
    attempt_field = f"{channel}_attempt_count"
    error_field   = f"{channel}_last_error"

    for attempt_idx in range(MAX_ATTEMPTS):
        alert = db.session.get(EmergencyAlert, alert_id)
        if alert is None:
            log.error("channel_retry alert_id=%d not found channel=%s", alert_id, channel)
            return

        current = getattr(alert, status_field)
        if current in ("DELIVERED", "FAILED", "SKIPPED", "IN_FLIGHT"):
            # IN_FLIGHT: message is queued with provider — do not resend
            log.info("channel_retry bail alert=%d channel=%s status=%s", alert_id, channel, current)
            return

        delay = RETRY_DELAYS[attempt_idx] if attempt_idx < len(RETRY_DELAYS) else RETRY_DELAYS[-1]
        if delay > 0:
            log.info("channel_retry wait=%ds alert=%d channel=%s attempt=%d",
                     delay, alert_id, channel, attempt_idx + 1)
            time.sleep(delay)

        # Record the attempt before sending (survives crashes)
        alert = db.session.get(EmergencyAlert, alert_id)
        if alert is None:
            return
        setattr(alert, attempt_field, getattr(alert, attempt_field) + 1)
        alert.last_attempt_at = datetime.now(timezone.utc)
        db.session.commit()

        try:
            send_fn(alert_id)
            return   # success or terminal skip handled inside send_fn

        except RetriableError as exc:
            log.warning("channel_retry retriable alert=%d channel=%s attempt=%d: %s",
                        alert_id, channel, attempt_idx + 1, exc)
            alert = db.session.get(EmergencyAlert, alert_id)
            if alert:
                setattr(alert, error_field, str(exc)[:500])
                db.session.commit()
            continue

        except NonRetriableError as exc:
            log.error("channel_retry non_retriable alert=%d channel=%s: %s",
                      alert_id, channel, exc)
            alert = db.session.get(EmergencyAlert, alert_id)
            if alert:
                setattr(alert, status_field, "FAILED")
                setattr(alert, error_field, str(exc)[:500])
                db.session.commit()
                reconcile_alert_status(alert)
            return

        except Exception as exc:
            log.exception("channel_retry unexpected alert=%d channel=%s attempt=%d",
                          alert_id, channel, attempt_idx + 1)
            alert = db.session.get(EmergencyAlert, alert_id)
            if alert:
                setattr(alert, error_field, str(exc)[:500])
                db.session.commit()
            continue

    # Exhausted all retries
    alert = db.session.get(EmergencyAlert, alert_id)
    if alert and getattr(alert, status_field) not in ("DELIVERED", "SKIPPED", "IN_FLIGHT"):
        setattr(alert, status_field, "FAILED")
        db.session.commit()
        reconcile_alert_status(alert)
    log.error("channel_retry exhausted alert=%d channel=%s", alert_id, channel)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _build_idempotency_key(user_id: int, session_id, safety_alert_id: int) -> str:
    return f"emergency:{user_id}:{session_id}:{safety_alert_id}"
