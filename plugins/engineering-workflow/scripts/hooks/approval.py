"""Decide whether the latest user message requests commit, push, or PR creation.

Recognize direct requests in Korean and English. Incidental mentions and
instructions quoted as examples do not grant approval.
"""

import re

ACTIONS = ("commit", "push", "pr")

NEGATION = re.compile(
    r"하지\s*(?:마|말)|하지\s*$|말고|말아|않|아직|안\s*해|안\s*하|보류|나중|전에|하기\s*전|"
    r"\bdon['’]?t\b|\bdo\s+not\b|\bnot\b|\bnever\b|\bwithout\b|\bbefore\b|\bhold\s+off\b|"
    r"\bskip\b|\blater\b|\bavoid\b",
    re.IGNORECASE,
)

CLAUSE_SPLIT = re.compile(
    r"[.!\n;]+|하고\s*|(?<=말고)\s*|그리고|그런데|하지만|그러나|\s+then\s+|\s+but\s+|\s+however\s+",
    re.IGNORECASE,
)
JOINED_REQUESTS = re.compile(r",|(?<!go ahead)\s+and\s+", re.IGNORECASE)
QUOTED_EXAMPLE = re.compile(r'\x60[^\x60]*\x60|"[^"]*"|“[^”]*”|(?<!\w)‘[^’]*’')
ACTION_MENTIONS = {
    "commit": re.compile(r"\bcommit\b|커밋|컴밋|올려", re.IGNORECASE),
    "push": re.compile(r"\bpush\b|푸시|푸쉬|올려", re.IGNORECASE),
    "pr": re.compile(r"\b(?:pr|mr|pull[ -]request|merge[ -]request)\b|풀\s?리퀘|머지\s?리퀘|피알", re.IGNORECASE),
}
ENGLISH_REQUEST = re.compile(
    r"(?:please\s+|go ahead and\s+)?(?:git\s+)?(?P<action>commit|push)"
    r"(?:\s+(?:it|this|that|them|everything|(?:all |the |these |this )?changes?))?"
    r"(?:\s+(?:now|again|please))?", re.IGNORECASE,
)
ENGLISH_PR = re.compile(
    r"(?:please\s+)?(?:open|create|make|submit|raise|file)\s+(?:(?:a|an|a new|new)\s+)?"
    r"(?:pr|mr|pull[ -]request|merge[ -]request)(?:\s+(?:now|please))?", re.IGNORECASE,
)
KOREAN_GIT = re.compile(
    r"(?:(?:이거|이걸|변경\s*사항(?:을)?|수정\s*사항(?:을)?)\s*)?"
    r"(?P<actions>(?:(?:커밋|컴밋|푸시|푸쉬)(?:\s*(?:이랑|와|과|및))?\s*)+)"
    r"(?:(?:좀\s*)?(?:진행\s*)?(?:해(?:\s*(?:줘|주세요|주시겠어요|요))?|"
    r"하도록(?:\s*해)?|하세요|하자|부탁(?:해|합니다)?))?"
)
KOREAN_PR = re.compile(
    r"(?:pr|mr|풀\s?리퀘(?:스트)?|머지\s?리퀘(?:스트)?|피알)(?:을|를)?\s*"
    r"(?:만들어|생성해|열어|띄워)(?:\s*(?:줘|주세요|요))?", re.IGNORECASE,
)
KOREAN_UPLOAD = re.compile(r"(?:이거\s*)?올려\s*(?:줘|주세요|요)")


def approved_actions(message):
    """Return the set of actions the message requests."""
    approved = set()
    denied = set()
    if not isinstance(message, str):
        return approved
    for clause in CLAUSE_SPLIT.split(QUOTED_EXAMPLE.sub(" ", message)):
        if NEGATION.search(clause):
            denied.update(action for action, pattern in ACTION_MENTIONS.items() if pattern.search(clause))
            continue
        for request in JOINED_REQUESTS.split(clause):
            request = request.strip().rstrip("~").strip()
            english = ENGLISH_REQUEST.fullmatch(request)
            korean = KOREAN_GIT.fullmatch(request)
            if english:
                approved.add(english["action"].lower())
            elif korean:
                if re.search(r"커밋|컴밋", korean["actions"]):
                    approved.add("commit")
                if re.search(r"푸시|푸쉬", korean["actions"]):
                    approved.add("push")
            elif KOREAN_UPLOAD.fullmatch(request):
                approved.update(("commit", "push"))
            elif ENGLISH_PR.fullmatch(request) or KOREAN_PR.fullmatch(request):
                approved.add("pr")
            else:
                break
    return approved - denied


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
