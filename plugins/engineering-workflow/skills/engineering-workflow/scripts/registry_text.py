import re

HANGUL = re.compile(r"[가-힣]+")
WORD = re.compile(r"[가-힣]+|[A-Za-z0-9][A-Za-z0-9_.+#-]*")
MAX_WORDS = 24
MAX_WORD = 40
MAX_FORMS = 120
MAX_TEXT = 20000
ENDINGS = sorted((
    "에서는", "에서도", "으로는", "으로도", "에게서", "이라는", "이라고", "입니다", "습니다", "합니다", "했었던", "했습니다",
    "에서", "으로", "에게", "까지", "부터", "처럼", "보다", "이나", "이랑", "하고", "했던", "하는", "하기", "해서", "했다",
    "하다", "해줘", "하면", "되는", "된", "한", "할", "해", "은", "는", "이", "가", "을", "를", "의", "에", "도", "만", "로",
    "와", "과", "랑", "나", "들"), key=len, reverse=True)
KOREAN_ENGLISH = {
    "게임": "game", "밸런스": "balance", "에셋": "asset", "성능": "performance", "플레이테스트": "playtest",
    "사운드": "sound", "소리": "sound", "유니티": "Unity", "블렌더": "Blender", "회귀": "regression", "범위": "scope",
    "하네스": "harness", "루프": "loop", "그래프": "graph", "의존성": "dependency", "교차검토": "independent review",
    "코드리뷰": "code review", "검토": "review", "보고서": "report", "리포트": "report", "테스트": "test",
    "시험": "test", "검증": "verification", "디버깅": "debug", "버그": "bug", "릴리즈": "release", "배포": "release deploy",
    "감사": "audit", "용량": "size budget", "예산": "budget", "점검": "check", "진행": "progress going",
    "계속": "keep going continue", "주석": "comments", "금지": "no", "커밋": "commit", "푸시": "push", "규칙": "rule",
    "디자인": "design", "시스템": "system", "토큰": "token", "배너": "banner", "브랜드": "brand", "말투": "voice tone",
    "발표": "presentation slides", "슬라이드": "slides", "자료": "deck document", "엑셀": "spreadsheet xlsx excel",
    "스프레드시트": "spreadsheet", "워드": "word docx", "문서": "document", "피디에프": "pdf", "훅": "hook",
    "대시보드": "dashboard board", "보드": "board", "조사": "research", "스킬": "skill", "플러그인": "plugin",
    "설정": "settings config", "모델": "model", "세션": "session", "에이전트": "agent", "앱": "app", "스토어": "store",
    "스크린샷": "screenshot", "이미지": "image", "색": "color", "화면": "screen ui", "번역": "translation",
    "검색": "search", "색인": "index", "기록": "record", "결정": "decision", "작업": "task work", "브라우저": "browser",
    "결제": "payment", "환불": "refund", "로그인": "login", "알림": "notification", "권한": "permission",
    "비밀": "secret", "키": "key", "서버": "server", "설치": "install", "만들기": "create", "새로": "new create",
    "정리": "clean organize", "작성": "write", "분석": "analysis", "계획": "plan", "일정": "schedule",
}


def stems(word):
    found = []
    for ending in ENDINGS:
        if word.endswith(ending) and len(word) > len(ending):
            stem = word[:-len(ending)]
            if stem not in found:
                found.append(stem)
    return found


def variants(word):
    if not HANGUL.fullmatch(word):
        return [word]
    return [word] + stems(word)


def index_terms(text, limit=400):
    seen = {}
    for match in HANGUL.finditer((text or "")[:MAX_TEXT]):
        word = match.group()
        if len(word) > MAX_WORD:
            continue
        for stem in stems(word):
            seen.setdefault(stem)
            if len(seen) >= limit:
                return " ".join(seen)
    return " ".join(seen)


def plural(word):
    if word.endswith("y") and len(word) > 2 and word[-2] not in "aeiou":
        return word[:-1] + "ies"
    return word + ("es" if word.endswith(("s", "sh", "ch", "x")) else "s")


def query_words(words):
    found = []
    for raw in words:
        for word in str(raw).split():
            if len(found) >= MAX_WORDS:
                return found
            found.append(word[:MAX_WORD])
    return found


def names(word, name):
    if word == name:
        return True
    return len(name) >= 2 and bool(HANGUL.fullmatch(name)) and word.startswith(name)


def expand(words, extra=None):
    table = dict(KOREAN_ENGLISH)
    table.update(extra or {})
    result = {}

    def add(item):
        if item and len(result) < MAX_FORMS:
            result.setdefault(item)

    def add_english(item):
        add(item)
        if item.isalpha() and item.islower() and len(item) > 2:
            add(plural(item))

    for raw in query_words(words):
        for word in WORD.findall(raw):
            for form in variants(word):
                add(form)
                for english in table.get(form, "").split():
                    add_english(english)
            if HANGUL.fullmatch(word):
                for key, english in table.items():
                    if len(key) >= 2 and key in word:
                        add(key)
                        for item in english.split():
                            add_english(item)
    return list(result)
