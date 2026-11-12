"""Secret detection shared by the Git guard and (later) the file-edit guard.

Only the kind of secret is ever reported, never the value.
"""

import re

# (kind, pattern). Group 1, when present, is the candidate value to screen for placeholders.
PATTERNS = [
    ("bearer token", re.compile(r"(?i)\bbearer\s+([A-Za-z0-9\-._~+/]{20,}=*)")),
    ("GitHub token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b")),
    ("GitLab token", re.compile(r"\b(glpat-[A-Za-z0-9\-_]{20,})")),
    ("sk- API key", re.compile(r"\b(sk-[A-Za-z0-9\-_]{20,})")),
    ("Slack token", re.compile(r"\b(xox[abprs]-[A-Za-z0-9-]{10,})")),
    ("AWS access key", re.compile(r"\b(AKIA[0-9A-Z]{16})\b")),
    ("JWT", re.compile(r"\b(eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})")),
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY")),
    (
        "quoted credential",
        re.compile(
            r"(?i)\b(?:password|passwd|pwd|secret|api[_-]?key|apikey|access[_-]?token|"
            r"auth[_-]?token|client[_-]?secret|private[_-]?key)\w*\s*[:=]\s*[\"']([^\"']{8,})[\"']"
        ),
    ),
    (
        "unquoted credential assignment",
        re.compile(
            r"(?im)^\s*(?:export\s+|set\s+|\$env:)?[A-Za-z0-9_]*"
            r"(?:PASSWORD|PASSWD|SECRET|TOKEN|API_KEY|APIKEY)[A-Za-z0-9_]*\s*=\s*([^\s\"'#]{8,})\s*$"
        ),
    ),
]

PLACEHOLDER = re.compile(
    r"(?i)^(?:\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|%[A-Za-z_][A-Za-z0-9_]*%|<[^>]+>|\*{3,}|x{4,}|"
    r"example[\w-]*|dummy[\w-]*|change[-_ ]?me|placeholder[\w-]*|test[\w-]*|sample[\w-]*|your[\w-]*|"
    r"none|null|nil|redacted|todo|tbd|fixme|fake[\w-]*|mock[\w-]*|insert[\w-]*|replace[\w-]*)$"
)
REFERENCE = re.compile(
    r"\$\{|\$[A-Za-z_]|%[A-Za-z_][A-Za-z0-9_]*%|<[A-Za-z_][^>]*>|\benv\.|process\.env|"
    r"System\.getenv|os\.environ|getenv\(|secrets?\.|vault|\{\{.*\}\}"
)
DEFAULT_IN_REFERENCE = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*:-?(.+)\}$")


def is_placeholder(value):
    """True when a captured value is obviously not a real secret."""
    value = value.strip()
    if not value:
        return True
    default = DEFAULT_IN_REFERENCE.match(value)
    if default:
        return is_placeholder(default.group(1))
    if PLACEHOLDER.match(value):
        return True
    if REFERENCE.search(value):
        return True
    if len(set(value)) <= 2:
        return True
    return False


def find_secret_kinds(text, known=None):
    """Return the kinds of secrets found in text, skipping values already in known."""
    known = known or set()
    kinds = []
    for kind, pattern in PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(1) if match.groups() else match.group(0)
            if match.groups() and is_placeholder(value):
                continue
            if value in known:
                continue
            if kind not in kinds:
                kinds.append(kind)
            break
    return kinds


def secret_values(text):
    """All candidate secret values in text (used to allow values an old file already had)."""
    values = set()
    for _, pattern in PATTERNS:
        for match in pattern.finditer(text):
            values.add(match.group(1) if match.groups() else match.group(0))
    return values
