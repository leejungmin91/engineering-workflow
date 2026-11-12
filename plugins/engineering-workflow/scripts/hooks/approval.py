"""Decide whether the latest user message requests commit, push, or PR creation.

The message is split into clauses. An action is approved when some clause names it,
carries no negation or deferral, and either reads as a request or consists of the
action words alone. Korean and English are covered.
"""

import re

ACTIONS = ("commit", "push", "pr")

ACTION_WORDS = {
    "commit": re.compile(r"커밋|컴밋|commit", re.IGNORECASE),
    "push": re.compile(r"푸시|푸쉬|push", re.IGNORECASE),
    "pr": re.compile(
        r"\bpr\b|\bprs\b|pull[ -]?requests?|풀\s?리퀘(?:스트)?|merge[ -]?requests?|\bmr\b|"
        r"머지\s?리퀘(?:스트)?|피알",
        re.IGNORECASE,
    ),
}
# "올려 줘" (upload it) means commit and push together.
UPLOAD = re.compile(r"올려|올리")

NEGATION = re.compile(
    r"하지\s*(?:마|말)|하지\s*$|말고|말아|않|아직|안\s*해|안\s*하|보류|나중|전에|하기\s*전|"
    r"\bdon'?t\b|\bdo\s+not\b|\bnot\b|\bnever\b|\bwithout\b|\bbefore\b|\bhold\s+off\b|"
    r"\bskip\b|\blater\b|\bavoid\b",
    re.IGNORECASE,
)

REQUEST_MARKER = re.compile(
    r"해(?:\s*(?:줘|주세요|주시|라|요|야|도|서))?|하(?:자|도록|세요|시고|시오|라|고)|진행|부탁|"
    r"하기|할게|할래|하면|해도|하는|줘|주세요|주시|만들|생성|열어|열고|보내|띄워|넣어|반영|"
    r"\bplease\b|\bcreate\b|\bopen\b|\bmake\b|\bsubmit\b|\bsend\b|\braise\b|\bfile\b|"
    r"\bgo\s+ahead\b|\bit\b|\bthis\b|\bthat\b|\bthe\b|"
    r"\bthese\b|\bthose\b|\bthem\b|\bnow\b|\ball\b|\beverything\b|\bchanges?\b|\bup\b|\bagain\b",
    re.IGNORECASE,
)

CLAUSE_SPLIT = re.compile(
    r"[.!?\n,;:]+|하고\s*|말고\s*|그리고|그런데|하지만|그러나|\s+and\s+|\s+then\s+|\s+but\s+|\s+however\s+",
    re.IGNORECASE,
)
FILLER = re.compile(r"[\s\W_]+|좀|도|만|이랑|와|과|및|하고|and|also|both", re.IGNORECASE)


def clauses(message):
    return [part.strip() for part in CLAUSE_SPLIT.split(message) if part and part.strip()]


def _only_action_words(clause):
    stripped = clause
    for pattern in ACTION_WORDS.values():
        stripped = pattern.sub(" ", stripped)
    stripped = UPLOAD.sub(" ", stripped)
    stripped = FILLER.sub("", stripped)
    return stripped == ""


def _ends_with_action(clause):
    tail = clause.rstrip(" .!?~")
    for pattern in ACTION_WORDS.values():
        for match in pattern.finditer(tail):
            if match.end() == len(tail):
                return True
    return False


def approved_actions(message):
    """Return the set of actions the message requests."""
    approved = set()
    if not isinstance(message, str):
        return approved
    for clause in clauses(message):
        present = {name for name, pattern in ACTION_WORDS.items() if pattern.search(clause)}
        upload = bool(UPLOAD.search(clause))
        if upload:
            present.update({"commit", "push"})
        if not present:
            continue
        if NEGATION.search(clause):
            continue
        if REQUEST_MARKER.search(clause) or _only_action_words(clause) or _ends_with_action(clause) or upload:
            approved.update(present)
    return approved


GO_AHEAD = re.compile(
    r"진행|실행|해\s*줘|하세요|해도|괜찮|좋아|\bgo\s+ahead\b|\bproceed\b|\byes\b|\bdo\s+it\b|\bok\b",
    re.IGNORECASE,
)


def confirms(message, keywords):
    """Codex replacement for "ask": the same-turn message approves a named operation.

    keywords are lower-case words that name the operation (e.g. {"stash", "drop"}).
    The message must contain every keyword, a go-ahead expression, and no negation.
    """
    if not isinstance(message, str):
        return False
    lowered = message.lower()
    if not all(word in lowered for word in keywords):
        return False
    if NEGATION.search(message):
        return False
    return bool(GO_AHEAD.search(message))
