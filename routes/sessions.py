from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app
from flask_security import auth_required, current_user
from models import db, TherapySession, ChatMessage

sessions_bp = Blueprint("sessions", __name__)


@sessions_bp.route("/api/sessions", methods=["GET"])
@auth_required()
def get_sessions():
    sessions = TherapySession.query.filter_by(user_id=current_user.id)\
        .order_by(TherapySession.started_at.desc()).all()
    return jsonify([{
        "id":          s.id,
        "startedAt":   s.started_at.isoformat(),
        "completedAt": s.completed_at.isoformat() if s.completed_at else None,
        "initialMood": s.initial_mood,
        "finalMood":   s.final_mood,
        "primaryGoal": s.primary_goal,
        "takeaway":    s.what_worked,
        "summary":     s.summary,
        "modalityUsed": s.modality_used
    } for s in sessions]), 200


@sessions_bp.route("/api/sessions", methods=["DELETE"])
@auth_required()
def delete_all_sessions():
    sessions = TherapySession.query.filter_by(user_id=current_user.id).all()
    for s in sessions:
        db.session.delete(s)
    db.session.commit()
    return jsonify({"message": "All sessions deleted"}), 200


@sessions_bp.route("/api/sessions", methods=["POST"])
@auth_required()
def start_session():
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Invalid request body"}), 400

    session = TherapySession(
        user_id=current_user.id,
        initial_mood=body.get("initialMood"),
        primary_goal=body.get("primaryGoal", "")
    )
    db.session.add(session)
    db.session.commit()
    return jsonify({"sessionId": session.id}), 201


@sessions_bp.route("/api/sessions/<int:session_id>/complete", methods=["POST"])
@auth_required()
def complete_session(session_id):
    session = TherapySession.query.filter_by(id=session_id, user_id=current_user.id).first()
    if not session:
        return jsonify({"error": "Session not found"}), 404

    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Invalid request body"}), 400

    session.final_mood   = body.get("finalMood")
    session.what_worked  = body.get("whatWorked", "")
    session.completed_at = datetime.now(timezone.utc)

    messages = ChatMessage.query.filter_by(session_id=session_id)\
        .order_by(ChatMessage.timestamp).all()

    if messages:
        transcript = "\n".join([f"{m.role.upper()}: {m.content}" for m in messages])
        try:
            client = current_app.extensions["openai_client"]
            summary_response = client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {"role": "system", "content": (
                        "You are summarizing a therapy session. Produce TWO outputs separated by the delimiter '---BRIEF---':\n"
                        "1. A thorough summary in up to 2 paragraphs. Cover: presenting mood, key themes discussed, "
                        "emotional shifts, therapeutic techniques used, progress made, any concerns or risks, and homework/action items. "
                        "Be clinical but compassionate.\n"
                        "2. A brief version: 2-3 sentences only. Hit the most important point, mood outcome, and any follow-up needed."
                    )},
                    {"role": "user", "content": f"Summarize this session:\n\n{transcript}"}
                ],
                max_tokens=400,
                temperature=0.5
            )
            raw = summary_response.choices[0].message.content
            if "---BRIEF---" in raw:
                full, brief         = raw.split("---BRIEF---", 1)
                session.summary       = full.strip()
                session.brief_summary = brief.strip()
            else:
                session.summary       = raw.strip()
                session.brief_summary = None
        except Exception:
            session.summary       = "Summary unavailable."
            session.brief_summary = None

    db.session.commit()
    return jsonify({"message": "Session completed", "summary": session.summary}), 200


@sessions_bp.route("/api/sessions/<int:session_id>", methods=["GET"])
@auth_required()
def get_session(session_id):
    session = TherapySession.query.filter_by(id=session_id, user_id=current_user.id).first()
    if not session:
        return jsonify({"error": "Session not found"}), 404

    messages = ChatMessage.query.filter_by(session_id=session_id)\
        .order_by(ChatMessage.timestamp).all()

    return jsonify({
        "id":          session.id,
        "startedAt":   session.started_at.isoformat(),
        "completedAt": session.completed_at.isoformat() if session.completed_at else None,
        "initialMood": session.initial_mood,
        "finalMood":   session.final_mood,
        "primaryGoal": session.primary_goal,
        "summary":     session.summary,
        "messages":    [{"role": m.role, "content": m.content} for m in messages]
    }), 200
