import logging
from datetime import datetime, timezone, timedelta
from models import db, UserRiskState, SafetyAlert

log = logging.getLogger(__name__)

WARNING_TEXT = (
    "I want to gently pause here. Please try not to use unclear or joking language about "
    "suicide, self-harm, or violence — even if you don't mean it literally. If something "
    "serious is going on, I want to make sure I understand. Are you safe right now?"
)

# Hardcoded — never model-generated (issue #3)
CRISIS_RESPONSE = (
    "I'm very concerned about what you've shared. Please reach out for immediate support right now.\n\n"
    "• Call or text 988 (Suicide & Crisis Lifeline — US)\n"
    "• Text HOME to 741741 (Crisis Text Line)\n"
    "• Call 911 or go to your nearest emergency room\n\n"
    "You don't have to face this alone. Please contact one of these resources now."
)

VALID_RISK_LEVELS      = {"CLEAR_IMMEDIATE_RISK", "POSSIBLE_HARM"}
VALID_ACTIONS          = {
    "IMMEDIATE_EMERGENCY_ACTION",
    "FLAG_AND_WARN",
    "FLAG_AND_MONITOR",
    "FLAG_FOR_HUMAN_REVIEW",
}
SAFE_ACTIONS           = {"FLAG_AND_MONITOR", "FLAG_AND_WARN", "FLAG_FOR_HUMAN_REVIEW"}

# ── Trend scoring ──────────────────────────────────────────────────────────────
_TREND_PROGRESSION = {"NONE": "MILD", "MILD": "MODERATE", "MODERATE": "SEVERE", "SEVERE": "SEVERE"}
_TREND_DECAY       = {"SEVERE": "MODERATE", "MODERATE": "MILD", "MILD": "NONE", "NONE": "NONE"}

# Keywords that suggest a signal is meaningful even at LOW confidence
_ESCALATION_KEYWORDS = {
    # repetition / persistence
    "again", "still", "keep", "always", "every time",
    # means
    "gun", "knife", "pills", "rope", "blade", "weapon", "overdose",
    # timing / immediacy
    "tonight", "today", "right now", "soon", "ready",
    # intent specificity
    "plan", "decided", "going to", "will do", "i will",
}


def _advance_trend(state: "UserRiskState") -> str:
    current = state.trend or "NONE"
    return _TREND_PROGRESSION.get(current, "MILD")


def _decay_trend(state: "UserRiskState") -> str:
    current = state.trend or "NONE"
    return _TREND_DECAY.get(current, "NONE")


def _is_meaningful_signal(triage: dict) -> bool:
    """
    True if this POSSIBLE_HARM event is strong enough to advance the trend.
    HIGH/MEDIUM confidence always advances.
    LOW confidence only advances if escalation keywords appear in the evidence.
    """
    if triage.get("confidence") in ("HIGH", "MEDIUM"):
        return True
    evidence = " ".join(triage.get("evidence_for", [])).lower()
    return any(kw in evidence for kw in _ESCALATION_KEYWORDS)


# ── Risk state helpers ─────────────────────────────────────────────────────────
def _get_or_create_risk_state(user_id: int) -> UserRiskState:
    state = UserRiskState.query.filter_by(user_id=user_id).first()
    if not state:
        state = UserRiskState(user_id=user_id)
        db.session.add(state)
        db.session.flush()
    return state


def _decay_counts(state: UserRiskState):
    """Reset 24h counter if more than 24 hours have passed since last update."""
    if state.updated_at:
        now  = datetime.now(timezone.utc)
        last = state.updated_at if state.updated_at.tzinfo else state.updated_at.replace(tzinfo=timezone.utc)
        if now - last > timedelta(hours=24):
            state.possible_harm_count_24h = 0


def _warning_throttled(state: UserRiskState) -> bool:
    """True if a warning was shown in the last 10 minutes."""
    if not state.last_warning_at:
        return False
    now  = datetime.now(timezone.utc)
    last = state.last_warning_at if state.last_warning_at.tzinfo else state.last_warning_at.replace(tzinfo=timezone.utc)
    return (now - last) < timedelta(minutes=10)


# ── Notification stubs (issue #8 — idempotent) ────────────────────────────────
def _notify_emergency_contact(user, alert: SafetyAlert, state: UserRiskState):
    """
    Dispatch emergency alert to guardian via SMS + email.
    Idempotent — skips if emergency_protocol_activated is already set.
    """
    if state.emergency_protocol_activated:
        return

    if not getattr(user, "guardian", None):
        log.info("_notify_emergency_contact skipped user=%s — no guardian", user.id)
        return

    if alert is None:
        log.warning("_notify_emergency_contact called with no alert user=%s", user.id)
        return

    try:
        from services.emergency_alerts import trigger_emergency_alert
        trigger_emergency_alert(user, alert, alert.session_id)
        log.info("_notify_emergency_contact dispatched user=%s alert=%s", user.id, alert.id)
    except Exception as exc:
        log.error("_notify_emergency_contact failed user=%s: %s", user.id, exc)


# ── Policy engine ──────────────────────────────────────────────────────────────
def run_policy(user, triage: dict, session_id) -> dict:
    """
    Deterministic policy engine.
    ALWAYS returns a dict with safety_mode in {NORMAL, HEIGHTENED, CRISIS}.
    """

    # ── Input validation (issue #2) ────────────────────────────────────────────
    risk_level = triage.get("risk_level")
    action     = triage.get("recommended_action") or triage.get("recommended_system_action", "")
    confidence = triage.get("confidence", "LOW")

    if risk_level not in VALID_RISK_LEVELS:
        risk_level = "POSSIBLE_HARM"

    if action not in VALID_ACTIONS:
        action = "FLAG_FOR_HUMAN_REVIEW"

    evidence = "; ".join(triage.get("evidence_for", [])) or "flagged by triage"

    # ── Confidence downgrade rule (subtle improvement) ─────────────────────────
    # LOW confidence on CLEAR_IMMEDIATE_RISK → still CRISIS (safety first),
    # but LOW confidence on POSSIBLE_HARM → HEIGHTENED (already the case).
    # Ensures no message with low-confidence concern falls through as NORMAL.

    state = _get_or_create_risk_state(user.id)
    _decay_counts(state)

    # ── Log SafetyAlert for every non-normal event ─────────────────────────────
    alert = None
    if risk_level in VALID_RISK_LEVELS:
        severity = "CRITICAL" if risk_level == "CLEAR_IMMEDIATE_RISK" else "MEDIUM"
        alert = SafetyAlert(
            user_id=user.id,
            session_id=session_id,
            trigger_phrase=evidence[:500],
            severity_level=severity,
            action_taken=action,
        )
        db.session.add(alert)
        db.session.flush()   # get alert.id before commit

    # ── Route A: immediate danger ──────────────────────────────────────────────
    if risk_level == "CLEAR_IMMEDIATE_RISK":
        state.last_risk_level = risk_level
        state.trend           = "SEVERE"   # always max on confirmed crisis
        if alert:
            alert.notified_at = datetime.now(timezone.utc)
        _notify_emergency_contact(user, alert, state)  # idempotent
        state.emergency_protocol_activated = True
        db.session.commit()
        return {
            "safety_mode":     "CRISIS",
            "show_warning":    False,
            "warning_text":    None,
            "block_therapy":   True,
            "crisis_response": CRISIS_RESPONSE,
            "alert_id":        alert.id if alert else None,
        }

    # ── POSSIBLE_HARM — update counters + trend (issue #7) ────────────────────
    state.possible_harm_count_24h += 1
    state.possible_harm_count_7d  += 1
    state.last_risk_level          = risk_level
    # Only advance trend on meaningful signals; decay on low-confidence noise
    state.trend = _advance_trend(state) if _is_meaningful_signal(triage) else _decay_trend(state)

    show_warning = False

    # Route B: first-time / low-severity — monitor only, do not clear prior queue
    if state.possible_harm_count_24h == 1 and state.trend == "NONE":
        pass   # just log, no warning, no queue change

    # Route C: repeated possible harm
    elif state.possible_harm_count_24h >= 2:
        if not _warning_throttled(state):
            show_warning              = True
            state.prior_warning_shown = True
            state.last_warning_at     = datetime.now(timezone.utc)
        if state.possible_harm_count_24h >= 4:
            state.human_review_queued = True

    # Route D: escalating trend
    if state.trend in ("MODERATE", "SEVERE"):
        state.human_review_queued = True
        if not _warning_throttled(state):
            show_warning              = True
            state.prior_warning_shown = True
            state.last_warning_at     = datetime.now(timezone.utc)

    # Route E: threshold crossed mid-session (issue #8 — idempotent)
    if action == "IMMEDIATE_EMERGENCY_ACTION":
        if alert:
            alert.severity_level = "CRITICAL"
            alert.notified_at    = datetime.now(timezone.utc)
        _notify_emergency_contact(user, alert, state)  # idempotent
        state.emergency_protocol_activated = True
        db.session.commit()
        return {
            "safety_mode":     "CRISIS",
            "show_warning":    False,
            "warning_text":    None,
            "block_therapy":   True,
            "crisis_response": CRISIS_RESPONSE,
            "alert_id":        alert.id if alert else None,
        }

    db.session.commit()

    # issue #9 — explicit HEIGHTENED return, always present
    return {
        "safety_mode":     "HEIGHTENED",
        "show_warning":    show_warning,
        "warning_text":    WARNING_TEXT if show_warning else None,
        "block_therapy":   False,
        "crisis_response": None,
        "alert_id":        alert.id if alert else None,
    }
