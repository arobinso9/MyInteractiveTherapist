from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_security import auth_required, current_user
from models import db, SafetyAlert

safety_bp = Blueprint("safety", __name__)


@safety_bp.route("/api/safety-trigger", methods=["POST"])
@auth_required()
def safety_trigger():
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Invalid request body"}), 400

    severity = body.get("severityLevel", "LOW").upper()
    if severity not in ("LOW", "MEDIUM", "CRITICAL"):
        severity = "LOW"

    alert = SafetyAlert(
        user_id=current_user.id,
        session_id=body.get("sessionId"),
        trigger_phrase=body.get("triggerPhrase", ""),
        severity_level=severity,
        action_taken=body.get("actionTaken", "")
    )
    db.session.add(alert)

    if severity == "CRITICAL" and current_user.guardian:
        alert.notified_at = datetime.now(timezone.utc)

    db.session.commit()
    return jsonify({
        "message": "Safety alert logged",
        "severity": severity,
        "guardianNotified": alert.notified_at is not None
    }), 201
