#!/usr/bin/env python3
import json, os, re, sys


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}))
    sys.exit(0)


def simple_commands(cmd):
    cmds, argv, word, has_word = [], [], [], False
    pending = []
    i, n = 0, len(cmd)
    skip_next_word = False

    def end_word():
        nonlocal word, has_word, skip_next_word
        if has_word:
            if skip_next_word: skip_next_word = False
            else: argv.append("".join(word))
        word, has_word = [], False

    def end_command():
        nonlocal argv
        end_word()
        if argv: cmds.append(argv)
        argv = []

    while i < n:
        c = cmd[i]
        if c == "\\" and i + 1 < n:
            if cmd[i + 1] != "\n": word.append(cmd[i + 1]); has_word = True
            i += 2; continue
        if c == "'":
            j = cmd.find("'", i + 1)
            if j < 0: j = n
            word.append(cmd[i + 1:j]); has_word = True; i = j + 1; continue
        if c == '"':
            j = i + 1; buf = []
            while j < n and cmd[j] != '"':
                if cmd[j] == "\\" and j + 1 < n and cmd[j + 1] in '"\\$`': buf.append(cmd[j + 1]); j += 2
                else: buf.append(cmd[j]); j += 1
            word.append("".join(buf)); has_word = True; i = j + 1; continue
        if c == "<" and cmd.startswith("<<", i) and not cmd.startswith("<<<", i):
            end_word()
            j = i + 2; strip = False
            if j < n and cmd[j] == "-": strip = True; j += 1
            while j < n and cmd[j] in " \t": j += 1
            k = j; delim = []
            while k < n and cmd[k] not in " \t\n;&|<>()":
                if cmd[k] == "'":
                    e = cmd.find("'", k + 1)
                    if e < 0: e = n
                    delim.append(cmd[k + 1:e]); k = e + 1
                elif cmd[k] == '"':
                    k += 1
                    while k < n and cmd[k] != '"':
                        if cmd[k] == "\\" and k + 1 < n and cmd[k + 1] in '"\\$`': delim.append(cmd[k + 1]); k += 2
                        else: delim.append(cmd[k]); k += 1
                    k += 1
                elif cmd[k] == "\\" and k + 1 < n: delim.append(cmd[k + 1]); k += 2
                else: delim.append(cmd[k]); k += 1
            pending.append(("".join(delim), strip)); i = k; continue
        if c in "<>":
            if has_word and "".join(word).isdigit(): word, has_word = [], False
            end_word()
            while i < n and cmd[i] in "<>": i += 1
            if i < n and cmd[i] == "&": i += 1
            skip_next_word = True; continue
        if c == "\n":
            end_command(); i += 1
            for delim, strip in pending:
                while i < n:
                    e = cmd.find("\n", i)
                    line = cmd[i:e] if e >= 0 else cmd[i:]
                    i = e + 1 if e >= 0 else n
                    if (line.lstrip("\t") if strip else line) == delim: break
            pending = []; continue
        if c in ";&|(){}`":
            end_command(); i += 1; continue
        if c in " \t":
            end_word(); i += 1; continue
        if c == "#" and not has_word:
            e = cmd.find("\n", i); i = e if e >= 0 else n; continue
        word.append(c); has_word = True; i += 1
    end_command()
    return cmds


KEYWORDS = {"then", "do", "else", "elif", "if", "while", "until", "!", "time", "command", "builtin", "exec", "nohup", "sudo", "env"}
GIT_VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--config-env"}
COMMIT_VALUE_OPTS = {"--message", "--file", "--author", "--date", "--reuse-message", "--reedit-message", "--fixup",
                     "--squash", "--template", "--cleanup", "--pathspec-from-file", "--trailer"}
EVERYTHING = {".", "*", ":/", ":/*", "..", ":(top)", ":(top)*", ":(top)."}


def is_everything(pathspec):
    if pathspec in EVERYTHING: return True
    parts = [p for p in pathspec.split("/") if p not in ("", ".")]
    return all(p in ("..", "*") for p in parts)


def stages_all(argv, depth=0):
    a = list(argv)
    while a and (a[0] in KEYWORDS or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", a[0])): a.pop(0)
    if not a: return False
    name = re.split(r"[\\/]", a[0])[-1].lower()
    if name.endswith(".exe"): name = name[:-4]
    if name in ("sh", "bash", "zsh", "dash") and "-c" in a and depth < 3:
        k = a.index("-c")
        return k + 1 < len(a) and any(stages_all(c, depth + 1) for c in simple_commands(a[k + 1]))
    if name != "git": return False
    k = 1
    while k < len(a) and a[k].startswith("-"):
        k += 2 if a[k] in GIT_VALUE_OPTS else 1
    if k >= len(a): return False
    verb, rest = a[k], a[k + 1:]
    if verb in ("add", "stage"):
        paths_only, all_flag, named, everything = False, False, 0, False
        for t in rest:
            if paths_only or not t.startswith("-") or t == "-":
                if is_everything(t): everything = True
                else: named += 1
                continue
            if t == "--": paths_only = True
            elif t in ("--all", "--update", "--no-ignore-removal"): all_flag = True
            elif not t.startswith("--") and ("A" in t or "u" in t): all_flag = True
        return everything or (all_flag and named == 0)
    if verb == "commit":
        k = 0
        while k < len(rest):
            t = rest[k]
            if t == "--": return any(is_everything(x) for x in rest[k + 1:])
            if t == "--all": return True
            if t in COMMIT_VALUE_OPTS: k += 2; continue
            if t.startswith("-") and not t.startswith("--") and len(t) > 1:
                takes_next = False
                for pos, ch in enumerate(t[1:], 1):
                    if ch == "a": return True
                    if ch in "mFCct":
                        takes_next = pos == len(t) - 1
                        break
                    if ch in "Su": break
                k += 2 if takes_next else 1
                continue
            if not t.startswith("-") and is_everything(t): return True
            k += 1
        return False
    return False


def covers(entries, rel, fold):
    rel = fold(rel)
    for entry in entries:
        parts = [p for p in str(entry).replace("\\", "/").split("/") if p not in ("", ".")]
        entry = fold("/".join(parts))
        if entry and (rel == entry or rel.startswith(entry + "/")):
            return True
    return False


def find_root(data):
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return os.path.realpath(env)
    cwd = data.get("cwd")
    start = os.path.realpath(cwd if isinstance(cwd, str) and cwd else os.getcwd())
    here = start
    while True:
        if os.path.isfile(os.path.join(here, "WORKING.md")) or os.path.exists(os.path.join(here, ".git")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            return start
        here = parent


def same_file(a, b):
    try:
        return os.path.samefile(a, b)
    except Exception:
        return False


def read_list(config, key):
    value = config.get(key)
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    if not isinstance(data, dict):
        return
    inp = data.get("tool_input") or {}
    if not isinstance(inp, dict):
        return
    tool = data.get("tool_name")
    if not isinstance(tool, str) or not tool:
        return
    root = find_root(data)
    try:
        with open(os.path.join(root, "WORKING.md"), encoding="utf-8") as handle:
            text = handle.read()
    except Exception:
        return
    section = re.search(r"^## Lane 1(?![0-9]).*?$(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not section:
        return

    if tool == "Bash":
        try:
            swept = any(stages_all(c) for c in simple_commands(str(inp.get("command", ""))))
        except Exception:
            swept = False
        if swept:
            deny("lane-guard: stage only this task's files by name (git add <paths>); 'git add -A/.', "
                 "'git commit -a' would sweep another session's uncommitted work into this commit.")
        return

    path = inp.get("file_path") or inp.get("notebook_path") or ""
    if not isinstance(path, str) or not path:
        return
    cwd = data.get("cwd")
    base = cwd if isinstance(cwd, str) and cwd else root
    full = os.path.realpath(path if os.path.isabs(path) else os.path.join(base, path))
    try:
        rel = os.path.relpath(full, root)
    except ValueError:
        return
    if rel == os.pardir or rel.startswith(os.pardir + os.sep) or os.path.isabs(rel):
        return
    rel = rel.replace(os.sep, "/")
    working = os.path.join(root, "WORKING.md")
    if rel == "WORKING.md" or same_file(full, working):
        return
    folds = working.swapcase() != working and same_file(working.swapcase(), working)
    fold = (lambda x: x.lower()) if folds else (lambda x: x)

    config = {}
    try:
        with open(os.path.join(root, ".claude", "lane-guard.json"), encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            config = loaded
    except Exception:
        pass
    always = [".claude", "claude.md", "agents.md"]
    guarded = read_list(config, "guarded")
    if not covers(always, rel, str.lower):
        if covers(read_list(config, "open") or [], rel, fold):
            return
        if guarded is not None and not covers(guarded, rel, fold):
            return

    sid = str(data.get("session_id") or "")
    holders = [h.rstrip(".") for h in re.findall(r"session_id=([A-Za-z0-9_.-]+)", section.group(1))]
    holders = [h for h in holders if h]
    if sid and sid in holders:
        return
    if holders:
        deny("lane-guard: lane 1 is held by another session (session_id=%s in WORKING.md), so %s may not be "
             "edited from this session (session_id=%s). Work in lane 2 or 3, or ask the holder or the user."
             % (", ".join(holders), rel, sid))
    deny("lane-guard: lane 1 is free. To edit %s, first take lane 1: write one line under '## Lane 1' in "
         "WORKING.md with session_id=%s, your session name, the task, the files and the start time; "
         "clear it after the commit." % (rel, sid))


if __name__ == "__main__":
    main()
