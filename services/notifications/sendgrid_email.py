"""
SendGrid email channel for emergency alerts.

send_guardian_email(alert_id)
    Contract: returns None on success/skip, raises RetriableError or NonRetriableError.
    Called by _channel_with_retry() in emergency_alerts.py.

handle_sendgrid_webhook(request)
    Verifies SendGrid ECDSA signature and updates EmergencyAlert email_status idempotently.
    Called from routes/webhooks.py.
"""

import logging
import os

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from sendgrid.helpers.eventwebhook import EventWebhook

from models import db, EmergencyAlert, ProviderWebhookEvent
from services.emergency_alerts import RetriableError, NonRetriableError, reconcile_alert_status

log = logging.getLogger(__name__)

# SendGrid event type → our internal email_status
_STATUS_MAP = {
    "processed": "IN_FLIGHT",
    "deferred":  "IN_FLIGHT",
    "delivered": "DELIVERED",
    "bounce":    "FAILED",
    "dropped":   "FAILED",
    "blocked":   "FAILED",
}

_SUBJECT = "URGENT: Safety concern flagged for {user_name}"

_BODY_TEXT = """\
URGENT SAFETY ALERT

{user_name} is using a mental health support app and a safety concern has been flagged.

Please check in with them immediately or contact emergency services if needed.

This message was sent automatically by ZenShell.
"""

_BODY_HTML = """\
<div style="font-family:sans-serif;max-width:600px;margin:auto;padding:24px;
            border:2px solid #d9534f;border-radius:8px;">
  <h2 style="color:#d9534f;margin-top:0;">&#9888;&#65039; Urgent Safety Alert</h2>
  <p><strong>{user_name}</strong> is using a mental health support app and a
  safety concern has been flagged.</p>
  <p>Please <strong>check in with them immediately</strong> or contact emergency
  services if needed.</p>
  <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
  <p style="font-size:12px;color:#888;">
    This message was sent automatically by ZenShell. Do not reply to this email.
  </p>
</div>
"""


def send_guardian_email(alert_id: int) -> None:
    """
    Send an emergency email to the guardian.
    Returns None on success or skip; raises RetriableError / NonRetriableError on failure.
    """
    alert = db.session.get(EmergencyAlert, alert_id)
    if alert is None:
        return

    snapshot   = alert.payload_snapshot or {}
    to_email   = snapshot.get("guardian_email")
    user_name  = snapshot.get("user_name", "A user")
    from_email = os.environ.get("SENDGRID_FROM_EMAIL")

    if not to_email:
        log.info("send_guardian_email SKIPPED alert=%d — no guardian email", alert_id)
        alert.email_status = "SKIPPED"
        db.session.commit()
        reconcile_alert_status(alert)
        return

    message = Mail(
        from_email          = from_email,
        to_emails           = to_email,
        subject             = _SUBJECT.format(user_name=user_name),
        plain_text_content  = _BODY_TEXT.format(user_name=user_name),
        html_content        = _BODY_HTML.format(user_name=user_name),
    )

    try:
        sg       = SendGridAPIClient(os.environ["SENDGRID_API_KEY"])
        response = sg.send(message)
        provider_id = response.headers.get("X-Message-Id", "")
        log.info("send_guardian_email queued alert=%d http=%d msg_id=%s",
                 alert_id, response.status_code, provider_id)
        alert.email_status      = "IN_FLIGHT"
        alert.email_provider_id = provider_id
        db.session.commit()

    except Exception as exc:
        status_code = getattr(exc, "status_code", None)
        # 4xx errors (except 429 rate-limit) are permanent
        if isinstance(status_code, int) and 400 <= status_code < 500 and status_code != 429:
            log.error("send_guardian_email non_retriable alert=%d status=%d: %s",
                      alert_id, status_code, exc)
            raise NonRetriableError(str(exc)) from exc
        log.warning("send_guardian_email retriable alert=%d status=%s: %s",
                    alert_id, status_code, exc)
        raise RetriableError(str(exc)) from exc


def handle_sendgrid_webhook(req) -> tuple:
    """
    Process a SendGrid Event Webhook POST (batched events).
    Verifies the ECDSA signature, records each event, and updates email_status.
    Returns (response_body, http_status_code).
    """
    # ── ECDSA signature verification ─────────────────────────────────────────
    ec_key    = os.environ.get("SENDGRID_WEBHOOK_VERIFICATION_KEY", "")
    signature = req.headers.get("X-Twilio-Email-Event-Webhook-Signature", "")
    timestamp = req.headers.get("X-Twilio-Email-Event-Webhook-Timestamp", "")
    payload   = req.get_data(as_text=True)

    if not ec_key:
        log.error("sendgrid_webhook SENDGRID_WEBHOOK_VERIFICATION_KEY not set — rejecting")
        return "Forbidden", 403

    try:
        ev = EventWebhook(ec_key)
        if not ev.verify_signature(payload, signature, timestamp):
            log.warning("sendgrid_webhook invalid_signature")
            return "Forbidden", 403
    except Exception as exc:
        log.warning("sendgrid_webhook signature_error: %s", exc)
        return "Forbidden", 403

    # ── Parse batched events ──────────────────────────────────────────────────
    try:
        import json
        events = json.loads(payload)
        if not isinstance(events, list):
            events = [events]
    except Exception:
        log.warning("sendgrid_webhook invalid JSON body")
        return "Bad Request", 400

    for event in events:
        _process_event(event)

    return "", 204


def _process_event(event: dict) -> None:
    sg_event_id   = event.get("sg_event_id", "")
    sg_message_id = event.get("sg_message_id", "")
    event_type    = event.get("event", "").lower()

    if not sg_event_id:
        return

    # ── Idempotency — one row per sg_event_id ─────────────────────────────────
    if ProviderWebhookEvent.query.filter_by(
        provider="sendgrid", provider_event_id=sg_event_id
    ).first():
        log.info("sendgrid_webhook duplicate sg_event_id=%s", sg_event_id)
        return

    # sg_message_id in events has format "{X-Message-Id}.{filter_id}"
    base_id = sg_message_id.split(".")[0] if sg_message_id else ""
    alert   = EmergencyAlert.query.filter_by(email_provider_id=base_id).first() if base_id else None

    db.session.add(ProviderWebhookEvent(
        provider          = "sendgrid",
        provider_event_id = sg_event_id,
        alert_id          = alert.id if alert else None,
        raw_payload       = event,
    ))

    if alert is None:
        log.warning("sendgrid_webhook unknown_msg_id=%s event=%s", base_id, event_type)
        db.session.commit()
        return

    new_status = _STATUS_MAP.get(event_type)
    if new_status and alert.email_status not in ("DELIVERED", "FAILED"):
        log.info("sendgrid_webhook alert=%d %s→%s event=%s",
                 alert.id, alert.email_status, new_status, event_type)
        alert.email_status = new_status
        if event_type in ("bounce", "dropped", "blocked"):
            alert.email_last_error = f"SendGrid event: {event_type}"
        db.session.commit()
        if new_status in ("DELIVERED", "FAILED"):
            reconcile_alert_status(alert)
    else:
        db.session.commit()
