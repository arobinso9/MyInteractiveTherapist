from flask import Blueprint, request, jsonify
from flask_security import auth_required, current_user
from models import db, JournalEntry

journal_bp = Blueprint("journal", __name__)


@journal_bp.route("/api/journal", methods=["POST"])
@auth_required()
def save_journal():
    body = request.get_json(silent=True)
    if not body or not body.get("content", "").strip():
        return jsonify({"error": "Journal content is required"}), 400

    entry = JournalEntry(user_id=current_user.id, content=body["content"].strip())
    db.session.add(entry)
    db.session.commit()
    return jsonify({"message": "Journal entry saved", "id": entry.id}), 201


@journal_bp.route("/api/journal", methods=["GET"])
@auth_required()
def get_journal():
    entries = JournalEntry.query.filter_by(user_id=current_user.id)\
        .order_by(JournalEntry.created_at.desc()).all()
    return jsonify([{
        "id":        e.id,
        "content":   e.content,
        "createdAt": e.created_at.isoformat()
    } for e in entries]), 200
