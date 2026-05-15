from models import TherapySession


def detect_goal_pattern(user_id: int, exclude_session_id: int) -> dict | None:
    """
    Looks at the 3 most recent completed sessions (excluding the given one).
    A session counts as a 'goal failure' if ANY of:
      - it ended without setting a next-session goal
      - the client reported they didn't / skipped the prior goal
      - the client redirected away from discussing the prior goal in chat

    Returns None if fewer than 3 prior completed sessions, or if any of those 3
    did NOT show a goal failure. Otherwise returns:
        {"breakdown": "- Session 1: ...\n- Session 2: ...\n- Session 3: ..."}
    (sessions ordered oldest → newest)
    """
    # After a pattern alert fires, the counter resets: only sessions started AFTER the
    # most recent pattern_raised session count toward the next pattern.
    last_raised = TherapySession.query.filter(
        TherapySession.user_id == user_id,
        TherapySession.pattern_raised == True,
    ).order_by(TherapySession.started_at.desc()).first()

    query = TherapySession.query.filter(
        TherapySession.user_id == user_id,
        TherapySession.completed_at.isnot(None),
        TherapySession.id != exclude_session_id,
    )
    if last_raised:
        query = query.filter(TherapySession.started_at > last_raised.started_at)

    last_three = query.order_by(TherapySession.started_at.desc()).limit(3).all()

    def _has_goal_failure(s):
        return (
            s.next_session_goal is None
            or s.prior_goal_followthrough in ("no", "skipped")
            or s.prior_goal_engagement == "redirected"
        )

    if len(last_three) != 3 or not all(_has_goal_failure(s) for s in last_three):
        return None

    rows = []
    for i, s in enumerate(reversed(last_three), start=1):  # oldest → newest
        bits = []
        if s.next_session_goal is None:
            bits.append("ended without setting a goal")
        if s.prior_goal_followthrough in ("no", "skipped"):
            bits.append(f"started by saying they {s.prior_goal_followthrough} the prior goal")
        if s.prior_goal_engagement == "redirected":
            bits.append("redirected away from the goal discussion")
        rows.append(f"- Session {i}: {'; '.join(bits) or 'goal disengagement'}")

    return {"breakdown": "\n".join(rows)}
