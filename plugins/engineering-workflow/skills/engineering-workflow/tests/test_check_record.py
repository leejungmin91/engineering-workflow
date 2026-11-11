import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_record.py"


def check(state="passed", snapshot="current", evidence="targeted regression: exit 0"):
    return dict(id="regression", status=state, snapshot=snapshot, evidence=evidence)


def task(id="parser", after=None, checks=None):
    return dict(id=id, after=after if after is not None else [],
                checks=checks if checks is not None else [check()])


class GateTests(unittest.TestCase):
    def run_gate(self, tasks):
        return subprocess.run([sys.executable, str(SCRIPT), "-", "--snapshot", "current"],
                              input=json.dumps(dict(tasks=tasks)), text=True, capture_output=True)

    def expect(self, tasks, status, *messages):
        result = self.run_gate(tasks)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, status, output)
        for message in messages:
            self.assertIn(message, output)

    def test_fresh_evidence_on_all_required_tasks_passes(self):
        self.expect([task("ui", ["parser"]), task()], 0, "READY")

    def test_failed_upstream_keeps_downstream_waiting(self):
        self.expect([task(checks=[check("failed")]), task("ui", ["parser"])],
                    1, "NOT READY", "parser/regression: failed", "ui: waiting for parser")

    def test_old_evidence_is_not_a_pass(self):
        self.expect([task(checks=[check(snapshot="before-last-change")])], 1, "stale evidence")

    def test_empty_proof_and_unverified_are_not_passes(self):
        self.expect([task(checks=[check(evidence=" "), dict(check("unverified"), id="device")])],
                    1, "missing evidence", "device: unverified")

    def test_cycle_and_unknown_dependency_are_invalid(self):
        self.expect([task("a", ["b"]), task("b", ["a"])], 2, "cycle")
        self.expect([task("a", ["missing"])], 2, "unknown dependency")

    def test_duplicate_ids_and_empty_gate_list_are_invalid(self):
        self.expect([task(), task()], 2, "duplicate task")
        self.expect([task(checks=[check(), check()])], 2, "duplicate check")
        self.expect([task(checks=[])], 2, "at least one check")
        self.expect([], 2, "at least one task")

    def test_duplicate_json_keys_cannot_overwrite_a_failure(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "-", "--snapshot", "current"],
            input='{"tasks":[{"id":"parser","after":[],"checks":[{"id":"regression",'
                  '"status":"failed","status":"passed","snapshot":"current","evidence":"exit 0"}]}]}',
            text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("duplicate JSON key", result.stderr)

    def test_evidence_text_is_not_echoed(self):
        marker = "SYNTHETIC_PRIVATE_OUTPUT"
        result = self.run_gate([task(checks=[check(evidence=marker)])])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(marker, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
