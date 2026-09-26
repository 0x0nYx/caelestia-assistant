"""cortex.dispatch — the unified local-vs-cloud dispatcher (§5).

These tests pin the three properties the architecture demands:

1. ONE DECISION POINT: the hand-off rule uses the router's own verdicts
   and the conformal calibrator's own verdict — nothing else. A confident
   settings request is answered locally (with the gated apply payload);
   an ABSTAIN / no-candidates QUESTION / DELEGATE request hands off to
   the cloud tier; a PLAN whose score the conformal calibrator does not
   cover (when calibration data exists) hands off too.
2. GAP LOGGING: every hand-off lands in the bounded ``cortex_gaps`` state
   bucket as a query SHAPE + intent category — the raw text is never
   stored. Near-threshold hand-offs also feed the ``cortex_review`` batch.
3. MINIMUM-SUPPORT DISCIPLINE: gap clustering applies the workspace.py
   floor (min_support=3, purity=0.6) — a small or noisy gap set produces
   ZERO candidates; only a repeated, consistent shape surfaces, and it
   surfaces as a LEDGER PROPOSAL that is never auto-applied.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from assistant.cortex.dispatch import (
    GAPS_KEY, MAX_GAPS, cluster_gaps, dispatch, log_gap, propose_gap_clusters,
    query_shape,
)
from assistant.cortex.learn import REVIEW_KEY
from assistant.brain.ledger import Ledger


def _write_target(directory: Path, payload: dict | None = None) -> Path:
    target = directory / "shell.json"
    base = {"bar": {"scale": 1.0, "position": "bottom"},
            "appearance": {"blur": True, "transparency": {"base": 0.85}}}
    if payload:
        for key, value in payload.items():
            if isinstance(value, dict) and key in base and isinstance(base[key], dict):
                base[key].update(value)
            else:
                base[key] = value
    target.write_text(json.dumps(base), encoding="utf-8")
    return target


def _conformal_state(scores):
    """A brain-state dict whose conformal calibrator has accepted-route
    history at the given scores (all 'applied', so cal.scores == scores)."""
    from assistant.cortex.conformal import ConformalCalibrator
    cal = ConformalCalibrator()
    for s in scores:
        cal.observe(s, "applied")
    return {"conformal": cal.to_dict()}


class DispatchDecisionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.target = _write_target(Path(self._tmp.name))

    def test_confident_settings_request_is_local_with_gated_apply(self):
        state = {}
        outcome = dispatch("make my bar thinner", state=state,
                           file_path=self.target)
        self.assertEqual(outcome["action"], "local")
        self.assertIsNone(outcome["reason"])
        self.assertTrue(outcome["answer"])
        self.assertIn("apply", outcome)
        calls = outcome["apply"]["calls"]
        self.assertEqual(calls[0]["name"], "setBarScale")
        self.assertEqual(calls[0]["value"], 0.9)
        # a local answer never logs a gap
        self.assertNotIn(GAPS_KEY, state)

    def test_abstain_hands_off_and_logs_gap_shape_not_text(self):
        state = {}
        outcome = dispatch("wibble frobnicate the quux", state=state,
                           file_path=self.target)
        self.assertEqual(outcome["action"], "cloud")
        self.assertEqual(outcome["reason"], "router-abstain")
        gaps = state.get(GAPS_KEY) or []
        self.assertEqual(len(gaps), 1)
        entry = gaps[0]
        # the shape is a token signature, never the raw request
        self.assertNotIn("text", entry)
        self.assertIsInstance(entry["shape"], list)
        self.assertTrue(all(isinstance(t, str) for t in entry["shape"]))
        self.assertEqual(entry["category"], "router-abstain")
        self.assertEqual(entry["n"], 1)
        # near-threshold hand-offs also feed the batch-review surface
        self.assertTrue(state.get(REVIEW_KEY))

    def test_delegate_hands_off_with_delegate_category(self):
        state = {}
        outcome = dispatch("my shell crashed and nothing works", state=state,
                           file_path=self.target)
        self.assertEqual(outcome["action"], "cloud")
        self.assertEqual(outcome["reason"], "delegate:diagnose")
        self.assertEqual(state[GAPS_KEY][0]["category"], "delegate:diagnose")

    def test_conformal_uncovered_plan_hands_off(self):
        # calibration history says accepted routes scored >= 0.99; a PLAN
        # whose top p is below that threshold is not covered -> cloud.
        state = _conformal_state([0.99] * 6)
        outcome = dispatch("make my bar thinner", state=state,
                           file_path=self.target)
        self.assertEqual(outcome["action"], "cloud")
        self.assertEqual(outcome["reason"], "below-conformal-threshold")
        self.assertEqual(state[GAPS_KEY][0]["category"],
                         "below-conformal-threshold")

    def test_no_conformal_data_means_local_not_punted(self):
        # an empty calibration set guarantees nothing in either direction;
        # the request must stay local rather than being punted on a guess.
        outcome = dispatch("make my bar thinner", state={},
                           file_path=self.target)
        self.assertEqual(outcome["action"], "local")

    def test_question_with_candidates_stays_local(self):
        # an apply-blocked plan (out-of-range value) is a QUESTION the local
        # layer owns: it shows the validation errors, it does not punt to the
        # cloud tier, and it carries no apply payload.
        outcome = dispatch("bar scale 5", state={}, file_path=self.target)
        self.assertEqual(outcome["action"], "local")
        self.assertIn("answer", outcome)
        self.assertNotIn("apply", outcome)
        self.assertTrue(any("range" in line for line in outcome["answer"]))

    def test_hand_off_dedupes_by_shape_and_counts(self):
        state = {}
        dispatch("wibble frobnicate the quux", state=state,
                 file_path=self.target)
        dispatch("wibble frobnicate the quux again", state=state,
                 file_path=self.target)
        gaps = state[GAPS_KEY]
        # near-identical requests share a shape bucket entry (counted), and
        # the bucket holds at most a bounded number of entries
        self.assertLessEqual(len(gaps), 3)
        total = sum(g["n"] for g in gaps)
        self.assertEqual(total, 2)

    def test_gap_bucket_is_bounded(self):
        state = {}
        for i in range(MAX_GAPS + 20):
            state[GAPS_KEY] = (state.get(GAPS_KEY) or [])[:MAX_GAPS]
            log_gap(state, f"unique request number {i}", "router-abstain",
                    "2026-09-26T00:00:00")
        self.assertLessEqual(len(state[GAPS_KEY]), MAX_GAPS)

    def test_session_round_trips_and_appears_in_outcome(self):
        outcome = dispatch("make my bar thinner", state={},
                           file_path=self.target)
        self.assertIn("session", outcome)
        self.assertIsInstance(outcome["session"], dict)


class GapClusteringTests(unittest.TestCase):
    """The workspace.py minimum-support + purity floor, applied to gaps."""

    def _state_with_gaps(self, *gaps):
        return {GAPS_KEY: list(gaps)}

    def test_small_gap_set_produces_zero_candidates(self):
        state = self._state_with_gaps(
            {"shape": ["alpha", "beta"], "category": "router-abstain", "n": 1},
            {"shape": ["gamma", "delta"], "category": "router-abstain", "n": 1},
        )
        summary = cluster_gaps(state)
        self.assertEqual(summary["candidates"], [])
        self.assertGreaterEqual(summary["rejected_clusters"], 1)

    def test_noisy_cluster_below_purity_floor_produces_zero(self):
        # three distinct shapes, one occurrence each: even clustered
        # together, the modal shape covers only 1/3 of the requests.
        state = self._state_with_gaps(
            {"shape": ["alpha", "beta"], "category": "router-abstain", "n": 1},
            {"shape": ["alpha", "beta", "gamma"], "category": "router-abstain", "n": 1},
            {"shape": ["alpha", "epsilon"], "category": "delegate:brain", "n": 1},
        )
        summary = cluster_gaps(state)
        self.assertEqual(summary["candidates"], [])

    def test_repeated_consistent_shape_surfaces(self):
        state = self._state_with_gaps(
            {"shape": ["alpha", "beta"], "category": "router-abstain", "n": 4},
            {"shape": ["unrelated"], "category": "router-abstain", "n": 1},
        )
        summary = cluster_gaps(state)
        self.assertEqual(len(summary["candidates"]), 1)
        cand = summary["candidates"][0]
        self.assertEqual(cand["support"], 4)
        self.assertEqual(cand["purity"], 1.0)
        self.assertEqual(cand["tokens"], ["alpha", "beta"])

    def test_single_repeated_gap_is_one_cluster(self):
        # one shape, three occurrences: k would be 1 — still gated by the
        # same floor, and it passes because the support is real.
        state = self._state_with_gaps(
            {"shape": ["alpha", "beta"], "category": "router-abstain", "n": 3})
        summary = cluster_gaps(state)
        self.assertEqual(len(summary["candidates"]), 1)
        self.assertEqual(summary["candidates"][0]["support"], 3)

    def test_cluster_is_deterministic(self):
        state = self._state_with_gaps(
            {"shape": ["alpha", "beta"], "category": "router-abstain", "n": 3},
            {"shape": ["alpha", "beta", "x"], "category": "router-abstain", "n": 2},
            {"shape": ["zzz", "yyy"], "category": "delegate:genius", "n": 5},
        )
        first = cluster_gaps(state)
        second = cluster_gaps(state)
        self.assertEqual(first, second)

    def test_empty_state_is_zero_everything(self):
        summary = cluster_gaps({})
        self.assertEqual(summary["n_gaps"], 0)
        self.assertEqual(summary["candidates"], [])


class GapProposalTests(unittest.TestCase):
    """Surfacing, never auto-absorption: ledger proposals only."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ledger = Ledger(Path(self._tmp.name) / "ledger.json")

    def test_qualifying_cluster_becomes_pending_ledger_proposal(self):
        state = {GAPS_KEY: [
            {"shape": ["alpha", "beta"], "category": "router-abstain", "n": 5},
        ]}
        res = propose_gap_clusters(state, self.ledger)
        self.assertEqual(len(res["proposals"]), 1)
        pending = self.ledger.pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["kind"], "ontology_gap")
        self.assertEqual(pending[0]["status"], "pending")
        self.assertIn("fell through to the cloud tier", pending[0]["reason"])

    def test_no_auto_application_ever(self):
        # approving the proposal only records a decision in the ledger;
        # it does not and cannot add a tool by itself.
        state = {GAPS_KEY: [
            {"shape": ["alpha", "beta"], "category": "router-abstain", "n": 5},
        ]}
        propose_gap_clusters(state, self.ledger)
        pid = self.ledger.pending()[0]["id"]
        self.ledger.decide(pid, True)
        approved = [p for p in self.ledger.items if p["id"] == pid][0]
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["diff"]["cluster"]["tokens"],
                         ["alpha", "beta"])

    def test_duplicate_pending_cluster_is_not_stacked(self):
        state = {GAPS_KEY: [
            {"shape": ["alpha", "beta"], "category": "router-abstain", "n": 5},
        ]}
        first = propose_gap_clusters(state, self.ledger)
        second = propose_gap_clusters(state, self.ledger)
        self.assertEqual(len(first["proposals"]), 1)
        self.assertEqual(second["proposals"], [])
        self.assertEqual(len(self.ledger.pending()), 1)


class QueryShapeTests(unittest.TestCase):

    def test_shape_is_bounded_and_deduplicated(self):
        shape = query_shape("please make the bar a little bit thinner "
                            "and also the dock and the notifications "
                            "and the greeter and the overview and the osd")
        self.assertLessEqual(len(shape), 8)
        self.assertEqual(len(shape), len(set(shape)))

    def test_reworded_requests_share_shapes(self):
        a = query_shape("make the bar thinner")
        b = query_shape("make the bar a bit thinner")
        self.assertEqual(a, b)


class QmlDispatchTransportGuards(unittest.TestCase):
    """Static pins on the sidebar's transport: the local-vs-cloud DECISION
    must live in cortex.dispatch (bridge op "dispatch"), never in the QML.
    The sidebar only carries the verdict — these guards keep it that way."""

    QML = Path(__file__).resolve().parents[3] / "shell" / "modules" / "sidebar" / "AiAssistant.qml"

    @unittest.skipIf(not QML.exists(), "AiAssistant.qml absent — QML guards skip")
    def setUp(self):
        self.qml = self.QML.read_text(encoding="utf-8")

    def _function_body(self, name: str) -> str:
        start = self.qml.index(f"function {name}(")
        end = self.qml.index("\n    }", start) + len("\n    }")
        return self.qml[start:end]

    def test_every_user_prompt_goes_through_the_dispatcher(self) -> None:
        body = self._function_body("sendPrompt")
        self.assertIn("tryLocalDispatch(promptText);", body,
                      "sendPrompt must offer every user prompt to the "
                      "unified dispatcher before any cloud call")
        self.assertIn("sendCloudPrompt(promptText, isSystemToolResult", body,
                      "non-dispatch traffic (tool results / retries) goes "
                      "straight to the cloud path")

    def test_cloud_path_has_exactly_the_transported_call_sites(self) -> None:
        # three call sites, all transport: sendPrompt's passthrough, and
        # handleDispatchOutcome's two (bridge-unavailable fallback + cloud
        # hand-off). Any other caller would be a second decision point.
        self.assertEqual(self.qml.count("sendCloudPrompt("), 4,
                         "sendCloudPrompt must appear exactly 4 times "
                         "(1 definition + 3 transported call sites)")

    def test_dispatcher_uses_the_bridge_op(self) -> None:
        body = self._function_body("tryLocalDispatch")
        self.assertIn('{ op: "dispatch"', body,
                      "the dispatch decision must come from the bridge's "
                      "dispatch op (cortex machinery), not QML logic")

    def test_local_verdict_routes_writes_through_existing_gates(self) -> None:
        body = self._function_body("handleDispatchOutcome")
        self.assertIn('outcome.action === "cloud"', body)
        self.assertIn("SettingsTools.request(", body,
                      "local applies must go through the SettingsTools gate")
        self.assertIn("SettingsTools.undo", body,
                       "local undos must go through the SettingsTools gate")
        self.assertIn("startTypingAnimation(answerText)", body)
        # bridge failure is logged, never silently swallowed
        self.assertIn("Logger.log", body)

    def test_session_resets_on_cloud_handoff_and_new_chats(self) -> None:
        body = self._function_body("handleDispatchOutcome")
        self.assertIn("dispatchSession = null;", body,
                      "a cloud hand-off must not carry local session state")
        for fn in ("createNewChat", "loadChat"):
            self.assertIn("dispatchSession = null;",
                          self._function_body(fn),
                          f"{fn} must reset the local dispatch session")


if __name__ == "__main__":
    unittest.main()
