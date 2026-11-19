import argparse
import os
import re
import subprocess
import sys
from pathlib import PurePosixPath

LIMIT = 20_000_000
ENV_NAME = re.compile(r"^(?:.*\.)?env(?:\.(?!example$|sample$|template$).*)?$")
SECRET_NAMES = re.compile(r"^(?:id_(?:rsa|dsa|ecdsa|ed25519)|\.netrc|\.npmrc|\.pypirc|credentials\.json|secrets?\.[a-z]+)$")
SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".keystore", ".jks", ".mobileprovision", ".sqlite", ".sqlite3", ".db", ".dump"}
HOME_PLACEHOLDERS = {"you", "me", "name", "user", "username", "runner", "ubuntu", "shared", "example", "vagrant"}
WORD_PLACEHOLDERS = re.compile(r"(?i)your|example|placeholder|changeme|redacted|dummy|sample|x{4,}|\*{3,}")
PLAIN_PASSWORDS = {"password", "pass", "passwd", "secret", "changeme", "example", "pw"}
RULES = [
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("access key", re.compile(
        r"\b(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{20,}"
        r"|[sr]k_live_[A-Za-z0-9]{16,}|AIza[0-9A-Za-z_-]{35}|xox[abprs]-[A-Za-z0-9-]{10,}"
        r"|eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
        r"|[MNO][A-Za-z0-9_-]{23,}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,})")),
    ("access key", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{20,}")),
    ("webhook address", re.compile(r"(?i)discord(?:app)?\.com/api/webhooks/\d+/[\w-]+|hooks\.slack\.com/services/[\w/]+")),
]
URL_LOGIN = re.compile(r"[a-z][a-z0-9+.-]*://(?:([^/\s:@]+):([^/\s:@]+)|([^/\s:@]{20,}))@")
ASSIGNED = re.compile(r"(?i)[A-Za-z0-9_-]*(?:api[_-]?key|secret|token|passw(?:or)?d|credential)[A-Za-z0-9_-]*[\"']?\s*[:=]\s*"
                      r"[\"']?([A-Za-z0-9_\-/+.=]{16,})")
HOME = re.compile(r"(?<![\w.])(?:/(?:Users|home)/|[A-Za-z]:\\Users\\)([^/\\\s\"'`<>$)*,;:]+)")


def git(top, *args):
    return subprocess.run(["git", "-C", top, *args], check=True, capture_output=True).stdout


def decode(data):
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", "replace")
    if b"\0" in data:
        data = data.replace(b"\0", b"")
    return data.decode("utf-8", "replace")


def assigned_secret(line):
    for value in ASSIGNED.findall(line):
        if not re.search(r"[0-9]", value) or WORD_PLACEHOLDERS.search(value):
            continue
        if "/" in value and re.fullmatch(r"[a-z0-9_./-]+", value):
            continue
        if re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+", value):
            continue
        return True
    return False


def url_login(line):
    for user, password, token in URL_LOGIN.findall(line):
        secret = password or token
        if secret.lower() in PLAIN_PASSWORDS or WORD_PLACEHOLDERS.search(secret) or re.search(r"[${<]", secret):
            continue
        return True
    return False


def findings(path, data):
    result = []
    name = PurePosixPath(path).name.lower()
    if ENV_NAME.match(name) or SECRET_NAMES.match(name) or PurePosixPath(name).suffix in SUFFIXES:
        result.append((path, 0, "file type that holds secrets or a database"))
    if len(data) > LIMIT:
        result.append((path, 0, "too large to check"))
        return result
    for number, line in enumerate(decode(data).splitlines(), 1):
        labels = [label for label, rule in RULES if rule.search(line)]
        if url_login(line):
            labels.append("credentials in a URL")
        if assigned_secret(line):
            labels.append("secret assigned in text")
        if any(owner.lower() not in HOME_PLACEHOLDERS for owner in HOME.findall(line)):
            labels.append("personal home path")
        result.extend((path, number, label) for label in dict.fromkeys(labels))
    return result


def staged(top):
    listing = git(top, "diff", "--cached", "--raw", "--no-renames", "--diff-filter=ACMRT", "-z").split(b"\0")
    for header, raw in zip(listing[0::2], listing[1::2]):
        if header.split()[1] == b"160000":
            continue
        path = raw.decode("utf-8", "surrogateescape")
        yield path, git(top, "cat-file", "blob", f":0:{path}")


def tracked(top):
    for raw in filter(None, git(top, "ls-files", "-z").split(b"\0")):
        path = raw.decode("utf-8", "surrogateescape")
        full = os.path.join(top, path)
        if os.path.islink(full) or not os.path.isfile(full):
            continue
        with open(full, "rb") as handle:
            yield path, handle.read(LIMIT + 1)


def main():
    parser = argparse.ArgumentParser(description="Reject secrets, database files, and personal paths before they are published.")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--staged", action="store_true", help="check the content staged for commit")
    scope.add_argument("--all", action="store_true", help="check the working copy of every tracked file")
    args = parser.parse_args()
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], check=True, capture_output=True,
                             text=True).stdout.strip()
        found = [item for path, data in (staged(top) if args.staged else tracked(top)) for item in findings(path, data)]
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"leak check could not run: {error}", file=sys.stderr)
        return 2
    for path, number, label in found:
        print(f"{path}:{number}: {label}" if number else f"{path}: {label}")
    if found:
        print("LEAK CHECK FAILED: remove these before committing. Values are not printed.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
