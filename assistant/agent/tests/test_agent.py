"""agent tests — decomposition, clarification entropy, consent-gated execution."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from assistant.agent import goals, clarify
from assistant.agent.engine import Agent, DISPATCHERS
from assistant.genius.graphs import toposort


class TestGoals(unittest.TestCase):
    def test_compound_split_on_sequence_words(self):
        parts = goals.split_compound("clean my downloads and then make the shell minimal")
        self.assertEqual(len(parts), 2)
        self.assertIn("clean", parts[0])
        self.assertIn("minimal", parts[1])

    def test_plain_and_not_split(self):
        parts = goals.split_compound("disable blur and move the dock left")
        self.assertEqual(len(parts), 1)

    def test_classify_goals(self):
        self.assertEqual(goals.classify_goal("vesktop freezes when I screenshare")["goal"],
                         "diagnose_issue")
        self.assertEqual(goals.classify_goal("make my bar thinner")["goal"],
                         "change_settings")
        self.assertEqual(goals.classify_goal("clean my downloads folder")["goal"],
                         "clean_files")
        self.assertEqual(goals.classify_goal("what is 15% of 80")["goal"],
                         "compute")

    def test_decompose_produces_dag(self):
        g = goals.decompose("why does vesktop freeze when I screenshare")
        edges = []
        for n in g["nodes"]:
            for d in n["depends"]:
                edges.append((d, n["id"]))
        ts = toposort(edges)
        self.assertTrue(ts["is_dag"])
        self.assertEqual(len(ts["order"]), len(g["nodes"]))

    def test_settings_graph_has_consent_gate(self):
        g = goals.decompose("make my bar thinner")
        gates = [n for n in g["nodes"] if n["consent_required"]]
        self.assertTrue(gates)
        self.assertTrue(all(n["risk"] in ("STATE_CHANGING", "PRIVILEGED",
                                          "DESTRUCTIVE")
                            for n in gates))
        # apply must depend on propose
        ids = {n["id"] for n in g["nodes"]}
        apply_nodes = [n for n in g["nodes"] if n["action"].startswith("apply")]
        for a in apply_nodes:
            for d in a["depends"]:
                self.assertIn(d, ids)
        self.assertTrue(g["consent_required"])

    def test_no_privileged_nodes_ever(self):
        for goal, method in goals.GOAL_METHODS.items():
            for step in method:
                self.assertIn(step["risk"], ("READ_ONLY", "STATE_CHANGING"),
                              f"{goal}/{step['id']} invents a privileged node")
                if step["risk"] == "STATE_CHANGING":
                    self.assertTrue(step["consent"])

    def test_decompose_deterministic(self):
        a = goals.decompose("clean my downloads and then make the shell minimal")
        b = goals.decompose("clean my downloads and then make the shell minimal")
        self.assertEqual([n["action"] for n in a["nodes"]],
                         [n["action"] for n in b["nodes"]])
        self.assertTrue(a["compound"])


class TestClarify(unittest.TestCase):
    def test_entropy_picker_ranks_discriminating_question(self):
        picker = clarify.EntropyPicker({"diagnose_issue": 3, "change_settings": 3})
        q = clarify.Question(
            "broken_or_tune",
            "Is something broken, or do you want it tuned?",
            {"broken": {"diagnose_issue": 1.0, "change_settings": 0.0},
             "tune": {"diagnose_issue": 0.0, "change_settings": 1.0}})
        gain = picker.expected_gain(q)
        self.assertGreater(gain, 0.5)  # perfect discriminator on max entropy

    def test_useless_question_not_asked(self):
        picker = clarify.EntropyPicker({"diagnose_issue": 1.0})
        q = clarify.Question(
            "noise", "Is the sky blue?",
            {"yes": {"diagnose_issue": 1.0}, "no": {"diagnose_issue": 1.0}})
        self.assertEqual(picker.expected_gain(q), 0.0)
        self.assertIsNone(picker.best_question([q]))

    def test_settles_after_clear_answer(self):
        picker = clarify.EntropyPicker({"a": 1, "b": 1})
        q = clarify.Question(
            "q1", "Which one?",
            {"one": {"a": 1.0, "b": 0.0}, "two": {"a": 0.0, "b": 1.0}})
        picker.observe(q, "one")
        self.assertTrue(picker.settled())
        self.assertEqual(picker.top(), ("a", picker.belief["a"]))
        self.assertAlmostEqual(picker.belief["a"], 1.0)

    def test_impossible_answer_ignored(self):
        picker = clarify.EntropyPicker({"a": 1, "b": 1})
        q = clarify.Question(
            "q1", "Which one?",
            {"one": {"a": 1.0, "b": 0.0}, "two": {"a": 0.0, "b": 1.0}})
        before = dict(picker.belief)
        picker.observe(q, "nonsense")
        self.assertEqual(picker.belief, before)  # zero-likelihood answer: no update


class TestEngine(unittest.TestCase):
    def test_simulate_executes_nothing(self):
        agent = Agent()
        result = agent.simulate("vesktop freezes and crashes every time")
        self.assertIn("projection", result)
        actions = [s["action"] for s in result["projection"]]
        self.assertIn("diagnose", actions)
        self.assertIn("retrieve_similar", actions)
        # the crucial guarantee: nothing ran
        self.assertEqual(agent._ctx["results"], {})

    def test_execute_read_only_chain(self):
        seen = []
        agent = Agent(consent_fn=lambda node: False,
                      observer=lambda action, outcome: seen.append(outcome))
        result = agent.execute("vesktop freezes and crashes every time")
        statuses = {n["action"]: n["status"] for n in result["nodes"]}
        self.assertEqual(statuses.get("diagnose"), "done")
        self.assertEqual(statuses.get("retrieve_similar"), "done")
        self.assertEqual(statuses.get("fix_plan"), "done")
        self.assertTrue(seen)

    def test_consent_refusal_blocks_downstream(self):
        # tidy goal on a real temp dir: survey is read-only, apply is gated
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "a.txt").write_text("x")
            agent = Agent(consent_fn=lambda node: False,
                          base_ctx={"tidy_root": td})
            result = agent.execute("clean my files")
            by_action = {n["action"]: n for n in result["nodes"]}
            self.assertEqual(by_action["tidy_survey"]["status"], "done")
            self.assertEqual(by_action["tidy_propose"]["status"], "refused")
            self.assertEqual(by_action["tidy_apply"]["status"], "skipped")
            self.assertIn("dependencies", by_action["tidy_apply"]["skip_reason"])

    def test_consent_grant_runs_apply(self):
        calls = []
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "photo.jpg").write_bytes(b"j")
            disp = dict(DISPATCHERS)

            def survey(ctx, params):
                ctx["tidy_root"] = td
                return DISPATCHERS["tidy_survey"](ctx, params)

            disp["tidy_survey"] = survey
            agent = Agent(dispatchers=disp,
                          consent_fn=lambda node:
                          (calls.append(node["action"]) or True),
                          base_ctx={"tidy_root": td})
            result = agent.execute("clean my files")
            by_action = {n["action"]: n for n in result["nodes"]}
            self.assertEqual(by_action["tidy_apply"]["status"], "done")
            self.assertIn("tidy_propose", calls)
            self.assertIn("tidy_apply", calls)

    def test_failed_node_skips_dependents_not_graph(self):
        disp = dict(DISPATCHERS)

        def boom(ctx, params):
            raise RuntimeError("engine hiccup")

        disp["diagnose"] = boom
        agent = Agent(dispatchers=disp, consent_fn=lambda n: False)
        result = agent.execute("vesktop freezes and crashes every time")
        by_action = {n["action"]: n for n in result["nodes"]}
        self.assertEqual(by_action["diagnose"]["status"], "failed")
        self.assertEqual(by_action["fix_plan"]["status"], "skipped")
        # independent branch still completed
        self.assertEqual(by_action["retrieve_similar"]["status"], "done")

    def test_observer_receives_outcomes(self):
        events = []
        agent = Agent(consent_fn=lambda n: False,
                      observer=lambda action, o: events.append((action, o["outcome"])))
        agent.execute("plan my day")
        self.assertTrue(any(o in ("accepted", "refused", "failed", "skipped")
                            for _a, o in events))

    def test_execute_result_serialisable(self):
        agent = Agent(consent_fn=lambda n: False)
        result = agent.execute("what is 2^10")
        json.dumps(result, default=str)  # must not raise

    def test_consent_fn_receives_risk_metadata(self):
        captured = {}

        def consent(node):
            captured.update(node)
            return False

        agent = Agent(consent_fn=consent)
        agent.execute("make my bar thinner")
        self.assertIn("risk", captured)
        self.assertIn("consent_required", captured)


if __name__ == "__main__":
    unittest.main()
