import io
import json
import random
import tempfile
import unittest
from pathlib import Path

from assistant.brain import anomaly, bandit, duration, forecast, graph, ledger
from assistant.brain import minhash, naive_bayes, planner, priority, srs, survival, vault
from assistant.brain import cli
from assistant.brain.nlp import tokens


class NaiveBayesTests(unittest.TestCase):
    def test_learns_tags_and_ranks_them(self):
        nb = naive_bayes.NaiveBayes()
        nb.train(tokens("kubernetes deploy pods cluster"), ["devops"])
        nb.train(tokens("sourdough flour yeast bake"), ["cooking"])
        nb.train(tokens("docker container image registry"), ["devops"])
        top = nb.rank(tokens("deploy the docker image to the cluster"))[0][0]
        self.assertEqual(top, "devops")

    def test_probabilities_sum_to_one(self):
        nb = naive_bayes.NaiveBayes()
        nb.train(["a"], ["x"])
        nb.train(["b"], ["y"])
        self.assertAlmostEqual(sum(p for _, p in nb.rank(["a"])), 1.0)

    def test_roundtrip(self):
        nb = naive_bayes.NaiveBayes()
        nb.train(["a", "b"], ["x"])
        nb2 = naive_bayes.NaiveBayes.from_dict(nb.to_dict())
        self.assertEqual(nb.rank(["a"]), nb2.rank(["a"]))


class MinHashTests(unittest.TestCase):
    def test_finds_near_duplicate_and_ignores_distinct(self):
        base = " ".join(f"word{i}" for i in range(80))
        docs = {
            "a.md": base,
            "b.md": base + " extra tail here",
            "c.md": " ".join(f"other{i}" for i in range(80)),
        }
        pairs = minhash.near_duplicates(docs, threshold=0.7)
        ids = {(a, b) for a, b, _ in pairs}
        self.assertIn(("a.md", "b.md"), ids)
        self.assertNotIn(("a.md", "c.md"), ids)

    def test_empty_text_is_skipped(self):
        self.assertEqual(minhash.near_duplicates({"e.md": "", "f.md": "!!!"}), [])


class GraphTests(unittest.TestCase):
    def test_pagerank_sums_to_one_and_favors_hub(self):
        g = graph.Graph()
        g.add("a", {"hub"})
        g.add("b", {"hub"})
        g.add("c", {"hub"})
        g.add("hub", set())
        pr = g.pagerank()
        self.assertAlmostEqual(sum(pr.values()), 1.0, places=6)
        self.assertEqual(max(pr, key=pr.get), "hub")

    def test_orphans(self):
        g = graph.Graph()
        g.add("a", {"b"})
        g.add("lonely", set())
        self.assertEqual(g.orphans(), ["lonely"])

    def test_communities_split_disconnected_components(self):
        g = graph.Graph()
        g.add("a", {"b"})
        g.add("b", {"c"})
        g.add("x", {"y"})
        comms = g.communities()
        self.assertEqual(len(comms), 2)
        self.assertIn(["a", "b", "c"], comms)

    def test_links_parse_aliases_and_anchors(self):
        self.assertEqual(graph.links("see [[Alpha|a]] and [[beta#h]]"), {"alpha", "beta"})


class PriorityTests(unittest.TestCase):
    def test_overdue_beats_far_deadline(self):
        m = priority.PriorityModel()
        overdue = m.score(priority.features({"deadline_days": -1, "importance": 0.5, "effort_min": 30}))
        far = m.score(priority.features({"deadline_days": 60, "importance": 0.5, "effort_min": 30}))
        self.assertGreater(overdue, far)

    def test_score_is_probability(self):
        m = priority.PriorityModel()
        for d in (None, -5, 0, 3, 100):
            s = m.score(priority.features({"deadline_days": d, "importance": 1.0, "effort_min": 1}))
            self.assertTrue(0.0 < s < 1.0)

    def test_fit_moves_weights_toward_labels(self):
        # Importance alone predicts approval: the learned importance weight should grow.
        examples = []
        for imp in (0.0, 0.1, 0.9, 1.0) * 10:
            examples.append(([0.5, imp, 0.5], 1 if imp > 0.5 else 0))
        before = priority.PriorityModel().w[1]
        m = priority.PriorityModel().fit(examples)
        self.assertGreater(m.w[1], before)


class DurationTests(unittest.TestCase):
    def test_prior_when_unseen(self):
        est = duration.DurationModel().estimate("writing")
        self.assertEqual(est["n"], 0)
        self.assertAlmostEqual(est["median_min"], 30.0, places=0)

    def test_observations_pull_estimate(self):
        m = duration.DurationModel()
        for _ in range(20):
            m.observe("review", 90)
        self.assertGreater(m.estimate("review")["median_min"], 70)
        self.assertGreater(m.estimate("review")["p80_min"], m.estimate("review")["median_min"])


class PlannerTests(unittest.TestCase):
    def test_knapsack_optimal_small_case(self):
        items = [
            {"id": "a", "minutes": 60, "value": 6.0},
            {"id": "b", "minutes": 60, "value": 5.0},
            {"id": "c", "minutes": 30, "value": 3.0},
        ]
        chosen, value, used = planner.knapsack(items, 90)
        self.assertEqual(sorted(chosen), ["a", "c"])
        self.assertAlmostEqual(value, 9.0)
        self.assertLessEqual(used, 90)

    def test_knapsack_empty_budget(self):
        self.assertEqual(planner.knapsack([{"id": "a", "minutes": 10, "value": 1}], 0), ([], 0.0, 0))

    def test_cpm_critical_path(self):
        tasks = {
            "design": {"minutes": 60, "deps": []},
            "build": {"minutes": 120, "deps": ["design"]},
            "docs": {"minutes": 30, "deps": ["design"]},
            "ship": {"minutes": 10, "deps": ["build", "docs"]},
        }
        s = planner.cpm(tasks)
        self.assertEqual(s["ship"]["ef"], 190)
        self.assertTrue(s["build"]["critical"])
        self.assertFalse(s["docs"]["critical"])
        self.assertEqual(s["docs"]["slack"], 90)

    def test_cpm_detects_cycle(self):
        with self.assertRaises(ValueError):
            planner.cpm({"a": {"minutes": 1, "deps": ["b"]}, "b": {"minutes": 1, "deps": ["a"]}})


class SurvivalTests(unittest.TestCase):
    def test_kaplan_meier_known_values(self):
        # 4 tasks; times 1, 2, 3, 4; completed at 1 and 3, censored at 2 and 4.
        curve = survival.kaplan_meier([1, 2, 3, 4], [True, False, True, False])
        self.assertAlmostEqual(curve[0][1], 3 / 4)
        self.assertAlmostEqual(curve[1][1], 3 / 4 * 1 / 2)

    def test_completion_prob_zero_after_all_events_when_no_survivors(self):
        curve = survival.kaplan_meier([1, 2], [True, True])
        self.assertEqual(survival.completion_prob(curve, 5, horizon=1), 0.0)


class ForecastTests(unittest.TestCase):
    def test_holt_extrapolates_linear_trend(self):
        out = forecast.holt([1, 2, 3, 4, 5, 6], alpha=0.9, beta=0.9, horizon=3)
        self.assertAlmostEqual(out[0], 7.0, delta=0.2)
        self.assertGreater(out[2], out[0])

    def test_kalman_converges_to_constant(self):
        k = forecast.Kalman1D(q=0.001, r=0.5, x0=0.0)
        for _ in range(60):
            x = k.update(10.0)
        self.assertAlmostEqual(x, 10.0, delta=0.5)


class SrsTests(unittest.TestCase):
    def test_good_grows_stability_and_again_shrinks_it(self):
        c = srs.new_card()
        good = srs.review(c, 3, elapsed_days=1.0)
        self.assertGreater(good["S"], c["S"])
        again = srs.review(good, 1, elapsed_days=1.0)
        self.assertLess(again["S"], good["S"])

    def test_retrievability_at_stability_is_ninety_percent(self):
        self.assertAlmostEqual(srs.retrievability(5.0, 5.0), 0.9)

    def test_due_when_retrievability_drops(self):
        self.assertTrue(srs.due({"S": 2.0, "D": 5.0}, now_elapsed=10.0))
        self.assertFalse(srs.due({"S": 30.0, "D": 5.0}, now_elapsed=1.0))

    def test_rejects_bad_rating(self):
        with self.assertRaises(ValueError):
            srs.review(srs.new_card(), 7)


class BanditTests(unittest.TestCase):
    def test_learns_preferred_hour(self):
        b = bandit.HourBandit()
        for _ in range(80):
            b.reward(9, acted=True)
            b.reward(15, acted=False)
        rng = random.Random(0)
        picks = [b.choose(allowed=[9, 15], rng=rng) for _ in range(200)]
        self.assertGreater(picks.count(9), picks.count(15))

    def test_respects_allowed_window(self):
        self.assertIn(b_choose_in_window(), range(8, 12))


def b_choose_in_window():
    return bandit.HourBandit().choose(allowed=range(8, 12), rng=random.Random(1))


class AnomalyTests(unittest.TestCase):
    def test_zscore_flags_outlier(self):
        self.assertGreater(anomaly.zscore([10, 11, 9, 10, 10], 30), 5)

    def test_entropy_bits(self):
        self.assertAlmostEqual(anomaly.shannon_bits(["a", "b", "c", "d"]), 2.0)
        self.assertEqual(anomaly.shannon_bits(["a", "a", "a"]), 0.0)

    def test_deferral_flag(self):
        self.assertTrue(anomaly.deferral_flag(3))
        self.assertFalse(anomaly.deferral_flag(2))


class LedgerTests(unittest.TestCase):
    def test_propose_decide_and_labels(self):
        with tempfile.TemporaryDirectory() as d:
            led = ledger.Ledger(Path(d) / "l.json")
            pid = led.propose("tag", "n.md", {"add_tags": ["x"]}, "why", 0.9)
            self.assertEqual(len(led.pending()), 1)
            led.decide(pid, approve=True)
            self.assertEqual(led.pending(), [])
            self.assertEqual(len(led.labeled("tag")), 1)
            with self.assertRaises(ValueError):
                led.decide(pid, approve=False)
            # persisted
            self.assertEqual(ledger.Ledger(Path(d) / "l.json").items[0]["status"], "approved")


class VaultTests(unittest.TestCase):
    def test_parse_front_matter_and_inline_tags(self):
        text = "---\ntags: [Python, ml-basics]\n---\nnotes about #tooling and a#notatag"
        self.assertEqual(vault.parse_note(text), {"python", "ml-basics", "tooling"})


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.vault = self.root / "vault"
        self.vault.mkdir()
        (self.vault / "kube.md").write_text(
            "tags: [devops]\nDeploy the kubernetes cluster pods with docker images and helm charts. [[deploy-notes]]")
        (self.vault / "kube-copy.md").write_text(
            "Deploy the kubernetes cluster pods with docker images and helm charts. [[deploy-notes]]")
        (self.vault / "bread.md").write_text(
            "tags: [cooking]\nSourdough flour yeast bake bread with starter.")
        (self.vault / "untagged.md").write_text(
            "docker images pods cluster deploy release notes")
        (self.vault / "lonely.md").write_text("no links here at all")
        self.state = self.root / "state.json"
        self.led = self.root / "ledger.json"

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        out = io.StringIO()
        code = cli.main(["--state", str(self.state), "--ledger", str(self.led), *args], out=out)
        return code, out.getvalue()

    def test_organize_proposes_and_reports(self):
        code, text = self.run_cli("organize", str(self.vault), "--dup", "0.6")
        self.assertEqual(code, 0)
        self.assertIn("duplicate pairs: 1", text)
        led = ledger.Ledger(self.led)
        kinds = {i["kind"] for i in led.pending()}
        self.assertIn("merge_duplicate", kinds)
        self.assertIn("orphan", kinds)

    def test_tag_command_ranks_devops_for_docker_text(self):
        code, text = self.run_cli("tag", str(self.vault), "docker pods deploy")
        self.assertEqual(code, 0)
        self.assertTrue(text.splitlines()[0].startswith("devops"))

    def test_plan_end_to_end_with_proposals(self):
        tasks = self.root / "tasks.json"
        tasks.write_text(json.dumps([
            {"id": "a", "title": "Write spec", "effort_min": 60, "importance": 0.9, "deadline_days": 1},
            {"id": "b", "title": "Read paper", "effort_min": 90, "importance": 0.3, "deps": ["a"]},
            {"id": "c", "title": "Email", "effort_min": 10, "importance": 0.4, "deadline_days": 30},
        ]))
        code, text = self.run_cli("plan", str(tasks), "--minutes", "100", "--propose", "--top", "2")
        self.assertEqual(code, 0)
        self.assertIn("ranked:", text)
        self.assertIn("critical path:", text)
        self.assertEqual(len(ledger.Ledger(self.led).pending()), 2)
        self.run_cli("ledger", "approve", "1")
        code, text = self.run_cli("ledger", "learn")
        self.assertIn("learned from 1", text)

    def test_estimate_observe_then_query(self):
        self.run_cli("estimate", "observe", "writing", "50")
        _, text = self.run_cli("estimate", "query", "writing")
        self.assertEqual(json.loads(text)["n"], 1)

    def test_review_grade_and_due(self):
        self.run_cli("review", "grade", "card1", "3", "--days", "0")
        _, text = self.run_cli("review", "due", "--days", "30")
        self.assertIn("card1", text)

    def test_remind_feedback_then_choose_in_window(self):
        self.run_cli("remind", "feedback", "10", "1")
        _, text = self.run_cli("remind", "choose", "--allowed", "9-11")
        self.assertIn(int(text.strip()), range(9, 12))

    def test_cull_and_focus_and_forecast(self):
        hist = self.root / "hist.json"
        hist.write_text(json.dumps({
            "durations": [1, 2, 3, 30, 40, 50],
            "observed": [True, True, True, False, False, False],
            "open": [{"id": "old", "age": 45}, {"id": "fresh", "age": 1}],
        }))
        _, text = self.run_cli("cull", str(hist))
        self.assertIn("cull? old", text)
        _, text = self.run_cli("focus", "a,b,a,c,b,d")
        self.assertIn("switch entropy", text)
        _, text = self.run_cli("forecast", "1,2,3,4,5,9")
        self.assertIn("anomaly", text)


if __name__ == "__main__":
    unittest.main()
