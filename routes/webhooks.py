from flask import Blueprint, request
from extensions import limiter

webhooks_bp = Blueprint("webhooks", __name__)


@webhooks_bp.route("/webhooks/twilio/sms", methods=["POST"])
@limiter.limit("120 per minute")
def twilio_sms_webhook():
    from services.notifications.twilio_sms import handle_twilio_webhook
    body, status = handle_twilio_webhook(request)
    return body, status


@webhooks_bp.route("/webhooks/sendgrid/events", methods=["POST"])
@limiter.limit("120 per minute")
def sendgrid_events_webhook():
    from services.notifications.sendgrid_email import handle_sendgrid_webhook
    body, status = handle_sendgrid_webhook(request)
    return body, status
