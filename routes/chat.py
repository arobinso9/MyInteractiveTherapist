import re
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

# Sync safety net: if a reply contains any of these, the popup fires regardless of triage verdict
_HOTLINE_KEYWORDS = re.compile(
    r"\b(988|741741|crisis text line|crisis lifeline|suicide.{0,5}crisis lifeline|findahelpline)\b",
    re.IGNORECASE,
)

SAFE_FALLBACK_MESSAGE = (
    "I want to respond carefully to what you shared. "
    "If this situation feels serious or urgent, please let me know clearly. "
    "You can also tell me more about what's going on right now."
)

_VALID_TRIAGE_RISK_LEVELS = {"NO_RISK", "CLEAR_IMMEDIATE_RISK", "POSSIBLE_HARM"}
_VALID_TRIAGE_ACTIONS     = {
    "NO_ACTION",
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
    wrap_up_mode = bool(data.get("wrapUp"))
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

    # Prior session's goal (if any) — surfaces to the AI so it can ask about progress
    prior_goal_session = all_past[0] if all_past else None
    if prior_goal_session and prior_goal_session.next_session_goal:
        past_context += (
            f"\n\nGoal set at end of last session ({prior_goal_session.started_at.strftime('%b %d, %Y')}): "
            f"\"{prior_goal_session.next_session_goal}\""
        )

    # User's pre-check answer about that prior goal (filled in on the pre-check screen)
    if therapy_session and therapy_session.prior_goal_followthrough:
        ft = therapy_session.prior_goal_followthrough
        note = therapy_session.prior_goal_note
        past_context += f"\n\nClient's pre-check answer about that goal: {ft}"
        if note:
            past_context += f" — they added: \"{note}\""

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

    # ── Pattern detection (only on first turn of a non-wrapup session) ────────
    is_first_turn = len(safe_history) == 0 and not wrap_up_mode
    if is_first_turn and therapy_session:
        # Pattern A: 3 most recent completed sessions all had next_session_goal = NULL (skipped goal-setting)
        last_three_completed = TherapySession.query.filter(
            TherapySession.user_id == current_user.id,
            TherapySession.completed_at.isnot(None),
            TherapySession.id != session_id,
        ).order_by(TherapySession.started_at.desc()).limit(3).all()

        if len(last_three_completed) == 3 and all(s.next_session_goal is None for s in last_three_completed):
            past_context += (
                "\n\nPATTERN ALERT — open this session by gently raising it ONCE, then continue normally: "
                "the client has skipped setting a goal at the end of their last 3 sessions in a row. "
                "Example phrasing: \"I notice the past few times we've wrapped up without picking anything to work on between sessions. "
                "I'm curious what's behind that — does setting a goal feel like pressure, or has nothing felt quite right? "
                "Could we explore that?\""
            )
        else:
            # Pattern B: last 3 followthrough answers (current + most recent past) all 'no' or 'skipped'
            ft_sessions = []
            if therapy_session.prior_goal_followthrough:
                ft_sessions.append(therapy_session)
            past_ft = TherapySession.query.filter(
                TherapySession.user_id == current_user.id,
                TherapySession.completed_at.isnot(None),
                TherapySession.id != session_id,
                TherapySession.prior_goal_followthrough.isnot(None),
            ).order_by(TherapySession.started_at.desc()).limit(3).all()
            ft_sessions.extend(past_ft)
            last_three_ft = ft_sessions[:3]

            if len(last_three_ft) == 3 and all(s.prior_goal_followthrough in ("no", "skipped") for s in last_three_ft):
                past_context += (
                    "\n\nPATTERN ALERT — open this session by gently raising it ONCE, then continue normally: "
                    "the client has set goals the last 3 sessions but hasn't followed through on any of them. "
                    "Example phrasing: \"I notice we've set goals the past few sessions and they haven't gotten followed through. "
                    "I'm curious what's getting in the way — is it that the goals haven't felt right, or something else?\""
                )

    # TEMP DIAGNOSTIC — remove later
    print(f"[CHAT_DIAG] session_id={session_id} risk={triage.get('risk_level')} conf={triage.get('confidence')} action={triage.get('recommended_action')} mode={policy.get('safety_mode')} hist={len(safe_history)} firstTurn={is_first_turn}", flush=True)

    # ── 4. Build messages with safety_mode injected into system prompt ────────
    safety_mode = policy["safety_mode"]   # NORMAL or HEIGHTENED
    system_content = build_system_prompt(intake, safety_mode) + past_context

    if wrap_up_mode:
        system_content += (
            "\n\nWRAP-UP MODE: The session is ending. The client may want to refine, push back on, "
            "or change the goal you proposed. Engage with their input. After your conversational reply, "
            "append a single line:\n"
            "---GOAL---\n"
            "<the current proposed goal in 1-2 sentences under 50 words>\n"
            "If no goal has been agreed yet or the client doesn't want one, write 'NONE' after ---GOAL---."
        )

    base_messages = [
        {"role": "system", "content": system_content},
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

            if review["verdict"] == "APPROVE":
                reply = draft
                break
            if review["verdict"] == "REVISE":
                reply = review["safe_response"] or draft or SAFE_FALLBACK_MESSAGE
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

        # ── 6b. Wrap-up mode: split reply from proposed goal ──────────────────
        proposed_goal = None
        if wrap_up_mode and "---GOAL---" in reply:
            chat_part, goal_part = reply.split("---GOAL---", 1)
            reply = chat_part.strip()
            goal_text = goal_part.strip()
            if goal_text and goal_text.upper() != "NONE":
                proposed_goal = goal_text
            if therapy_session:
                therapy_session.next_session_goal = proposed_goal  # may be None to clear

        # ── 7. Persist messages ───────────────────────────────────────────────
        if therapy_session:
            db.session.add(ChatMessage(session_id=session_id, role="user",      content=user_message))
            db.session.add(ChatMessage(session_id=session_id, role="assistant", content=reply))
            db.session.commit()

        # ── 8. Sync safety net: if reply contains hotline info, fire the popup
        if safety_mode != "CRISIS" and _HOTLINE_KEYWORDS.search(reply):
            current_app.logger.warning(
                "HOTLINE_SYNC user=%s session=%s — AI included hotline text; upgrading safetyMode to CRISIS",
                current_user.id, session_id,
            )
            safety_mode = "CRISIS"

        return jsonify({
            "reply":        reply,
            "safetyMode":   safety_mode,
            "proposedGoal": proposed_goal,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
