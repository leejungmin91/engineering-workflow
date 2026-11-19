import importlib.util
import json
import subprocess
import sys
import threading
import unittest
import urllib.error
import urllib.request
from collections import namedtuple
from http.server import ThreadingHTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "registry_kiwi_server.py"
SPEC = importlib.util.spec_from_file_location("registry_kiwi_server", SCRIPT)
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)
Token = namedtuple("Token", "form tag")


class FakeKiwi:
    def tokenize(self, text):
        table = {"창": "NNG", "돌": "NNG", "을": "JKO", "Unity": "SL", "깎": "VV"}
        return [Token(piece, table.get(piece, "NNG")) for piece in text.split()]


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.KIWI = FakeKiwi()
        cls.http = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.http.serve_forever, daemon=True).start()
        cls.address = f"http://127.0.0.1:{cls.http.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()

    def post(self, path, body, **headers):
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(self.address + path, data=data, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.load(error)

    def test_nouns_are_returned_per_text_without_repeats_or_other_word_classes(self):
        status, reply = self.post("/nouns", {"texts": ["창 돌 을 창 깎 Unity", "", None]})
        self.assertEqual(status, 200)
        self.assertEqual(reply["nouns"], [["창", "돌", "Unity"], [], []])

    def test_bad_requests_get_400_and_the_server_keeps_running(self):
        for path, body in (("/other", {"texts": []}), ("/nouns", {"texts": "no"}), ("/nouns", b"{"), ("/nouns", [])):
            status, reply = self.post(path, body)
            self.assertEqual((status, reply), (400, {"error": "bad request"}))
        self.assertEqual(self.post("/nouns", {"texts": ["돌"]})[1]["nouns"], [["돌"]])

    def test_requests_from_a_web_page_or_another_host_name_are_refused(self):
        self.assertEqual(self.post("/nouns", {"texts": ["돌"]}, Origin="https://evil.example")[0], 400)
        self.assertEqual(self.post("/nouns", {"texts": ["돌"]}, Host="evil.example:8792")[0], 400)
        self.assertEqual(self.post("/nouns", {"texts": ["돌"]}, Host="localhost:8792")[0], 200)
        self.assertEqual(server.Handler.timeout, 15)

    def test_health_check_and_long_text_cut(self):
        with urllib.request.urlopen(self.address + "/", timeout=5) as response:
            self.assertEqual(json.load(response), {"ok": True})
        _, reply = self.post("/nouns", {"texts": ["x " * 9999 + "x 돌"]})
        self.assertEqual(reply["nouns"], [["x"]])

    def test_it_listens_on_this_machine_only_and_says_so_when_kiwi_is_missing(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('ThreadingHTTPServer(("127.0.0.1", args.port), Handler)', source)
        try:
            import kiwipiepy
        except ImportError:
            result = subprocess.run([sys.executable, str(SCRIPT), "--port", "0"], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 2)
            self.assertIn("kiwipiepy is not installed", result.stderr)


if __name__ == "__main__":
    unittest.main()
