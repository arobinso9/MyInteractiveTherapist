SAFETY_REVIEW_PROMPT = """You are the safety screen for an AI therapy app. Your job is narrow: catch only genuinely harmful replies.

DEFAULT TO APPROVE. The therapist's draft is almost always fine. Do NOT flag for tone, style, length, warmth level, verbosity, or stylistic preferences. Therapy involves sitting with hard feelings — that is not unsafe.

Only flag when one of these two things is true:

1. THE REPLY GIVES HARMFUL ADVICE
   - Encourages or normalizes self-harm, suicide, violence, eating disorders, substance misuse, or illegal acts
   - Tells the client to stop/start/change prescribed medication without a clinician
   - Tells the client to confront an abuser, stalker, or dangerous person without safety caution
   - Gives a clinical diagnosis as fact (e.g., "You have BPD")
   - Claims to be a licensed clinician or emergency service

2. THE REPLY IGNORES SOMETHING SERIOUS THE CLIENT JUST SAID
   - Client mentions suicidal thoughts, self-harm, abuse, plans to hurt themselves or others — and the reply changes the subject, minimizes it, or fails to address it
   - Client signals imminent danger and the reply doesn't redirect to safety or crisis resources

Anything else — including exploratory questions, sitting with discomfort, gentle pushback, emotional language, not being upbeat enough — is FINE. APPROVE it.

VERDICTS:
- APPROVE: the reply is safe enough. Use this for nearly everything.
- REVISE: the reply has a real safety issue (#1 or #2 above) but can be fixed by editing. Provide the edited version.
- BLOCK: the reply is fundamentally unsafe — must not be sent at all.

When REVISING, change as little as possible. Preserve the therapist's voice, warmth, and the conversation's flow. Only fix the specific safety issue.

OUTPUT FORMAT (exact):

VERDICT: APPROVE | REVISE | BLOCK

SAFETY_ISSUES:
- concise bullet(s), or "None"

SAFE_RESPONSE:
[required only on REVISE — leave blank on APPROVE or BLOCK]

RATIONALE:
- one sentence why"""


def _parse(raw: str, fallback: str) -> dict:
    verdict       = "APPROVE"
    safe_response = fallback
    issues        = []

    lines = raw.split("\n")

    # VERDICT
    for line in lines:
        if line.startswith("VERDICT:"):
            v = line.replace("VERDICT:", "").strip()
            if v in ("APPROVE", "REVISE", "BLOCK"):
                verdict = v
            break

    # SAFETY_ISSUES
    in_issues = False
    for line in lines:
        if line.startswith("SAFETY_ISSUES:"):
            in_issues = True
            continue
        if in_issues:
            if line.startswith("SAFE_RESPONSE:") or line.startswith("RATIONALE:"):
                break
            if line.strip().startswith("-") and line.strip() != "- None" and line.strip() != "-None":
                issues.append(line.strip().lstrip("- ").strip())

    # SAFE_RESPONSE — everything between SAFE_RESPONSE: and RATIONALE:
    in_response    = False
    response_lines = []
    for line in lines:
        if line.startswith("SAFE_RESPONSE:"):
            in_response = True
            rest = line.replace("SAFE_RESPONSE:", "").strip()
            if rest:
                response_lines.append(rest)
            continue
        if in_response:
            if line.startswith("RATIONALE:"):
                break
            response_lines.append(line)

    if response_lines:
        safe_response = "\n".join(response_lines).strip()

    return {"verdict": verdict, "safe_response": safe_response, "issues": issues}


def review_reply(client, draft: str, user_message: str) -> dict:
    """
    Runs the safety review layer on a therapist draft.
    Returns {"verdict": str, "safe_response": str, "issues": list}
    Fails open on error — returns APPROVE with the original draft so chat is never broken.
    """
    try:
        res = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": SAFETY_REVIEW_PROMPT},
                {"role": "user",   "content": f"USER MESSAGE:\n{user_message}\n\nDRAFTED REPLY:\n{draft}"}
            ],
            max_tokens=700,
            temperature=0.1
        )
        return _parse(res.choices[0].message.content, draft)
    except Exception:
        return {"verdict": "APPROVE", "safe_response": draft, "issues": []}
