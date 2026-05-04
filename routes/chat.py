from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app
from flask_security import auth_required, current_user
from models import db, TherapySession, ChatMessage, SafetyAlert
from utils.prompts import build_system_prompt
from utils.risk_triage import triage_message
from utils.risk_engine import run_policy
from utils.safety_review import review_reply
from extensions import limiter

MAX_SAFETY_RETRIES = 3

SAFE_FALLBACK_MESSAGE = (
    "I want to respond carefully to what you shared. "
    "If this situation feels serious or urgent, please let me know clearly. "
    "You can also tell me more about what's going on right now."
)

_VALID_TRIAGE_RISK_LEVELS = {"CLEAR_IMMEDIATE_RISK", "POSSIBLE_HARM"}
_VALID_TRIAGE_ACTIONS     = {
    "IMMEDIATE_EMERGENCY_ACTION",
    "FLAG_AND_WARN",
    "FLAG_AND_MONITOR",
    "FLAG_FOR_HUMAN_REVIEW",
}

chat_bp = Blueprint("chat", __name__)

ALLOWED_ROLES = {"user", "assistant"}


@chat_bp.route("/api/chat", methods=["POST"])
@limiter.limit("30 per minute; 200 per day")
@auth_required()
def chat():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request body"}), 400

    session_id   = data.get("sessionId")
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    therapy_session = None
    if session_id:
        therapy_session = TherapySession.query.filter_by(
            id=session_id, user_id=current_user.id
        ).first()

    client = current_app.extensions["openai_client"]

    # ── 1. Incoming user-risk triage (issue #1 — fail safe) ───────────────────
    try:
        triage = triage_message(client, user_message)
    except Exception as exc:
        current_app.logger.warning("triage_message raised unexpectedly: %s", exc)
        triage = {
            "risk_level":         "POSSIBLE_HARM",
            "confidence":         "LOW",
            "evidence_for":       ["Triage model unavailable — flagged for safety"],
            "evidence_against":   [],
            "recommended_action": "FLAG_AND_MONITOR",
            "rationale":          "Outer triage guard caught exception; defaulting to POSSIBLE_HARM.",
        }
    # ── Normalize legacy action names (issue #3 — prompt/engine mismatch) ───────
    if triage.get("recommended_action") == "ACTIVATE_EMERGENCY_CONTACT_PROTOCOL":
        triage["recommended_action"] = "IMMEDIATE_EMERGENCY_ACTION"

    # ── Validate triage fields before policy (issue #1) ───────────────────────
    if triage.get("risk_level") not in _VALID_TRIAGE_RISK_LEVELS:
        current_app.logger.warning("Invalid risk_level from triage: %r", triage.get("risk_level"))
        triage["risk_level"] = "POSSIBLE_HARM"
    if triage.get("recommended_action") not in _VALID_TRIAGE_ACTIONS:
        current_app.logger.warning("Invalid recommended_action from triage: %r", triage.get("recommended_action"))
        triage["recommended_action"] = "FLAG_AND_MONITOR"

    policy = run_policy(current_user._get_current_object(), triage, session_id)

    current_app.logger.info(
        "safety_pipeline user=%s session=%s risk=%s confidence=%s action=%s safety_mode=%s",
        current_user.id, session_id,
        triage.get("risk_level"), triage.get("confidence"),
        triage.get("recommended_action"), policy.get("safety_mode"),
    )

    # ── 2. CRISIS: skip therapy, return crisis response immediately ───────────
    if policy["block_therapy"]:
        current_app.logger.critical(          # issue #5 — audit trail
            "CRISIS_TRIGGER user=%s session=%s risk=%s action=%s",
            current_user.id, session_id,
            triage.get("risk_level"), triage.get("recommended_action"),
        )
        if therapy_session:
            db.session.add(ChatMessage(session_id=session_id, role="user",      content=user_message))
            db.session.add(ChatMessage(session_id=session_id, role="assistant", content=policy["crisis_response"]))
            db.session.commit()
        return jsonify({
            "reply":            policy["crisis_response"],
            "safetyMode":       "CRISIS",
            "severityDetected": "CRITICAL",
        })

    # ── 3. Build session history ───────────────────────────────────────────────
    intake = current_user.intake.data if current_user.intake else {}

    all_past = TherapySession.query.filter(
        TherapySession.user_id == current_user.id,
        TherapySession.completed_at.isnot(None),
        TherapySession.summary.isnot(None),
        TherapySession.id != session_id
    ).order_by(TherapySession.started_at.desc()).all()

    recent = list(reversed(all_past[:10]))
    older  = list(reversed(all_past[10:]))

    past_context = ""
    if recent:
        recent_block = "\n".join(
            f"- {s.started_at.strftime('%b %d, %Y')}: {s.summary}"
            for s in recent
        )
        past_context += f"\n\nRecent session notes:\n{recent_block}"

    if older:
        def _brief(s):
            if s.brief_summary:
                return s.brief_summary
            return s.summary[:120].rstrip() + ("…" if len(s.summary) > 120 else "")

        older_block = "\n\n".join(
            f"{s.started_at.strftime('%b %d, %Y')}:\n{_brief(s)}"
            for s in older
        )
        past_context += f"\n\nEarlier session history:\n{older_block}"

    if therapy_session:
        db_history   = ChatMessage.query.filter_by(session_id=session_id)\
            .order_by(ChatMessage.timestamp).all()
        safe_history = [{"role": m.role, "content": m.content} for m in db_history]
    else:
        raw_history  = data.get("history", [])
        safe_history = [
            {"role": msg["role"], "content": str(msg["content"])}
            for msg in raw_history
            if isinstance(msg, dict) and msg.get("role") in ALLOWED_ROLES
        ]

    # ── 4. Build messages with safety_mode injected into system prompt ────────
    safety_mode = policy["safety_mode"]   # NORMAL or HEIGHTENED
    base_messages = [
        {"role": "system", "content": build_system_prompt(intake, safety_mode) + past_context},
        *safe_history,
        {"role": "user", "content": user_message},
    ]

    # ── 5. Therapist generation + outgoing safety review loop ─────────────────
    try:
        active_messages = list(base_messages)
        reply           = None

        for attempt in range(MAX_SAFETY_RETRIES):
            response = client.chat.completions.create(
                model="gpt-4.1",
                messages=active_messages,
                max_tokens=500,
                temperature=0.7,
            )
            draft  = response.choices[0].message.content
            review = review_reply(client, draft, user_message)

            # issue #5 — guard against malformed review response
            if not review or "safe_response" not in review:
                current_app.logger.warning("review_reply returned malformed output on attempt %d", attempt)
                reply = SAFE_FALLBACK_MESSAGE
                break

            if review["verdict"] in ("APPROVE", "REVISE"):
                reply = review["safe_response"] or SAFE_FALLBACK_MESSAGE
                break

            issues_text = "; ".join(review["issues"]) if review["issues"] else "safety violation"
            current_app.logger.info("safety_review BLOCK attempt=%d issues=%s", attempt, issues_text)
            active_messages = list(base_messages) + [{
                "role": "system",
                "content": (
                    f"Your previous response was blocked by the safety review layer "
                    f"for the following reason(s): {issues_text}. "
                    "Please rewrite your response avoiding these issues entirely. "
                    "Focus on immediate safety and supportive language."
                )
            }]

            if attempt == MAX_SAFETY_RETRIES - 1:
                reply = (review.get("safe_response") or SAFE_FALLBACK_MESSAGE)

        # ── 6. Prepend warning if policy requires it ──────────────────────────
        if policy["show_warning"] and policy["warning_text"]:
            reply = policy["warning_text"] + "\n\n" + reply

        # ── 7. Persist messages ───────────────────────────────────────────────
        if therapy_session:
            db.session.add(ChatMessage(session_id=session_id, role="user",      content=user_message))
            db.session.add(ChatMessage(session_id=session_id, role="assistant", content=reply))
            db.session.commit()

        return jsonify({
            "reply":      reply,
            "safetyMode": safety_mode,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
