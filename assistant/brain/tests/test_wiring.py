"""Hub routing and JSON bridge: the assistant's public surface."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from assistant import hub
from assistant.brain import bridge


class HubTests(unittest.TestCase):
    def test_help_lists_every_route(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(hub.main(["--help"]), 0)
        for name in ("diagnose", "ask", "search", "issue", "settings", "brain", "api"):
            self.assertIn(name, out.getvalue())

    def test_unknown_command_exits_2(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(hub.main(["bogus"]), 2)

    def test_selfcheck_routes_to_diagnostics(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(hub.main(["selfcheck"]), 0)
        self.assertIn("selfcheck OK", out.getvalue())

    def test_brain_routes_to_cli(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = hub.main(["brain", "--state", str(d / "s.json"),
                                 "--ledger", str(d / "l.json"), "ledger", "list"])
            self.assertEqual(code, 0)
            self.assertIn("no pending proposals", out.getvalue())


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.state = str(self.d / "s.json")
        self.ledger = str(self.d / "l.json")

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, request):
        return bridge.handle(request, state_path=self.state, ledger_path=self.ledger)

    def test_unknown_op_and_bad_shape(self):
        self.assertFalse(self.call({"op": "explode"})["ok"])
        self.assertFalse(self.call(["not", "a", "dict"])["ok"])

    def test_missing_field_is_an_error_not_a_crash(self):
        r = self.call({"op": "estimate_observe"})
        self.assertFalse(r["ok"])
        self.assertIn("KeyError", r["error"])

    def test_plan_then_propose_then_approve_then_learn(self):
        tasks = [{"id": "a", "effort_min": 30, "importance": 0.9, "deadline_days": 1},
                 {"id": "b", "effort_min": 30, "importance": 0.2}]
        r = self.call({"op": "plan", "tasks": tasks, "minutes": 60, "propose": True, "top": 2})
        self.assertTrue(r["ok"])
        self.assertEqual(r["result"]["proposed"], 2)
        pending = self.call({"op": "ledger_list"})["result"]
        self.assertEqual(len(pending), 2)
        self.assertTrue(self.call({"op": "ledger_decide", "id": pending[0]["id"], "approve": True})["ok"])
        learned = self.call({"op": "ledger_learn"})
        self.assertEqual(learned["result"]["examples"], 1)

    def test_review_and_estimate_ops(self):
        self.assertTrue(self.call({"op": "review_grade", "id": "c", "rating": 3, "days": 0})["ok"])
        due = self.call({"op": "review_due", "days": 30})["result"]
        self.assertIn("c", due)
        self.assertTrue(self.call({"op": "estimate_observe", "category": "x", "minutes": 40})["ok"])
        self.assertEqual(self.call({"op": "estimate_query", "category": "x"})["result"]["n"], 1)

    def test_invalid_hour_is_rejected(self):
        self.assertFalse(self.call({"op": "remind_feedback", "hour": 99, "acted": True})["ok"])

    def test_genius_decide_op_ranks_options(self):
        r = self.call({"op": "genius_decide",
                       "matrix": [[8, 256], [6, 512]],
                       "labels": ["air", "pro"],
                       "criteria": ["battery", "storage"],
                       "weights": [0.5, 0.5], "method": "topsis"})
        self.assertTrue(r["ok"])
        self.assertEqual(r["result"]["winner"], "pro")
        self.assertEqual(r["result"]["ranking"], ["pro", "air"])

    def test_genius_decide_op_defaults_and_errors(self):
        # omitted weights -> equal weighting; omitted method -> wsm
        r = self.call({"op": "genius_decide", "matrix": [[8], [6]],
                       "labels": ["air", "pro"], "criteria": ["battery"]})
        self.assertTrue(r["ok"])
        self.assertEqual(r["result"]["winner"], "air")
        # unknown method -> honest error inside the result, never a crash
        r = self.call({"op": "genius_decide", "matrix": [[1]], "labels": ["a"],
                       "criteria": ["x"], "method": "vibes"})
        self.assertTrue(r["ok"])
        self.assertIn("unknown method", r["result"]["error"])
        # missing required field -> ok:false error envelope
        self.assertFalse(self.call({"op": "genius_decide"})["ok"])

    def test_stdin_main_returns_exit_codes(self):
        out = io.StringIO()
        code = bridge.main(["--state", self.state, "--ledger", self.ledger],
                           stdin_text=json.dumps({"op": "ledger_list"}), out=out)
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out.getvalue())["ok"])
        out = io.StringIO()
        self.assertEqual(bridge.main([], stdin_text="not json", out=out), 1)


if __name__ == "__main__":
    unittest.main()
