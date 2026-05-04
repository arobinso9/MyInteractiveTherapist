RISK_TRIAGE_PROMPT = """You are the Safety Triage Layer for a mental health app.

Your task is to analyze the USER'S message and classify it into one of two risk levels:

- CLEAR_IMMEDIATE_RISK (credible, current, life-threatening danger)
- POSSIBLE_HARM (concerning but not clearly imminent risk)

You do not provide therapy.
You do not respond to the user.
You only classify risk based on evidence.

--------------------------------------------------
CORE RULES
--------------------------------------------------

1. Do NOT escalate based on emotional intensity alone.
2. Do NOT treat jokes, sarcasm, slang, or exaggeration as real danger without supporting evidence.
3. CLEAR_IMMEDIATE_RISK requires credible, literal, current, actionable danger.
4. When evidence is ambiguous or incomplete, use POSSIBLE_HARM.
5. Missing a real emergency is worse than over-flagging, but do not infer danger without evidence.

--------------------------------------------------
LEVEL 1: CLEAR_IMMEDIATE_RISK
--------------------------------------------------

Use ONLY when there is strong evidence of real, current danger, such as:

- explicit intent to die or seriously self-harm
- explicit intent to seriously harm another person
- plan, method, or preparation
- access to means (gun, pills, knife, etc.)
- timing or imminence ("tonight", "right now", "after this")
- inability to stay safe ("I can't stop myself", "I can't stay safe")
- active attempt, overdose, or ongoing emergency
- immediate violent threat with actionable details
- acute psychotic or medical state causing immediate danger

Examples:
- "I am going to kill myself tonight"
- "I already took the pills"
- "I have the gun and I'm ready"
- "I can't keep myself safe right now"

--------------------------------------------------
LEVEL 2: POSSIBLE_HARM
--------------------------------------------------

Use when the message is concerning but lacks clear evidence of imminent danger:

- passive suicidal thoughts ("I wish I wasn't here")
- vague or ambiguous self-harm language
- self-harm urges without stated intent to act now
- repeated dark jokes about suicide or violence
- hopelessness or escalating distress
- violent thoughts without plan or target
- ambiguous statements that could be serious
- deterioration that should be monitored

Examples:
- "Maybe everyone would be better off without me"
- "I want to cut"
- "lol I'm gonna kill myself if that happens"
- "I could murder him"

--------------------------------------------------
NON-LITERAL LANGUAGE FILTER
--------------------------------------------------

Do NOT classify as CLEAR_IMMEDIATE_RISK based only on common non-literal expressions:

- "I'm dead"
- "this is killing me"
- "my mom is going to kill me"
- "I died of embarrassment"
- "brb jumping off a cliff lol"

If no real-world intent indicators exist, classify as POSSIBLE_HARM or lower.

--------------------------------------------------
ESCALATION LOGIC
--------------------------------------------------

CLEAR_IMMEDIATE_RISK typically requires:
- explicit intent
AND at least one of:
  - plan
  - means
  - timing/immediacy
  - preparation
  - inability to stay safe
  - active attempt/emergency

Do NOT escalate based on repetition alone without stronger evidence.

--------------------------------------------------
OUTPUT FORMAT (STRICT)
--------------------------------------------------

Return exactly:

RISK_LEVEL: CLEAR_IMMEDIATE_RISK | POSSIBLE_HARM

CONFIDENCE: LOW | MEDIUM | HIGH

EVIDENCE_FOR_CLASSIFICATION:
- short bullet(s) quoting or closely paraphrasing key phrases
- if none, write "None"

EVIDENCE_AGAINST_IMMEDIATE_RISK:
- short bullet(s) such as:
  "No plan stated"
  "No means mentioned"
  "No timing/immediacy"
  "Appears joking or hyperbolic"
- if not applicable, write "None"

RECOMMENDED_SYSTEM_ACTION:
- IMMEDIATE_EMERGENCY_ACTION   (for CLEAR_IMMEDIATE_RISK)
- FLAG_AND_WARN                (for POSSIBLE_HARM, moderate concern)
- FLAG_AND_MONITOR             (for POSSIBLE_HARM, low concern)
- FLAG_FOR_HUMAN_REVIEW        (for ambiguous/high POSSIBLE_HARM)

RATIONALE:
- 1-2 concise sentences explaining the decision based on evidence only

Be precise, conservative, and clinically cautious.
When uncertain, prefer the safer interpretation."""


def _parse_triage(raw: str) -> dict:
    result = {
        "risk_level":             None,
        "confidence":             "LOW",
        "evidence_for":           [],
        "evidence_against":       [],
        "recommended_action":     "FLAG_AND_MONITOR",
        "rationale":              "",
    }

    lines      = raw.split("\n")
    current_section = None

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("RISK_LEVEL:"):
            val = stripped.replace("RISK_LEVEL:", "").strip()
            if val in ("CLEAR_IMMEDIATE_RISK", "POSSIBLE_HARM"):
                result["risk_level"] = val

        elif stripped.startswith("CONFIDENCE:"):
            val = stripped.replace("CONFIDENCE:", "").strip()
            if val in ("LOW", "MEDIUM", "HIGH"):
                result["confidence"] = val

        elif stripped.startswith("EVIDENCE_FOR_CLASSIFICATION:"):
            current_section = "evidence_for"

        elif stripped.startswith("EVIDENCE_AGAINST_IMMEDIATE_RISK:"):
            current_section = "evidence_against"

        elif stripped.startswith("RECOMMENDED_SYSTEM_ACTION:"):
            current_section = "action"
            val = stripped.replace("RECOMMENDED_SYSTEM_ACTION:", "").strip()
            if val:
                result["recommended_action"] = val

        elif stripped.startswith("RATIONALE:"):
            current_section = "rationale"

        elif stripped.startswith("-") and stripped not in ("- None", "-None", "- none"):
            bullet = stripped.lstrip("- ").strip()
            if current_section == "evidence_for":
                result["evidence_for"].append(bullet)
            elif current_section == "evidence_against":
                result["evidence_against"].append(bullet)
            elif current_section == "action":
                result["recommended_action"] = bullet

        elif current_section == "rationale" and stripped:
            result["rationale"] += (" " + stripped) if result["rationale"] else stripped

    return result


def triage_message(client, message: str) -> dict:
    """
    Classifies a user message for risk level.
    Returns parsed triage dict. Fails safe to POSSIBLE_HARM on error.
    """
    try:
        res = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": RISK_TRIAGE_PROMPT},
                {"role": "user",   "content": f"USER MESSAGE:\n{message}"}
            ],
            max_tokens=400,
            temperature=0.1
        )
        return _parse_triage(res.choices[0].message.content)
    except Exception:
        # Fail safe — treat as possible harm so the conversation continues
        # but the flag is still raised
        return {
            "risk_level":         "POSSIBLE_HARM",
            "confidence":         "LOW",
            "evidence_for":       ["Triage model unavailable — flagged for safety"],
            "evidence_against":   [],
            "recommended_action": "FLAG_AND_MONITOR",
            "rationale":          "Triage API call failed; defaulting to POSSIBLE_HARM.",
        }
