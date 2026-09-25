"""Tests for the second round of brain modules: textmine, linkrec, spellfix,
ghost, journal, rhythm, placement, calibrate, drift, health, dreamtime — and
the service.py / bridge.py wiring that exposes them.
"""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from assistant.brain import (
    calibrate, drift, dreamtime, ghost, health, journal, linkrec, placement,
    rhythm, spellfix, textmine,
)
from assistant.brain import bridge, cli, service
from assistant.brain.graph import Graph


class TextMineTests(unittest.TestCase):
    def test_keywords_favor_distinctive_words(self):
        doc = "the vault has orphan notes and duplicate notes about kubernetes"
        corpus = ["cooking notes about sourdough bread", "cooking notes about pasta"]
        kw = textmine.keywords(doc, corpus, top=5)
        self.assertIn("kubernetes", kw)
        self.assertNotIn("notes", kw[:1])  # common word should not dominate top-1

    def test_summarize_shorter_than_target_returns_everything(self):
        text = "One sentence. Two sentence."
        self.assertEqual(textmine.summarize(text, sentences_out=5),
                         ["One sentence.", "Two sentence."])

    def test_summarize_picks_fewer_sentences_in_order(self):
        text = ("Cats are independent animals. Cats often sleep sixteen hours a day. "
                "The stock market fell sharply today. Cats groom themselves constantly. "
                "Interest rates rose this quarter.")
        out = textmine.summarize(text, sentences_out=2)
        self.assertEqual(len(out), 2)
        # order preserved relative to original text
        positions = [text.index(s) for s in out]
        self.assertEqual(positions, sorted(positions))


class LinkRecTests(unittest.TestCase):
    def test_shared_neighbour_pair_outranks_unrelated_pair(self):
        g = Graph()
        g.add("a", {"hub"})
        g.add("b", {"hub"})
        g.add("c", set())
        notes = {"a": "unrelated text one", "b": "unrelated text two", "c": "totally different"}
        suggestions = linkrec.suggest_links(g, notes, top=5)
        pair_ids = [{s["a"], s["b"]} for s in suggestions]
        self.assertIn({"a", "b"}, pair_ids)

    def test_cold_start_falls_back_to_text_similarity(self):
        g = Graph()
        base = "recipe for sourdough bread with flour and water and a long proofing time"
        notes = {"x": base, "y": base + " plus a pinch of salt at the end"}
        suggestions = linkrec.suggest_links(g, notes, top=5, min_jaccard=0.1)
        self.assertTrue(any(s["via"] == "text_similarity" for s in suggestions))

    def test_already_linked_pair_is_skipped(self):
        g = Graph()
        g.add("a", {"b"})
        notes = {"a": "same same same", "b": "same same same"}
        suggestions = linkrec.suggest_links(g, notes)
        self.assertNotIn({"a", "b"}, [{s["a"], s["b"]} for s in suggestions])


class SpellFixTests(unittest.TestCase):
    def test_flags_rare_near_miss_of_common_word(self):
        texts = ["kubernetes " * 6, "kuberentes cluster notes"]
        idx = spellfix.SpellIndex(common_min=5).build(texts)
        rows = idx.suggest()
        typos = {r["typo"]: r["likely"] for r in rows}
        self.assertEqual(typos.get("kuberentes"), "kubernetes")

    def test_no_suggestions_for_uniform_vocabulary(self):
        idx = spellfix.SpellIndex().build(["apple banana cherry apple banana cherry"])
        self.assertEqual(idx.suggest(), [])


class GhostTests(unittest.TestCase):
    def test_finds_unchecked_box_and_action_line(self):
        notes = {"n1": "- [ ] renew passport\nToDo: call the plumber\nJust a regular line."}
        rows = ghost.find_ghosts(notes, known_task_titles=[])
        lines = {r["line"] for r in rows}
        self.assertIn("renew passport", lines)
        self.assertIn("call the plumber", lines)

    def test_known_task_is_not_flagged_again(self):
        notes = {"n1": "- [ ] renew passport soon"}
        rows = ghost.find_ghosts(notes, known_task_titles=["renew passport soon"])
        self.assertEqual(rows, [])


class JournalTests(unittest.TestCase):
    def test_brier_score_zero_for_perfect_confidence(self):
        entries = {}
        journal.record(entries, "d1", "it will rain", 1.0)
        journal.resolve(entries, "d1", True)
        journal.record(entries, "d2", "it will snow", 0.0)
        journal.resolve(entries, "d2", False)
        self.assertEqual(journal.brier_score(entries), 0.0)

    def test_resolve_unknown_decision_raises(self):
        with self.assertRaises(KeyError):
            journal.resolve({}, "missing", True)

    def test_calibration_curve_buckets_by_confidence(self):
        entries = {}
        for i in range(4):
            journal.record(entries, f"d{i}", "x", 0.9)
            journal.resolve(entries, f"d{i}", i != 0)  # 3/4 correct
        curve = journal.calibration_curve(entries, bins=5)
        self.assertEqual(len(curve), 1)
        self.assertEqual(curve[0]["n"], 4)
        self.assertAlmostEqual(curve[0]["hit_rate"], 0.75)


class RhythmTests(unittest.TestCase):
    def test_detects_skewed_day(self):
        weekdays = [1] * 20 + [0, 2, 3, 4, 5, 6]
        pattern = rhythm.day_of_week_pattern(weekdays)
        top = max(pattern, key=lambda r: r["z"])
        self.assertEqual(top["day"], "Tue")

    def test_notable_filters_small_deviations(self):
        pattern = [{"day": "Mon", "count": 5, "z": 0.1}, {"day": "Tue", "count": 5, "z": 3.0}]
        self.assertEqual(rhythm.notable(pattern, threshold=1.5), [pattern[1]])


class PlacementTests(unittest.TestCase):
    def test_ranks_closest_registry_entry(self):
        registry = [
            {"id": "bar.thickness", "description": "height and thickness of the top bar"},
            {"id": "blur.radius", "description": "background blur radius amount"},
        ]
        ranked = placement.suggest("make my bar thinner", registry)
        self.assertEqual(ranked[0]["id"], "bar.thickness")

    def test_no_match_returns_empty(self):
        registry = [{"id": "x", "description": "completely unrelated words here"}]
        self.assertEqual(placement.suggest("zzz qqq", registry), [])


class CalibrateTests(unittest.TestCase):
    def test_acceptance_rate_reflects_history(self):
        labeled = [{"kind": "tag", "status": "approved"}] * 8 + [{"kind": "tag", "status": "rejected"}] * 2
        rates = calibrate.acceptance_rate(labeled)
        self.assertGreater(rates["tag"]["mean"], 0.7)
        self.assertEqual(rates["tag"]["n"], 10)

    def test_daily_budget_roundtrip_and_reward(self):
        budget = calibrate.DailyBudget()
        budget.reward("more", True)
        budget.reward("less", False)
        restored = calibrate.DailyBudget.from_dict(budget.to_dict())
        self.assertEqual(restored.alpha["more"], budget.alpha["more"])
        self.assertEqual(restored.beta["less"], budget.beta["less"])


class DriftTests(unittest.TestCase):
    def test_detects_added_removed_and_changed(self):
        base = " ".join(f"word{i}" for i in range(60))
        old = {"a": base, "b": "will be removed " + base}
        new = {"a": base, "c": "brand new content entirely different words here"}
        result = drift.diff(old, new)
        self.assertEqual(result["added"], ["c"])
        self.assertEqual(result["removed"], ["b"])
        self.assertEqual(result["changed"], [])

    def test_reworded_item_flagged_as_changed(self):
        old = {"a": "one two three four five six seven eight nine ten"}
        new = {"a": "completely different words now unrelated to before at all"}
        result = drift.diff(old, new, similarity_threshold=0.5)
        self.assertEqual(result["changed"][0]["id"], "a")


class HealthTests(unittest.TestCase):
    def test_orphan_and_stale_score_lower_than_healthy(self):
        healthy = health.score("h", age_days=1, orphan_ids=set(), dup_ids=set())
        unhealthy = health.score("u", age_days=200, orphan_ids={"u"}, dup_ids={"u"})
        self.assertGreater(healthy["score"], unhealthy["score"])
        self.assertTrue(unhealthy["stale"])
        self.assertTrue(unhealthy["orphan"])

    def test_rank_notes_worst_first(self):
        rows = [{"id": "a", "score": 90}, {"id": "b", "score": 10}]
        self.assertEqual([r["id"] for r in health.rank_notes(rows)], ["b", "a"])


class DreamtimeTests(unittest.TestCase):
    def test_not_eligible_on_battery(self):
        self.assertFalse(dreamtime.eligible(idle_minutes=30, on_ac_power=False, cpu_load_percent=5))

    def test_eligible_schedules_within_budget(self):
        jobs = [{"id": "organize", "minutes": 10, "value": 5},
                {"id": "health", "minutes": 10, "value": 8},
                {"id": "drift", "minutes": 10, "value": 1}]
        self.assertTrue(dreamtime.eligible(idle_minutes=30, on_ac_power=True, cpu_load_percent=5))
        chosen = dreamtime.schedule(jobs, budget_min=20)
        self.assertEqual(chosen, ["health", "organize"])


class ServiceAndCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.vault = self.d / "vault"
        self.vault.mkdir()
        (self.vault / "a.md").write_text("kubernetes deploy notes about clusters", encoding="utf-8")
        (self.vault / "b.md").write_text("cooking notes about sourdough bread baking", encoding="utf-8")
        self.state = str(self.d / "state.json")
        self.ledger = str(self.d / "ledger.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_links_suggest_via_service_and_cli(self):
        result = service.links_suggest(str(self.vault), self.ledger, propose=True)
        self.assertIsInstance(result, list)
        out = io.StringIO()
        code = cli.main(["--state", self.state, "--ledger", self.ledger,
                         "links", str(self.vault)], out)
        self.assertEqual(code, 0)

    def test_keywords_and_summarize_via_bridge(self):
        r = bridge.handle({"op": "note_keywords", "vault": str(self.vault), "note_id": "a.md"},
                          state_path=self.state, ledger_path=self.ledger)
        self.assertTrue(r["ok"])
        self.assertIn("kubernetes", r["result"])
        r2 = bridge.handle({"op": "note_summarize", "vault": str(self.vault), "note_id": "a.md"},
                           state_path=self.state, ledger_path=self.ledger)
        self.assertTrue(r2["ok"])

    def test_journal_record_resolve_report_roundtrip(self):
        service.journal_record("d1", "the deploy will work", 0.8, self.state)
        service.journal_resolve("d1", True, self.state)
        report = service.journal_report(self.state)
        self.assertAlmostEqual(report["brier_score"], 0.04)

    def test_placement_propose_writes_ledger_entry(self):
        registry = [{"id": "bar.thickness", "description": "bar height thickness"}]
        ranked = service.placement_propose("make bar thinner", registry, self.ledger, propose=True)
        self.assertEqual(ranked[0]["id"], "bar.thickness")
        pending = service.ledger_list(self.ledger)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["kind"], "placement")

    def test_calibration_report_after_some_decisions(self):
        from assistant.brain.ledger import Ledger
        ledger = Ledger(self.ledger)
        pid1 = ledger.propose("tag", "a.md", {}, "reason", 0.9)
        ledger.decide(pid1, True)
        report = service.calibration_report(self.ledger)
        self.assertIn("tag", report["acceptance_by_kind"])

    def test_health_report_via_service(self):
        rows = service.health_report(str(self.vault))
        self.assertEqual(len(rows), 2)
        self.assertTrue(all("score" in r for r in rows))

    def test_dream_window_via_bridge(self):
        r = bridge.handle({"op": "dream_window", "idle_minutes": 30, "on_ac_power": True,
                           "cpu_load_percent": 5,
                           "jobs": [{"id": "health", "minutes": 10, "value": 5}],
                           "budget_min": 20},
                          state_path=self.state, ledger_path=self.ledger)
        self.assertTrue(r["ok"])
        self.assertTrue(r["result"]["eligible"])
        self.assertEqual(r["result"]["chosen"], ["health"])

    def test_spellcheck_and_ghosts_cli_smoke(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["--state", self.state, "--ledger", self.ledger,
                             "spellcheck", str(self.vault)], out)
        self.assertEqual(code, 0)
        out2 = io.StringIO()
        code2 = cli.main(["--state", self.state, "--ledger", self.ledger,
                          "ghosts", str(self.vault)], out2)
        self.assertEqual(code2, 0)


if __name__ == "__main__":
    unittest.main()
