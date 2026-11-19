import argparse
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TAGS = ("NNG", "NNP", "SL", "XR")
MAX_BODY = 40_000_000
MAX_TEXT = 20000
HOSTS = ("127.0.0.1", "localhost", "::1")
LOCK = threading.Lock()
KIWI = None


def nouns(text):
    seen = {}
    with LOCK:
        tokens = KIWI.tokenize(str(text or "")[:MAX_TEXT])
    for token in tokens:
        if token.tag in TAGS:
            seen.setdefault(token.form)
    return list(seen)


class Handler(BaseHTTPRequestHandler):
    timeout = 15

    def local(self):
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        return host in HOSTS and not self.headers.get("Origin")

    def do_POST(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not self.local() or self.path != "/nouns" or not 0 < size <= MAX_BODY:
                raise ValueError("bad request")
            texts = json.loads(self.rfile.read(size)).get("texts")
            if not isinstance(texts, list):
                raise ValueError("texts must be a list")
            body = json.dumps({"nouns": [nouns(text) for text in texts]}, ensure_ascii=False).encode("utf-8")
            status = 200
        except Exception:
            body, status = b'{"error": "bad request"}', 400
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return


def main():
    global KIWI
    parser = argparse.ArgumentParser(description="Serve Korean nouns from the Kiwi analyzer to the registry on this machine.")
    parser.add_argument("--port", type=int, default=8792)
    args = parser.parse_args()
    try:
        from kiwipiepy import Kiwi
    except ImportError:
        print("kiwipiepy is not installed in this Python", file=sys.stderr)
        return 2
    KIWI = Kiwi()
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
