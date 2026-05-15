CLASSIFIER_PROMPT = """You classify how a therapy client responded to the therapist's opening question about their prior-session goal.

The therapist's opening message asked the client whether they want to talk about how their prior goal went OR jump into something else.

Output EXACTLY one word:
- "engaged" — the client opened the door to discussing the prior goal. Examples: "yeah sure", "ok let's talk about it", "i did it but it was hard", "i forgot", "it was rough", any reply that engages with the goal topic.
- "redirected" — the client declined the goal topic or changed subject. Examples: "let's talk about something else", "nothing about that", "idk", "wtvr", "i had a hard week", "actually work was crazy", any reply that brings up a new topic instead of the goal.

If the reply is genuinely ambiguous, default to "engaged" (do not assume deflection)."""


def classify_goal_engagement(client, user_reply: str) -> str | None:
    """
    Classifies whether the client engaged with or redirected away from the prior-goal discussion.
    Returns 'engaged' or 'redirected', or None on failure.
    """
    try:
        res = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": CLASSIFIER_PROMPT},
                {"role": "user",   "content": f"CLIENT REPLY:\n{user_reply}"}
            ],
            max_tokens=5,
            temperature=0,
        )
        out = (res.choices[0].message.content or "").strip().lower()
        if "redirect" in out:
            return "redirected"
        if "engage" in out:
            return "engaged"
        return None
    except Exception:
        return None
