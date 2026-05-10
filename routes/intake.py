from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_security import auth_required, current_user
from sqlalchemy.orm.attributes import flag_modified
from models import db, IntakeProfile

intake_bp = Blueprint("intake", __name__)


@intake_bp.route("/api/intake", methods=["GET"])
@auth_required()
def get_intake():
    if not current_user.intake:
        return jsonify({"error": "No intake found"}), 404
    return jsonify({
        "data": current_user.intake.data,
        "completedAt": (current_user.intake.completed_at.isoformat() + "Z") if current_user.intake.completed_at else None
    }), 200


@intake_bp.route("/api/intake", methods=["POST"])
@auth_required()
def save_intake():
    body = request.get_json(silent=True)
    if not body or "data" not in body:
        return jsonify({"error": "Intake data is required"}), 400

    completed = body.get("completed", False)

    if current_user.intake:
        current_user.intake.data = body["data"]
        flag_modified(current_user.intake, "data")
        if completed:
            current_user.intake.completed_at = datetime.now(timezone.utc)
    else:
        intake = IntakeProfile(
            user_id=current_user.id,
            data=body["data"],
            completed_at=datetime.now(timezone.utc) if completed else None
        )
        db.session.add(intake)

    db.session.commit()
    return jsonify({"message": "Intake saved"}), 200
