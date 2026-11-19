import argparse
import fnmatch
import json
import re
import sys
import xml.etree.ElementTree as ElementTree
from collections import Counter
from pathlib import Path

HANGUL = re.compile(r"[가-힣]")
HANGUL_WORD = re.compile(r"[가-힣]+")
SPLIT = re.compile(r"(?<=[.!?…])\s+|\n+")
PRINTF = re.compile(r"%(?:\d+\$)?[-+0 #]*\d*(?:\.\d+)?l{0,2}[@sdifuxXcg]|%\{[A-Za-z0-9_]+\}|\$\{[A-Za-z0-9_.]+\}")
ARGUMENT = re.compile(r"[A-Za-z0-9_]*")
PAIRED = re.compile(r"은\(는\)|는\(은\)|이\(가\)|가\(이\)|을\(를\)|를\(을\)|와\(과\)|과\(와\)|\(으\)로|\(이\)")
STRINGS_LINE = re.compile(r'^\s*"?([^"=]+?)"?\s*=\s*"?(.*?)"?\s*;?\s*$')
PROPERTY_LINE = re.compile(r"^\s*([^=:\s]+)\s*[=:]\s*(.*?)\s*$")
ESCAPE = re.compile(r"\\(u[0-9A-Fa-f]{4}|.)")
LOG_LINE = re.compile(r"^\s*[-*]\s*(.+?)\s*=>\s*(.+?)\s*(?:\|.*)?$")
LEVELS = ("hapsyo", "haeyo", "plain")
LEVEL_NAMES = {"hapsyo": "합니다", "haeyo": "해요", "plain": "한다"}
NOUNS = {"필요", "중요", "수요", "개요", "주요", "소요", "동요", "민요", "강요", "판다", "사이다", "다", "요"}
VERB_FINALS = {4, 6, 18, 20, 25, 26, 27}
PLAIN_ENDINGS = ("이다", "하다", "르다", "쁘다", "프다", "니다", "리다", "지다", "보다", "주다", "되다", "크다")
SPELLING = {
    "되요": "돼요", "됬": "됐", "몇일": "며칠", "할께": "할게", "줄께": "줄게", "볼께": "볼게", "갈께": "갈게",
    "올께": "올게", "드릴께": "드릴게", "어떻해": "어떡해", "금새": "금세", "웬지": "왠지", "왠만": "웬만",
    "않되": "안 되", "않돼": "안 돼", "뵈요": "봬요", "오랫만": "오랜만", "역활": "역할", "어의없": "어이없",
    "일일히": "일일이", "깨끗히": "깨끗이", "곰곰히": "곰곰이", "틈틈히": "틈틈이", "바꼈": "바뀌었",
}
TRANSLATED = re.compile(r"되어 ?[지집진질졌]|당신|것이 가능|에 의해|함에 있어|에 있어서|[을를] 가집니다")
SHEET_KEYS = {"level", "terms", "banned", "period", "max_length", "paired_particles", "allow", "sources", "log"}


class Problem(Exception):
    pass


def level(sentence):
    words = HANGUL_WORD.findall(sentence)
    if not words:
        return None
    last = words[-1]
    if last in NOUNS:
        return None
    if last.endswith(("니다", "니까", "시오")):
        return "hapsyo"
    if last.endswith(("요", "죠")) and len(last) >= 2:
        return "haeyo"
    if last.endswith("다") and len(last) >= 2 and (
            last.endswith(PLAIN_ENDINGS) or (ord(last[-2]) - 0xAC00) % 28 in VERB_FINALS):
        return "plain"
    return None


def sentences(text):
    return [part.strip() for part in SPLIT.split(text) if part.strip()]


def flatten(value, prefix=""):
    if isinstance(value, str):
        yield prefix or "(root)", value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from flatten(item, f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(value, list):
        for position, item in enumerate(value):
            yield from flatten(item, f"{prefix}[{position}]")


def unescape(text):
    def one(match):
        code = match.group(1)
        if code[0] == "u" and len(code) == 5:
            return chr(int(code[1:], 16))
        return {"n": "\n", "t": " ", "r": "\n"}.get(code, code)
    return ESCAPE.sub(one, text)


def arguments(text, start, found, depth=0):
    position = start
    while position < len(text):
        if text[position] == "}":
            return position + 1
        if text[position] != "{" or depth > 20:
            position += 1
            continue
        end = position + 1
        while end < len(text) and text[end] not in ",{}":
            end += 1
        name = text[position + 1:end].strip()
        if end == len(text) or text[end] == "{" or not ARGUMENT.fullmatch(name):
            position += 1
        elif text[end] == "}":
            found.add(name)
            position = end + 1
        else:
            found.add(name)
            position = end + 1
            while position < len(text) and text[position] != "}":
                position = arguments(text, position + 1, found, depth + 1) if text[position] == "{" else position + 1
            position += 1
    return position


def placeholders(text):
    named = set()
    arguments(text, 0, named)
    return sorted(PRINTF.findall(text)) + sorted("{" + name + "}" for name in named)


def read_source(path):
    try:
        raw = Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        raise Problem(f"cannot read {path}: {error}")
    suffix = Path(path).suffix.lower()
    if suffix in (".json", ".arb"):
        try:
            return [(key, text) for key, text in flatten(json.loads(raw)) if not key.startswith("@")]
        except (ValueError, RecursionError) as error:
            raise Problem(f"{path} is not valid JSON: {error}")
    if suffix == ".xml":
        try:
            tree = ElementTree.fromstring(raw)
        except ElementTree.ParseError as error:
            raise Problem(f"{path} is not valid XML: {error}")
        return [(item.get("name", ""), unescape("".join(item.itertext()))) for item in tree.iter("string")]
    if suffix in (".strings", ".properties"):
        found = []
        pattern = STRINGS_LINE if suffix == ".strings" else PROPERTY_LINE
        for line in raw.splitlines():
            if line.lstrip().startswith(("//", "#", "/*", "!")):
                continue
            match = pattern.match(line)
            if match:
                found.append((match.group(1).strip(), unescape(match.group(2))))
        return found
    return [(str(number), line.strip()) for number, line in enumerate(raw.splitlines(), 1) if line.strip()]


def read_sheet(path):
    try:
        sheet = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise Problem(f"cannot read style sheet {path}: {error}")
    if not isinstance(sheet, dict):
        raise Problem(f"style sheet {path} must be an object")
    unknown = sorted(set(sheet) - SHEET_KEYS)
    if unknown:
        raise Problem(f"style sheet {path} has unknown keys: {', '.join(unknown)}")
    if sheet.get("level") not in (None,) + LEVELS:
        raise Problem(f"level must be one of {', '.join(LEVELS)}")
    if sheet.get("period") not in (None, "never", "always"):
        raise Problem("period must be never or always")
    if sheet.get("paired_particles", "warn") not in ("allow", "warn", "error"):
        raise Problem("paired_particles must be allow, warn, or error")
    terms = sheet.get("terms", {})
    if not isinstance(terms, dict) or not all(
            isinstance(wrong, list) and all(isinstance(item, str) and item for item in wrong) for wrong in terms.values()):
        raise Problem("terms must map a preferred word to a list of words to avoid")
    limits = sheet.get("max_length", {})
    if not isinstance(limits, dict) or not all(isinstance(limit, int) and limit > 0 for limit in limits.values()):
        raise Problem("max_length must map a key pattern to a positive number")
    for name in ("banned", "allow", "sources"):
        if not isinstance(sheet.get(name, []), list) or not all(isinstance(item, str) for item in sheet.get(name, [])):
            raise Problem(f"{name} must be a list of texts")
    if not isinstance(sheet.get("log", ""), str):
        raise Problem("log must be a path")
    return sheet


def read_log(path):
    try:
        raw = Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        raise Problem(f"cannot read correction log {path}: {error}")
    pairs = []
    for line in raw.splitlines():
        match = LOG_LINE.match(line)
        if match:
            wrong, right = (part.strip().strip("`") for part in match.groups())
            if wrong and right and wrong != right:
                pairs.append((wrong, right))
    return pairs


def has(text, wrong, right):
    return wrong in (text.replace(right, "\0") if right and wrong in right else text)


def key_matches(key, pattern):
    return key == pattern or fnmatch.fnmatchcase(key, pattern.replace("[", "[[]"))


def allowed(key, text, allow):
    return any(text == item or key_matches(key, item) for item in allow)


def check_text(key, text, sheet, corrections):
    found = []

    def add(rule, message, severity="error"):
        found.append({"key": key, "rule": rule, "severity": severity, "message": message, "text": text})

    for preferred, avoid in sheet.get("terms", {}).items():
        for wrong in avoid:
            if has(text, wrong, preferred):
                add("term", f"'{wrong}' should be '{preferred}'")
    for wrong, right in corrections:
        if has(text, wrong, right):
            add("corrected", f"'{wrong}' was corrected to '{right}' before")
    for phrase in sheet.get("banned", []):
        if isinstance(phrase, str) and phrase and phrase in text:
            add("banned", f"'{phrase}' is banned by the style sheet")
    for wrong, right in SPELLING.items():
        if wrong in text:
            add("spelling", f"'{wrong}' should be '{right}'")
    if "  " in text.strip() or re.search(r"\S [.,!?](?:\s|$)", text):
        add("spacing", "double space, or a space before punctuation")
    for pattern, limit in sheet.get("max_length", {}).items():
        if key_matches(key, pattern) and len(text) > limit:
            add("length", f"{len(text)} characters, the limit for {pattern} is {limit}")
    paired = sheet.get("paired_particles", "warn")
    match = PAIRED.search(text)
    if match and paired != "allow":
        add("paired-particle", f"'{match.group()}' reads as a template; pick the particle from the word",
            "error" if paired == "error" else "warning")
    match = TRANSLATED.search(text)
    if match:
        add("translated", f"'{match.group()}' reads as translated; say it the way a person would", "warning")
    parts = sentences(text)
    levels = [(part, level(part)) for part in parts]
    wanted = sheet.get("level")
    seen = [item for _, item in levels if item]
    if wanted:
        for part, item in levels:
            if item and item != wanted:
                add("speech-level", f"'{part}' ends in {LEVEL_NAMES[item]} style, the sheet says {LEVEL_NAMES[wanted]}")
    elif len(set(seen)) > 1:
        add("speech-level", "one text mixes " + " and ".join(LEVEL_NAMES[item] for item in dict.fromkeys(seen))
            + " styles")
    period = sheet.get("period")
    last = parts[-1].rstrip(" \"'”’)") if parts else ""
    if period == "never" and last.endswith(".") and not last.endswith(".."):
        add("period", "ends with a period, the sheet says never")
    if period == "always" and levels and levels[-1][1] and not last.endswith((".", "!", "?", "…")):
        add("period", "has no closing punctuation, the sheet says always")
    return found, seen


def check(sources, sheet, corrections, base=None):
    findings = []
    majority = Counter()
    by_level = []
    allow = sheet.get("allow", [])
    for source in sources:
        entries = read_source(source)
        if base:
            original = dict(read_source(base))
            for key, text in entries:
                if (key in original and placeholders(text) != placeholders(original[key])
                        and not allowed(key, text, allow)):
                    findings.append({"file": str(source), "key": key, "rule": "placeholder", "severity": "error",
                                     "message": f"placeholders differ from {base}: "
                                                f"{' '.join(placeholders(original[key])) or 'none'}",
                                     "text": text})
        for key, text in entries:
            if not HANGUL.search(text) or allowed(key, text, allow):
                continue
            found, seen = check_text(key, text, sheet, corrections)
            for item in found:
                findings.append({"file": str(source), **item})
            majority.update(seen)
            if len(set(seen)) == 1:
                by_level.append((str(source), key, text, seen[0]))
    if not sheet.get("level") and len(majority) > 1:
        top = max(LEVELS, key=lambda name: majority[name])
        for source, key, text, item in by_level:
            if item != top:
                findings.append({"file": source, "key": key, "rule": "speech-level", "severity": "error",
                                 "message": f"{LEVEL_NAMES[item]} style, most texts use {LEVEL_NAMES[top]}",
                                 "text": text})
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description="Mechanical checks for Korean product copy: speech level, terms, "
                                                 "earlier corrections, spelling, punctuation, placeholders.")
    parser.add_argument("files", nargs="*", help="copy files (.json, .arb, .strings, .properties, .xml, or plain text)")
    parser.add_argument("--style", help="style sheet (default: .harness/copy-style.json when it exists)")
    parser.add_argument("--log", help="correction log (default: the sheet's log, then .harness/copy-corrections.md)")
    parser.add_argument("--base", help="source-language file with the same keys, to compare placeholders")
    parser.add_argument("--strict", action="store_true", help="warnings fail the check too")
    parser.add_argument("--json", action="store_true", help="print the findings as JSON")
    args = parser.parse_args(argv)
    try:
        style = Path(args.style) if args.style else Path(".harness/copy-style.json")
        if args.style and not style.is_file():
            raise Problem(f"style sheet {style} not found")
        sheet = read_sheet(style) if style.is_file() else {}
        root = style.parent.parent if style.is_file() and style.parent.name == ".harness" else Path(".")
        sources = args.files or [str(root / item) for item in sheet.get("sources", []) if isinstance(item, str)]
        if not sources:
            raise Problem("no files given and the style sheet lists no sources")
        log = Path(args.log) if args.log else (root / sheet["log"] if sheet.get("log") else
                                              root / ".harness" / "copy-corrections.md")
        if (args.log or sheet.get("log")) and not log.is_file():
            raise Problem(f"correction log {log} not found")
        corrections = read_log(log) if log.is_file() else []
        findings = check(sources, sheet, corrections, args.base)
    except Problem as error:
        print(f"COPY CHECK UNAVAILABLE: {error}", file=sys.stderr)
        return 2
    errors = sum(item["severity"] == "error" for item in findings)
    warnings = len(findings) - errors
    if args.json:
        output = json.dumps(findings, ensure_ascii=False, indent=1)
    else:
        lines = [f"{item['file']}:{item['key']}: {item['severity']}: {item['rule']}: {item['message']}"
                 for item in findings]
        output = "\n".join(lines + [f"{errors} errors, {warnings} warnings"])
    sys.stdout.buffer.write((output + "\n").encode("utf-8"))
    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
