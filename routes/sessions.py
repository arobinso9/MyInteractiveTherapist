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
        "id":              s.id,
        "startedAt":       s.started_at.isoformat() + "Z",
        "completedAt":     (s.completed_at.isoformat() + "Z") if s.completed_at else None,
        "initialMood":     s.initial_mood,
        "finalMood":       s.final_mood,
        "primaryGoal":     s.primary_goal,
        "takeaway":        s.what_worked,
        "summary":         s.summary,
        "modalityUsed":    s.modality_used,
        "nextSessionGoal": s.next_session_goal,
    } for s in sessions]), 200


@sessions_bp.route("/api/sessions", methods=["DELETE"])
@auth_required()
def delete_sessions():
    body         = request.get_json(silent=True) or {}
    session_ids  = body.get("sessionIds")

    query = TherapySession.query.filter_by(user_id=current_user.id)
    if isinstance(session_ids, list) and session_ids:
        query = query.filter(TherapySession.id.in_(session_ids))

    sessions = query.all()
    for s in sessions:
        db.session.delete(s)
    db.session.commit()
    return jsonify({"message": f"Deleted {len(sessions)} session(s)", "count": len(sessions)}), 200


_VALID_FOLLOWTHROUGH = {"yes", "partial", "no", "skipped"}


@sessions_bp.route("/api/sessions", methods=["POST"])
@auth_required()
def start_session():
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Invalid request body"}), 400

    followthrough = (body.get("priorGoalFollowthrough") or "").strip().lower()
    if followthrough and followthrough not in _VALID_FOLLOWTHROUGH:
        followthrough = None
    note = (body.get("priorGoalNote") or "").strip() or None

    session = TherapySession(
        user_id=current_user.id,
        initial_mood=body.get("initialMood"),
        primary_goal=body.get("primaryGoal", ""),
        prior_goal_followthrough=followthrough or None,
        prior_goal_note=note,
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

    # Goal from post-check (may be edited from the wrap-up draft, or skipped entirely)
    goal_raw = (body.get("nextSessionGoal") or "").strip()
    session.next_session_goal = goal_raw or None

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


@sessions_bp.route("/api/sessions/<int:session_id>/wrap-up", methods=["POST"])
@auth_required()
def wrap_up_session(session_id):
    session = TherapySession.query.filter_by(id=session_id, user_id=current_user.id).first()
    if not session:
        return jsonify({"error": "Session not found"}), 404
    if session.completed_at:
        return jsonify({"error": "Session already completed"}), 400

    messages = ChatMessage.query.filter_by(session_id=session_id)\
        .order_by(ChatMessage.timestamp).all()
    if not messages:
        return jsonify({"error": "No messages in session to wrap up"}), 400

    transcript = "\n".join(f"{m.role.upper()}: {m.content}" for m in messages)

    wrap_up_system = (
        "You are a therapist wrapping up the session. The client just indicated they're ending. "
        "Produce TWO outputs separated by the delimiter '---GOAL---':\n\n"
        "1. A warm, concise closing message (2-4 sentences). Briefly acknowledge what came up in this session, "
        "then propose ONE small, specific, actionable goal for the client to work on before next session. "
        "End with an open question like 'does that feel doable?' so they can respond.\n\n"
        "2. The goal itself in 1-2 sentences under 50 words. This is what will be saved and "
        "asked about next session. It should be concrete and doable.\n\n"
        "Format example:\n"
        "You shared a lot about how heavy work has been this week. For next time, a small goal could be: "
        "notice one moment when you feel that tightness in your chest and pause for three slow breaths before reacting. "
        "Does that feel like something you can try?\n"
        "---GOAL---\n"
        "Pause for three breaths when chest tightness appears at work."
    )

    try:
        client = current_app.extensions["openai_client"]
        resp = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": wrap_up_system},
                {"role": "user",   "content": f"Session transcript:\n\n{transcript}"}
            ],
            max_tokens=350,
            temperature=0.5,
        )
        raw = resp.choices[0].message.content
        if "---GOAL---" in raw:
            reply, goal = raw.split("---GOAL---", 1)
            reply = reply.strip()
            goal  = goal.strip()
        else:
            reply = raw.strip()
            goal  = ""
    except Exception as exc:
        current_app.logger.warning("wrap_up generation failed: %s", exc)
        reply = "Before we wrap, what's one small thing you want to work on before next session?"
        goal  = ""

    db.session.add(ChatMessage(session_id=session_id, role="assistant", content=reply))
    session.next_session_goal = goal or None
    db.session.commit()

    return jsonify({"reply": reply, "proposedGoal": goal}), 200


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
        "startedAt":   session.started_at.isoformat() + "Z",
        "completedAt": (session.completed_at.isoformat() + "Z") if session.completed_at else None,
        "initialMood": session.initial_mood,
        "finalMood":   session.final_mood,
        "primaryGoal": session.primary_goal,
        "summary":     session.summary,
        "messages":    [{"role": m.role, "content": m.content} for m in messages]
    }), 200
