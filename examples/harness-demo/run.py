import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins" / "engineering-workflow" / "skills" / "engineering-workflow" / "scripts"
COPY = ROOT / "plugins" / "engineering-workflow" / "skills" / "korean-copy" / "scripts" / "copy_check.py"
DEMO = "examples/harness-demo"


def run(*args):
    result = subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, capture_output=True)
    return result.returncode, result.stdout.decode("utf-8", "replace"), result.stderr.decode("utf-8", "replace")


def say(text=""):
    sys.stdout.buffer.write((text + "\n").encode("utf-8"))
    sys.stdout.flush()


def steps(out):
    yield ("Progress board: render the shop board to one HTML page",
           [SCRIPTS / "board.py", "render", f"{DEMO}/shop/.harness/board.json", "--out", out / "board.html"], 0, ())
    yield ("Work records: check the shop records", [SCRIPTS / "record.py", "--root", f"{DEMO}/shop", "check"], 0,
           ("records ok",))
    yield ("Registry scan: read both apps into nodes and links (no database needed)",
           [SCRIPTS / "registry_scan.py", f"{DEMO}/registry.json", "--out", out / "scan.json"], 0, ())
    yield ("Drift: which app no longer has the template's shared rules",
           [SCRIPTS / "app_template.py", "drift", "--config", f"{DEMO}/registry.json"], 1,
           ("cafe: differs: Workflow",))
    yield ("Korean copy: the cafe strings against its style sheet",
           [COPY, "--style", f"{DEMO}/cafe/.harness/copy-style.json"], 1,
           ("order.failed: error: speech-level", "menu.buy: error: term: '구매' should be '구입'"))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the harness demo on two sample apps, without a database.")
    parser.add_argument("--check", action="store_true", help="exit 1 unless every step gives the expected result")
    args = parser.parse_args(argv)
    failed = 0
    with tempfile.TemporaryDirectory() as folder:
        out = Path(folder)
        for title, command, code, expected in steps(out):
            got, stdout, stderr = run(*command)
            ok = got == code and all(item in stdout for item in expected) and "SKIPPED" not in stderr
            failed += not ok
            shown = " ".join(Path(part).relative_to(ROOT).as_posix() if str(part).startswith(str(ROOT)) else str(part)
                             for part in command)
            say(f"\n== {title}\n$ python3 {shown}")
            say((stdout.strip() or stderr.strip())[:1200] if "scan" not in title else stderr.strip()[:1200])
            say(f"exit {got} (expected {code}){'' if ok else '  <-- unexpected'}")
        scan = json.loads((out / "scan.json").read_text(encoding="utf-8"))
        nodes = {item["id"] for entry in scan["files"].values() for item in entry["nodes"]}
        links = {(item["from"], item["type"], item["to"]) for entry in scan["files"].values() for item in entry["links"]}
        errors = [path for path, entry in scan["files"].items() if entry.get("error")]
        say(f"scan: {len(scan['files'])} files, {len(nodes)} nodes, {len(links)} links")
        record = "record:shop/2026-11-19-round-refunds-per-line-item"
        wanted = {"app:shop", "app:cafe", record, "task:shop/T2"}
        wanted_links = {(record, "CONCERNS", "skill:payments"), (record, "FOR", "task:shop/T1"),
                        ("task:shop/T2", "AFTER", "task:shop/T1")}
        if errors or not wanted <= nodes or not wanted_links <= links:
            failed += 1
            say(f"scan errors {errors}, missing nodes {sorted(wanted - nodes)}, missing links "
                f"{sorted(wanted_links - links)}  <-- unexpected")
        if not (out / "board.html").is_file() or "Refund by store credit" not in (out / "board.html").read_text(
                encoding="utf-8"):
            failed += 1
            say("board page was not written  <-- unexpected")
    say(f"\n{'all steps gave the expected result' if not failed else f'{failed} unexpected results'}")
    return 1 if args.check and failed else 0


if __name__ == "__main__":
    sys.exit(main())
