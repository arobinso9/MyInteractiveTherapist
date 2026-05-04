# TODO: Replace with dedicated safety AI scanner — current keyword matching is a placeholder
CRISIS_PHRASES = {
    "CRITICAL": ["kill myself", "end my life", "want to die", "suicide", "i have a plan", "going to hurt myself"],
    "MEDIUM":   ["hurt myself", "self harm", "cutting", "don't want to be here", "wish i was dead"],
    "LOW":      ["hopeless", "can't go on", "no point", "give up"],
}


def detect_crisis(text: str):
    lower = text.lower()
    for severity, phrases in CRISIS_PHRASES.items():
        if any(p in lower for p in phrases):
            return severity, next(p for p in phrases if p in lower)
    return None, None
