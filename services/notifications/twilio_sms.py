"""
Twilio SMS channel for emergency alerts.

send_guardian_sms(alert_id)
    Contract: returns None on success/skip, raises RetriableError or NonRetriableError.
    Called by _channel_with_retry() in emergency_alerts.py.

handle_twilio_webhook(request)
    Verifies Twilio signature and updates EmergencyAlert sms_status idempotently.
    Called from routes/webhooks.py.
"""

import logging
import os

from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from twilio.request_validator import RequestValidator

from models import db, EmergencyAlert, ProviderWebhookEvent
from services.emergency_alerts import RetriableError, NonRetriableError, reconcile_alert_status

log = logging.getLogger(__name__)

# Permanent Twilio error codes — retrying won't help
_NON_RETRIABLE_CODES = {
    21211,  # Invalid 'To' phone number
    21214,  # 'To' number cannot be reached
    21606,  # 'From' number not SMS-capable
    21610,  # Recipient unsubscribed
    20003,  # Authentication failure
    20404,  # Resource not found
}

# Twilio MessageStatus → our internal sms_status
_STATUS_MAP = {
    "queued":      "IN_FLIGHT",
    "accepted":    "IN_FLIGHT",
    "sent":        "IN_FLIGHT",
    "delivered":   "DELIVERED",
    "failed":      "FAILED",
    "undelivered": "FAILED",
}

_SMS_BODY = (
    "URGENT: {user_name} is using a mental health support app and a safety concern "
    "has been flagged. Please check in with them immediately or contact emergency "
    "services if needed. This message was sent automatically."
)


def _get_client() -> Client:
    return Client(
        os.environ["TWILIO_ACCOUNT_SID"],
        os.environ["TWILIO_AUTH_TOKEN"],
    )


def send_guardian_sms(alert_id: int) -> None:
    """
    Send an emergency SMS to the guardian.
    Returns None on success or skip; raises RetriableError / NonRetriableError on failure.
    """
    alert = db.session.get(EmergencyAlert, alert_id)
    if alert is None:
        return

    snapshot  = alert.payload_snapshot or {}
    to_number = snapshot.get("guardian_phone")
    user_name = snapshot.get("user_name", "A user")

    if not to_number:
        log.info("send_guardian_sms SKIPPED alert=%d — no guardian phone", alert_id)
        alert.sms_status = "SKIPPED"
        db.session.commit()
        reconcile_alert_status(alert)
        return

    from_number    = os.environ.get("TWILIO_FROM_NUMBER")
    callback_base  = os.environ.get("TWILIO_CALLBACK_BASE_URL", "").rstrip("/")
    status_callback = f"{callback_base}/webhooks/twilio/sms" if callback_base else None

    try:
        client  = _get_client()
        message = client.messages.create(
            to=to_number,
            from_=from_number,
            body=_SMS_BODY.format(user_name=user_name),
            status_callback=status_callback,
        )
        log.info("send_guardian_sms queued alert=%d sid=%s", alert_id, message.sid)
        alert.sms_status      = "IN_FLIGHT"
        alert.sms_provider_id = message.sid
        db.session.commit()

    except TwilioRestException as exc:
        if exc.code in _NON_RETRIABLE_CODES:
            log.error("send_guardian_sms non_retriable alert=%d code=%d: %s",
                      alert_id, exc.code, exc)
            raise NonRetriableError(str(exc)) from exc
        log.warning("send_guardian_sms retriable alert=%d code=%d: %s",
                    alert_id, exc.code, exc)
        raise RetriableError(str(exc)) from exc

    except Exception as exc:
        log.warning("send_guardian_sms network_error alert=%d: %s", alert_id, exc)
        raise RetriableError(str(exc)) from exc


def handle_twilio_webhook(req) -> tuple:
    """
    Process a Twilio status-callback POST.
    Verifies the request signature, records the event, and updates sms_status.
    Returns (response_body, http_status_code).
    """
    # ── Signature verification ────────────────────────────────────────────────
    validator = RequestValidator(os.environ.get("TWILIO_AUTH_TOKEN", ""))
    signature = req.headers.get("X-Twilio-Signature", "")
    params    = req.form.to_dict()

    if not validator.validate(req.url, params, signature):
        log.warning("twilio_webhook invalid_signature url=%s", req.url)
        return "Forbidden", 403

    message_sid    = params.get("MessageSid", "")
    message_status = params.get("MessageStatus", "").lower()
    error_code     = params.get("ErrorCode", "")

    # ── Idempotency — one row per (provider, sid:status) ─────────────────────
    event_key = f"{message_sid}:{message_status}"
    if ProviderWebhookEvent.query.filter_by(
        provider="twilio", provider_event_id=event_key
    ).first():
        log.info("twilio_webhook duplicate event_key=%s", event_key)
        return "", 204

    alert = EmergencyAlert.query.filter_by(sms_provider_id=message_sid).first()

    db.session.add(ProviderWebhookEvent(
        provider          = "twilio",
        provider_event_id = event_key,
        alert_id          = alert.id if alert else None,
        raw_payload       = params,
    ))

    if alert is None:
        log.warning("twilio_webhook unknown_sid sid=%s", message_sid)
        db.session.commit()
        return "", 204

    new_status = _STATUS_MAP.get(message_status)
    if new_status and alert.sms_status not in ("DELIVERED", "FAILED"):
        log.info("twilio_webhook alert=%d %s→%s", alert.id, alert.sms_status, new_status)
        alert.sms_status = new_status
        if error_code:
            alert.sms_last_error = f"Twilio error {error_code}"
        db.session.commit()
        if new_status in ("DELIVERED", "FAILED"):
            reconcile_alert_status(alert)
    else:
        db.session.commit()

    return "", 204
