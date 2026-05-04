"""
Tests for the emergency alert system.
Covers: idempotency, retry logic, webhook deduplication, reconciliation, failure handling.
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from twilio.base.exceptions import TwilioRestException


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL",                    "sqlite:///:memory:")
    monkeypatch.setenv("OPENAI_API_KEY",                  "test-key")
    monkeypatch.setenv("TWILIO_ACCOUNT_SID",              "ACtest123")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN",               "test_auth_token")
    monkeypatch.setenv("TWILIO_FROM_NUMBER",              "+15550000000")
    monkeypatch.setenv("TWILIO_CALLBACK_BASE_URL",        "http://localhost:5000")
    monkeypatch.setenv("SENDGRID_API_KEY",                "SG.testkey")
    monkeypatch.setenv("SENDGRID_FROM_EMAIL",             "alerts@test.com")
    monkeypatch.setenv("SENDGRID_WEBHOOK_VERIFICATION_KEY", "test-ec-key")


@pytest.fixture
def app(_env):
    from app import create_app
    application = create_app()
    application.config["TESTING"] = True
    ctx = application.app_context()
    ctx.push()
    yield application
    from models import db
    db.session.remove()
    db.drop_all()
    ctx.pop()


@pytest.fixture
def db(app):
    from models import db as _db
    return _db


@pytest.fixture
def user(db):
    from models import User, GuardianProfile
    u = User(username="testuser", password="hashed_pw")
    db.session.add(u)
    db.session.flush()
    db.session.add(GuardianProfile(
        user_id=u.id, name="Jane Guardian",
        email="guardian@example.com", phone="+15551234567",
    ))
    db.session.commit()
    db.session.refresh(u)
    return u


@pytest.fixture
def safety_alert(db, user):
    from models import SafetyAlert
    a = SafetyAlert(user_id=user.id, severity_level="CRITICAL")
    db.session.add(a)
    db.session.commit()
    return a


@pytest.fixture
def ea(db, user, safety_alert):
    """Pre-built EmergencyAlert with full guardian snapshot."""
    from models import EmergencyAlert
    record = EmergencyAlert(
        user_id          = user.id,
        message_id       = str(safety_alert.id),
        idempotency_key  = f"emergency:{user.id}:None:{safety_alert.id}",
        status           = "DISPATCHING",
        sms_status       = "PENDING",
        email_status     = "PENDING",
        payload_snapshot = {
            "user_id":         user.id,
            "user_name":       user.username,
            "guardian_email":  "guardian@example.com",
            "guardian_phone":  "+15551234567",
            "safety_alert_id": safety_alert.id,
        },
    )
    db.session.add(record)
    db.session.commit()
    return record


def _make_twilio_request(sid="SMtest123", status="delivered", error_code=""):
    req = MagicMock()
    req.url = "http://localhost:5000/webhooks/twilio/sms"
    req.form.to_dict.return_value = {
        "MessageSid":    sid,
        "MessageStatus": status,
        "ErrorCode":     error_code,
    }
    req.headers.get = lambda key, default="": {
        "X-Twilio-Signature": "valid_sig",
    }.get(key, default)
    return req


def _make_sendgrid_request(events: list):
    req = MagicMock()
    req.get_data.return_value = json.dumps(events)
    req.headers.get = lambda key, default="": {
        "X-Twilio-Email-Event-Webhook-Signature": "valid_sig",
        "X-Twilio-Email-Event-Webhook-Timestamp": "1234567890",
    }.get(key, default)
    return req


# ── trigger_emergency_alert ───────────────────────────────────────────────────

def test_trigger_creates_alert(app, db, user, safety_alert):
    from models import EmergencyAlert
    from services.emergency_alerts import trigger_emergency_alert

    with patch("services.emergency_alerts._run_in_background") as mock_bg:
        result = trigger_emergency_alert(user, safety_alert, None)

    assert result.id is not None
    assert result.status == "DISPATCHING"
    assert result.sms_status == "PENDING"
    assert result.email_status == "PENDING"
    assert result.payload_snapshot["guardian_email"] == "guardian@example.com"
    assert result.payload_snapshot["guardian_phone"] == "+15551234567"
    assert mock_bg.call_count == 2  # one SMS thread, one email thread
    assert db.session.get(EmergencyAlert, result.id) is not None


def test_trigger_idempotent(app, db, user, safety_alert):
    from models import EmergencyAlert
    from services.emergency_alerts import trigger_emergency_alert

    with patch("services.emergency_alerts._run_in_background"):
        first  = trigger_emergency_alert(user, safety_alert, None)
        second = trigger_emergency_alert(user, safety_alert, None)

    assert first.id == second.id
    assert db.session.query(EmergencyAlert).count() == 1


# ── reconcile_alert_status ────────────────────────────────────────────────────

def test_reconcile_both_delivered(db, ea):
    from services.emergency_alerts import reconcile_alert_status
    ea.sms_status   = "DELIVERED"
    ea.email_status = "DELIVERED"
    db.session.commit()

    reconcile_alert_status(ea)

    assert ea.status == "SENT"
    assert ea.completed_at is not None


def test_reconcile_partial(db, ea):
    from services.emergency_alerts import reconcile_alert_status
    ea.sms_status   = "DELIVERED"
    ea.email_status = "FAILED"
    db.session.commit()

    reconcile_alert_status(ea)

    assert ea.status == "PARTIALLY_SENT"
    assert ea.completed_at is not None


def test_reconcile_both_failed(db, ea):
    from services.emergency_alerts import reconcile_alert_status
    ea.sms_status   = "FAILED"
    ea.email_status = "FAILED"
    db.session.commit()

    reconcile_alert_status(ea)

    assert ea.status == "FAILED"


def test_reconcile_both_skipped(db, ea):
    from services.emergency_alerts import reconcile_alert_status
    ea.sms_status   = "SKIPPED"
    ea.email_status = "SKIPPED"
    db.session.commit()

    reconcile_alert_status(ea)

    assert ea.status == "FAILED"  # no contact info on either channel


def test_reconcile_delivered_and_skipped(db, ea):
    from services.emergency_alerts import reconcile_alert_status
    ea.sms_status   = "DELIVERED"
    ea.email_status = "SKIPPED"
    db.session.commit()

    reconcile_alert_status(ea)

    assert ea.status == "SENT"  # one channel reached guardian


def test_reconcile_in_flight(db, ea):
    from services.emergency_alerts import reconcile_alert_status
    ea.sms_status   = "IN_FLIGHT"
    ea.email_status = "PENDING"
    db.session.commit()

    reconcile_alert_status(ea)

    assert ea.status == "DISPATCHING"  # still waiting


# ── send_guardian_sms ─────────────────────────────────────────────────────────

def test_sms_skipped_when_no_phone(db, ea):
    from services.notifications.twilio_sms import send_guardian_sms
    ea.payload_snapshot = {**ea.payload_snapshot, "guardian_phone": None}
    db.session.commit()

    with patch("services.emergency_alerts.reconcile_alert_status") as mock_rec:
        send_guardian_sms(ea.id)

    db.session.refresh(ea)
    assert ea.sms_status == "SKIPPED"
    mock_rec.assert_called_once()


def test_sms_success(db, ea):
    from services.notifications.twilio_sms import send_guardian_sms

    mock_message     = MagicMock()
    mock_message.sid = "SMtest123"

    with patch("services.notifications.twilio_sms.Client") as mock_cls:
        mock_cls.return_value.messages.create.return_value = mock_message
        send_guardian_sms(ea.id)

    db.session.refresh(ea)
    assert ea.sms_status      == "IN_FLIGHT"
    assert ea.sms_provider_id == "SMtest123"


def test_sms_non_retriable_error(db, ea):
    from services.notifications.twilio_sms import send_guardian_sms
    from services.emergency_alerts import NonRetriableError

    exc = TwilioRestException(status=400, uri="/messages", msg="Invalid number", code=21211)
    with patch("services.notifications.twilio_sms.Client") as mock_cls:
        mock_cls.return_value.messages.create.side_effect = exc
        with pytest.raises(NonRetriableError):
            send_guardian_sms(ea.id)


def test_sms_retriable_error(db, ea):
    from services.notifications.twilio_sms import send_guardian_sms
    from services.emergency_alerts import RetriableError

    exc = TwilioRestException(status=503, uri="/messages", msg="Service unavailable", code=20500)
    with patch("services.notifications.twilio_sms.Client") as mock_cls:
        mock_cls.return_value.messages.create.side_effect = exc
        with pytest.raises(RetriableError):
            send_guardian_sms(ea.id)


# ── handle_twilio_webhook ─────────────────────────────────────────────────────

def test_twilio_webhook_invalid_signature(app, db, ea):
    from services.notifications.twilio_sms import handle_twilio_webhook

    with patch("services.notifications.twilio_sms.RequestValidator") as mock_rv:
        mock_rv.return_value.validate.return_value = False
        body, status = handle_twilio_webhook(_make_twilio_request())

    assert status == 403


def test_twilio_webhook_delivered(app, db, ea):
    from services.notifications.twilio_sms import handle_twilio_webhook
    ea.sms_provider_id = "SMtest123"
    ea.sms_status      = "IN_FLIGHT"
    db.session.commit()

    with patch("services.notifications.twilio_sms.RequestValidator") as mock_rv:
        mock_rv.return_value.validate.return_value = True
        body, status = handle_twilio_webhook(
            _make_twilio_request(sid="SMtest123", status="delivered")
        )

    assert status == 204
    db.session.refresh(ea)
    assert ea.sms_status == "DELIVERED"


def test_twilio_webhook_failed_status(app, db, ea):
    from services.notifications.twilio_sms import handle_twilio_webhook
    ea.sms_provider_id = "SMtest123"
    ea.sms_status      = "IN_FLIGHT"
    db.session.commit()

    with patch("services.notifications.twilio_sms.RequestValidator") as mock_rv:
        mock_rv.return_value.validate.return_value = True
        handle_twilio_webhook(
            _make_twilio_request(sid="SMtest123", status="failed", error_code="30008")
        )

    db.session.refresh(ea)
    assert ea.sms_status    == "FAILED"
    assert ea.sms_last_error == "Twilio error 30008"


def test_twilio_webhook_duplicate_ignored(app, db, ea):
    from services.notifications.twilio_sms import handle_twilio_webhook
    from models import ProviderWebhookEvent
    ea.sms_provider_id = "SMtest123"
    ea.sms_status      = "IN_FLIGHT"
    db.session.commit()

    req = _make_twilio_request(sid="SMtest123", status="delivered")
    with patch("services.notifications.twilio_sms.RequestValidator") as mock_rv:
        mock_rv.return_value.validate.return_value = True
        handle_twilio_webhook(req)
        handle_twilio_webhook(req)  # duplicate

    assert db.session.query(ProviderWebhookEvent).count() == 1


def test_twilio_webhook_unknown_sid(app, db):
    from services.notifications.twilio_sms import handle_twilio_webhook
    from models import ProviderWebhookEvent

    with patch("services.notifications.twilio_sms.RequestValidator") as mock_rv:
        mock_rv.return_value.validate.return_value = True
        body, status = handle_twilio_webhook(
            _make_twilio_request(sid="SMunknown", status="delivered")
        )

    assert status == 204
    event = db.session.query(ProviderWebhookEvent).first()
    assert event is not None
    assert event.alert_id is None


# ── send_guardian_email ───────────────────────────────────────────────────────

def test_email_skipped_when_no_address(db, ea):
    from services.notifications.sendgrid_email import send_guardian_email
    ea.payload_snapshot = {**ea.payload_snapshot, "guardian_email": None}
    db.session.commit()

    with patch("services.emergency_alerts.reconcile_alert_status") as mock_rec:
        send_guardian_email(ea.id)

    db.session.refresh(ea)
    assert ea.email_status == "SKIPPED"
    mock_rec.assert_called_once()


def test_email_success(db, ea):
    from services.notifications.sendgrid_email import send_guardian_email

    mock_response         = MagicMock()
    mock_response.status_code = 202
    mock_response.headers.get.return_value = "msg-id-abc"

    with patch("services.notifications.sendgrid_email.SendGridAPIClient") as mock_cls:
        mock_cls.return_value.send.return_value = mock_response
        send_guardian_email(ea.id)

    db.session.refresh(ea)
    assert ea.email_status      == "IN_FLIGHT"
    assert ea.email_provider_id == "msg-id-abc"


def test_email_non_retriable_4xx(db, ea):
    from services.notifications.sendgrid_email import send_guardian_email
    from services.emergency_alerts import NonRetriableError

    exc = Exception("Bad request")
    exc.status_code = 400
    with patch("services.notifications.sendgrid_email.SendGridAPIClient") as mock_cls:
        mock_cls.return_value.send.side_effect = exc
        with pytest.raises(NonRetriableError):
            send_guardian_email(ea.id)


def test_email_retriable_5xx(db, ea):
    from services.notifications.sendgrid_email import send_guardian_email
    from services.emergency_alerts import RetriableError

    exc = Exception("Internal error")
    exc.status_code = 500
    with patch("services.notifications.sendgrid_email.SendGridAPIClient") as mock_cls:
        mock_cls.return_value.send.side_effect = exc
        with pytest.raises(RetriableError):
            send_guardian_email(ea.id)


def test_email_retriable_429(db, ea):
    from services.notifications.sendgrid_email import send_guardian_email
    from services.emergency_alerts import RetriableError

    exc = Exception("Rate limited")
    exc.status_code = 429
    with patch("services.notifications.sendgrid_email.SendGridAPIClient") as mock_cls:
        mock_cls.return_value.send.side_effect = exc
        with pytest.raises(RetriableError):
            send_guardian_email(ea.id)


# ── handle_sendgrid_webhook ───────────────────────────────────────────────────

def test_sendgrid_webhook_no_key(app, db, monkeypatch):
    from services.notifications.sendgrid_email import handle_sendgrid_webhook
    monkeypatch.setenv("SENDGRID_WEBHOOK_VERIFICATION_KEY", "")

    body, status = handle_sendgrid_webhook(_make_sendgrid_request([]))
    assert status == 403


def test_sendgrid_webhook_invalid_signature(app, db):
    from services.notifications.sendgrid_email import handle_sendgrid_webhook

    with patch("services.notifications.sendgrid_email.EventWebhook") as mock_ev:
        mock_ev.return_value.verify_signature.return_value = False
        body, status = handle_sendgrid_webhook(_make_sendgrid_request([]))

    assert status == 403


def test_sendgrid_webhook_delivered(app, db, ea):
    from services.notifications.sendgrid_email import handle_sendgrid_webhook
    ea.email_provider_id = "msg-id-abc"
    ea.email_status      = "IN_FLIGHT"
    db.session.commit()

    events = [{
        "sg_event_id":   "evt-001",
        "sg_message_id": "msg-id-abc.filter0",
        "event":         "delivered",
    }]
    with patch("services.notifications.sendgrid_email.EventWebhook") as mock_ev:
        mock_ev.return_value.verify_signature.return_value = True
        body, status = handle_sendgrid_webhook(_make_sendgrid_request(events))

    assert status == 204
    db.session.refresh(ea)
    assert ea.email_status == "DELIVERED"


def test_sendgrid_webhook_bounce(app, db, ea):
    from services.notifications.sendgrid_email import handle_sendgrid_webhook
    ea.email_provider_id = "msg-id-abc"
    ea.email_status      = "IN_FLIGHT"
    db.session.commit()

    events = [{
        "sg_event_id":   "evt-002",
        "sg_message_id": "msg-id-abc.filter0",
        "event":         "bounce",
    }]
    with patch("services.notifications.sendgrid_email.EventWebhook") as mock_ev:
        mock_ev.return_value.verify_signature.return_value = True
        handle_sendgrid_webhook(_make_sendgrid_request(events))

    db.session.refresh(ea)
    assert ea.email_status    == "FAILED"
    assert ea.email_last_error == "SendGrid event: bounce"


def test_sendgrid_webhook_duplicate_ignored(app, db, ea):
    from services.notifications.sendgrid_email import handle_sendgrid_webhook
    from models import ProviderWebhookEvent
    ea.email_provider_id = "msg-id-abc"
    ea.email_status      = "IN_FLIGHT"
    db.session.commit()

    events = [{
        "sg_event_id":   "evt-001",
        "sg_message_id": "msg-id-abc.filter0",
        "event":         "delivered",
    }]
    with patch("services.notifications.sendgrid_email.EventWebhook") as mock_ev:
        mock_ev.return_value.verify_signature.return_value = True
        handle_sendgrid_webhook(_make_sendgrid_request(events))
        handle_sendgrid_webhook(_make_sendgrid_request(events))  # duplicate

    assert db.session.query(ProviderWebhookEvent).count() == 1


def test_sendgrid_webhook_batched_events(app, db, ea):
    """Multiple events in one POST are each processed independently."""
    from services.notifications.sendgrid_email import handle_sendgrid_webhook
    from models import ProviderWebhookEvent
    ea.email_provider_id = "msg-id-abc"
    ea.email_status      = "IN_FLIGHT"
    db.session.commit()

    events = [
        {"sg_event_id": "evt-A", "sg_message_id": "msg-id-abc.filter0", "event": "processed"},
        {"sg_event_id": "evt-B", "sg_message_id": "msg-id-abc.filter0", "event": "delivered"},
    ]
    with patch("services.notifications.sendgrid_email.EventWebhook") as mock_ev:
        mock_ev.return_value.verify_signature.return_value = True
        body, status = handle_sendgrid_webhook(_make_sendgrid_request(events))

    assert status == 204
    assert db.session.query(ProviderWebhookEvent).count() == 2
    db.session.refresh(ea)
    assert ea.email_status == "DELIVERED"


# ── _channel_with_retry ───────────────────────────────────────────────────────

def test_channel_stops_on_non_retriable(app, db, ea):
    from services.emergency_alerts import _channel_with_retry, NonRetriableError

    call_count = {"n": 0}
    def bad_send(alert_id):
        call_count["n"] += 1
        raise NonRetriableError("permanent failure")

    with patch("services.emergency_alerts.time.sleep"):
        _channel_with_retry(ea.id, "sms", bad_send)

    assert call_count["n"] == 1  # no retries after non-retriable
    db.session.refresh(ea)
    assert ea.sms_status == "FAILED"


def test_channel_retries_then_fails(app, db, ea):
    from services.emergency_alerts import _channel_with_retry, RetriableError, MAX_ATTEMPTS

    call_count = {"n": 0}
    def flaky_send(alert_id):
        call_count["n"] += 1
        raise RetriableError("temporary failure")

    with patch("services.emergency_alerts.time.sleep"):
        _channel_with_retry(ea.id, "sms", flaky_send)

    assert call_count["n"] == MAX_ATTEMPTS
    db.session.refresh(ea)
    assert ea.sms_status == "FAILED"


def test_channel_succeeds_on_second_attempt(app, db, ea):
    from services.emergency_alerts import _channel_with_retry, RetriableError

    attempts = {"n": 0}
    def eventually_works(alert_id):
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise RetriableError("not yet")
        # success — function returns None and updates status itself
        from models import db as _db, EmergencyAlert
        alert = _db.session.get(EmergencyAlert, alert_id)
        alert.sms_status = "IN_FLIGHT"
        _db.session.commit()

    with patch("services.emergency_alerts.time.sleep"):
        _channel_with_retry(ea.id, "sms", eventually_works)

    assert attempts["n"] == 2
    db.session.refresh(ea)
    assert ea.sms_status == "IN_FLIGHT"


def test_channel_bails_if_already_terminal(app, db, ea):
    """If status is already DELIVERED when the loop checks, stop immediately."""
    from services.emergency_alerts import _channel_with_retry

    ea.sms_status = "DELIVERED"
    db.session.commit()

    call_count = {"n": 0}
    def should_not_run(alert_id):
        call_count["n"] += 1

    with patch("services.emergency_alerts.time.sleep"):
        _channel_with_retry(ea.id, "sms", should_not_run)

    assert call_count["n"] == 0
