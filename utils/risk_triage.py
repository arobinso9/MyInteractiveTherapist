RISK_TRIAGE_PROMPT = """You screen user messages in a therapy app for safety risk. Most messages are NOT a safety risk — therapy involves people venting, feeling sad, talking about hard stuff. That is normal, not a risk.

Classify into ONE of three levels:

- NO_RISK: Default. The message contains no real safety concern. Examples: "hi", "I'm sad", "work has been awful", "I'm angry at my mom", "I feel hopeless about my job", "tell me about CBT". Sadness, anger, frustration, stress, and emotional intensity by themselves are NOT a safety risk.

- POSSIBLE_HARM: Concerning content without a direct, literal statement of suicidal/violent intent. Examples: "I wish I didn't exist", "Maybe everyone would be better off without me", "I want to cut", "I keep thinking about dying", "I want to hurt myself". Passive ideation, self-harm urges, ambiguous violent thoughts.

- CLEAR_IMMEDIATE_RISK: A literal, direct statement of suicidal or homicidal intent, OR concerning content paired with imminence/plan/means/inability to stay safe.
  Direct statements that fall here ON THEIR OWN (no modifier needed):
    - "I want to kill myself"
    - "I want to die"
    - "I'm going to kill myself"
    - "I'm going to end my life"
    - "I want to commit suicide"
    - "I want to kill [someone]"
  Also CLEAR_IMMEDIATE_RISK when any concerning statement is paired with:
    - timing/imminence ("tonight", "today", "right now")
    - a plan or method
    - access to means (gun, pills, rope, knife)
    - an active attempt or overdose
    - inability to stay safe ("I can't stop myself")

RULES:
1. Default to NO_RISK. Only escalate if there's actual concerning content.
2. Do NOT treat normal emotional language as a safety risk. Sadness ≠ suicidal. Anger ≠ violent.
3. Hyperbole filter: phrases like "this is killing me", "my mom will murder me", "I'm dead", "lol I'm gonna jump off a cliff", "ugh I want to die from this meeting" are NOT risk — these are non-literal expressions of frustration. Look for surrounding context indicating the statement is hyperbolic (laughing, joking, exaggerating about a mundane event). When the statement is sincere and direct, it IS a risk regardless of how short the message is.
4. A direct first-person statement of wanting to die or kill yourself/someone IS CLEAR_IMMEDIATE_RISK on its own. Do not downgrade it to POSSIBLE_HARM just because no plan or timing is mentioned.
5. When the message has zero risk indicators and is not hyperbolic, ALWAYS pick NO_RISK.

OUTPUT FORMAT (exact):

RISK_LEVEL: NO_RISK | POSSIBLE_HARM | CLEAR_IMMEDIATE_RISK

CONFIDENCE: LOW | MEDIUM | HIGH

EVIDENCE_FOR_CLASSIFICATION:
- bullet(s) quoting key phrases, or "None"

EVIDENCE_AGAINST_IMMEDIATE_RISK:
- bullet(s) such as "No plan", "No means", "No timing", "Appears hyperbolic", or "None"

RECOMMENDED_SYSTEM_ACTION:
- NO_ACTION                    (for NO_RISK)
- FLAG_AND_MONITOR             (for POSSIBLE_HARM, low concern)
- FLAG_AND_WARN                (for POSSIBLE_HARM, moderate concern)
- FLAG_FOR_HUMAN_REVIEW        (for ambiguous/high POSSIBLE_HARM)
- IMMEDIATE_EMERGENCY_ACTION   (for CLEAR_IMMEDIATE_RISK)

RATIONALE:
- 1 sentence based on evidence"""


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
            if val in ("NO_RISK", "CLEAR_IMMEDIATE_RISK", "POSSIBLE_HARM"):
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
