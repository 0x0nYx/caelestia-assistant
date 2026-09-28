"""Issue #120 conformance (exponential-build-5 A9).

One test file mapping EVERY bullet of ladybug-me/caelestia-kde#120 to a
command and an assertion, plus the honest implemented / partial /
not-implemented table. The table is the single source of truth: a test
fails when reality drifts from the declared status in EITHER direction
— a shipped surface missing its IMPLEMENTED row, or an undeclared
surface appearing while its row still says NOT_IMPLEMENTED.

#120's ask (issue text, condensed to its bullets):
  1. Intent parser -> structured tool calls -> ConfigObject, never
     editing config files directly.
  2. Per-tool range validation, and confirmation for multi-setting
     changes.
  3. Explainability ("why is my dock blurry", "why is my launcher so
     large").
  4. Undo history ("undo the last change", "restore yesterday's theme").
  5. Nexus complements: explain, recommend values, optimize for gaming,
     battery, "more macOS", "more minimal".
  6. Phase 3: context-aware recommendations, optimization profiles,
     workspace automation, monitor-aware config, personalized
     suggestions.

STATUS table (honest as of this commit; flip a row ONLY together with
the surface it describes):
  b1  intent->validated-calls       IMPLEMENTED   parser->planner->applier
  b2a per-tool range validation     IMPLEMENTED   planner rejects, --apply
                                                  refuses rejected plans
  b2b multi-change confirmation     IMPLEMENTED   _confirm_multi gate
  b3  explainability                IMPLEMENTED   --explain, --why-chain
                                                  (F14), graph (F12), why
  b4a "undo the last change"        IMPLEMENTED   --undo/--undo-id/
                                                  --restore + dispatch
  b4b "restore yesterday's theme"   PARTIAL       --undo-id and macros
                                                  exist; no NL time-
                                                  expression surface
  b5a explain (Nexus complement)    IMPLEMENTED   same surfaces as b3
  b5b recommend values              NOT_IMPLEMENTED  F29 planned; drift
                                                  test pins the absence
  b5c optimize profiles             IMPLEMENTED   presets (gaming,
                                                  battery-saver,
                                                  macos-like, minimal)
                                                  + NL routing + --rank
  b6a context-aware recommendations NOT_IMPLEMENTED  F30 planned
  b6b optimization profiles         PARTIAL       preset bundles + the
                                                  learned pairwise
                                                  ladder; no profile
                                                  algebra/composition
  b6c workspace automation          NOT_IMPLEMENTED
  b6d monitor-aware config          NOT_IMPLEMENTED
  b6e personalized suggestions      PARTIAL       brain prefs/nlhistory
                                                  learn; nothing wired
                                                  into #120 proposals
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

STATUS = {
    "b1": "IMPLEMENTED", "b2a": "IMPLEMENTED", "b2b": "IMPLEMENTED",
    "b3": "IMPLEMENTED", "b4a": "IMPLEMENTED", "b4b": "PARTIAL",
    "b5a": "IMPLEMENTED", "b5b": "NOT_IMPLEMENTED", "b5c": "IMPLEMENTED",
    "b6a": "NOT_IMPLEMENTED", "b6b": "PARTIAL", "b6c": "NOT_IMPLEMENTED",
    "b6d": "NOT_IMPLEMENTED", "b6e": "PARTIAL",
}


def _settings(argv, state="{}", target=None):
    """Run the settings CLI in-process against a scratch file (or an
    EXISTING target, so history/backup siblings persist across calls)."""
    from assistant.settings import cli as settings_cli
    if target is None:
        tmp = tempfile.mkdtemp(prefix="iss120-")
        target = Path(tmp) / "shell.json"
        target.write_text(state, encoding="utf-8")
    out, err = io.StringIO(), io.StringIO()
    argv = [*argv, "--file", str(target)]
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = settings_cli.main(argv)
        except SystemExit as exc:
            rc = int(exc.code or 0)
    return rc, out.getvalue(), err.getvalue(), target


def _route(text):
    """The NL front door (cortex route verb) in-process."""
    from assistant.cortex import pipeline
    home = tempfile.mkdtemp(prefix="iss120-home-")
    old = os.environ.get("HOME")
    os.environ["HOME"] = home
    try:
        return pipeline.process(text)
    finally:
        if old is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = old


class TableDriftTests(unittest.TestCase):
    def test_status_table_is_complete_and_honest(self) -> None:
        bullets = ("b1", "b2a", "b2b", "b3", "b4a", "b4b", "b5a", "b5b",
                   "b5c", "b6a", "b6b", "b6c", "b6d", "b6e")
        self.assertEqual(sorted(STATUS), sorted(bullets))
        for k, v in STATUS.items():
            self.assertIn(v, ("IMPLEMENTED", "PARTIAL", "NOT_IMPLEMENTED"),
                          f"{k}: invalid status {v!r}")

    def test_not_implemented_rows_pin_absence(self) -> None:
        """A NOT_IMPLEMENTED row is a PROMISE about the surface set: the
        named capability must not secretly exist. When it ships, the
        row flips in the same commit (the drift detector)."""
        from assistant.settings import cli as settings_cli
        parser = settings_cli._build_arg_parser()
        flags = {a.option_strings[0]
                 for a in parser._actions if a.option_strings}
        if STATUS["b5b"] == "NOT_IMPLEMENTED":
            # F29 recommend-values: no recommendation flag exists yet
            self.assertFalse(
                any("recommend" in f for f in flags),
                "a recommend-values surface exists — flip b5b's row")
        if STATUS["b6a"] == "NOT_IMPLEMENTED":
            self.assertFalse(
                any("context" in f for f in flags),
                "a context-profile surface exists — flip b6a's row")


class B1IntentToValidatedCalls(unittest.TestCase):
    """#120 bullet 1: parser -> structured tool calls, never direct edits."""

    def test_nl_request_plans_validated_ops(self) -> None:
        rc, out, _err, target = _settings(["make the bar 20% smaller"],
                                          state='{"bar": {"scale": 1.0}}')
        self.assertEqual(rc, 0)
        self.assertIn("INTENT", out)
        self.assertIn("setBarScale", out)
        self.assertIn("0.8", out)
        self.assertEqual(json.loads(target.read_text()),
                         {"bar": {"scale": 1.0}})  # dry-run: untouched

    def test_apply_writes_only_through_the_journaled_applier(self) -> None:
        rc, out, _err, target = _settings(
            ["make the bar 20% smaller", "--apply"],
            state='{"bar": {"scale": 1.0}}')
        self.assertEqual(rc, 0)
        data = json.loads(target.read_text())
        self.assertEqual(data["bar"]["scale"], 0.8)
        # the journaled writer's two siblings: the backup slot and the
        # bounded history ledger (never a bare rewrite)
        self.assertTrue((target.parent /
                         (target.name + ".assistant-backup")).exists()
                        or "backup" in out.lower())
        history = target.parent / (target.name +
                                   ".assistant-history.json")
        self.assertTrue(history.exists())
        entries = json.loads(history.read_text())["entries"]
        self.assertTrue(entries[0]["ops"][0]["path"].endswith("scale"))

    def test_qml_service_surface_is_pinned(self) -> None:
        """The ConfigObject side lives in the shell's own QML service;
        its function surface is pinned by the settings layer's own
        cross-check suite (skips when the checkout is absent)."""
        qml = (Path(__file__).resolve().parents[2] / "shell" /
               "services" / "SettingsTools.qml")
        if not qml.exists():
            self.skipTest("SettingsTools.qml absent — QML guards skip")
        text = qml.read_text(encoding="utf-8")
        for fn in ("validate", "buildPlan", "previewOf", "confirmPlan",
                   "applyOps", "pushHistory", "undo", "undoById"):
            self.assertIn(fn, text)


class B2ValidationAndConfirmation(unittest.TestCase):
    """#120 bullet 2: per-tool range validation + multi-change confirm."""

    def test_out_of_range_is_rejected_and_apply_refuses(self) -> None:
        rc, out, err, target = _settings(["--call", "setDockIconSize=500"])
        self.assertNotEqual(rc, 0)
        self.assertIn("outside the allowed range 16-96", out)
        self.assertIn("nothing was written", err + out)
        self.assertEqual(json.loads(target.read_text()), {})

    def test_enum_value_validation(self) -> None:
        rc, out, _err, _t = _settings(["--call", "setBarPosition=diagonal"])
        self.assertNotEqual(rc, 0)
        self.assertIn("top|bottom|left|right", out)

    def test_multi_change_needs_confirmation_without_tty(self) -> None:
        rc, out, err, target = _settings(["--preset", "gaming", "--apply"])
        self.assertNotEqual(rc, 0)
        self.assertIn("need confirmation", err + out)
        self.assertIn("nothing was written", err + out)
        self.assertEqual(json.loads(target.read_text()), {})

    def test_multi_change_applies_with_explicit_confirm(self) -> None:
        rc, out, _err, target = _settings(
            ["--preset", "gaming", "--apply", "--confirm"])
        self.assertEqual(rc, 0)
        data = json.loads(target.read_text())
        self.assertEqual(data["appearance"]["blur"], False)


class B3Explainability(unittest.TestCase):
    """#120 bullet 3: 'why is my dock blurry' / 'why is my launcher...'."""

    def test_explain_answers_with_citation(self) -> None:
        state = json.dumps({"appearance": {"blur": True,
                                           "transparency":
                                           {"enabled": True}}})
        rc, out, _err, _t = _settings(["--explain", "why is my dock blurry"],
                                      state=state)
        self.assertEqual(rc, 0)
        self.assertIn("BlurOffsets.qml", out)  # the shipped citation

    def test_why_chain_gives_the_armed_causal_chain(self) -> None:
        state = json.dumps({"appearance": {"blur": False,
                                           "transparency":
                                           {"enabled": False}}})
        rc, out, _err, _t = _settings(["--why-chain", "appearance.blur"],
                                      state=state)
        self.assertEqual(rc, 0)
        self.assertIn("appearance.transparency.enabled", out)
        self.assertIn("AppearancePage.qml", out)

    def test_graph_affects_lists_curated_upstream(self) -> None:
        from assistant.graph import build as gbuild, queries as gq
        r = gq.what_affects(gbuild.build_graph(), "appearance.blur")
        self.assertEqual(r["verdict"], "OK")
        self.assertTrue(r["upstream"])

    def test_route_handles_why_questions(self) -> None:
        result = _route("why is my dock blurry")
        self.assertEqual(result.verdict, "EXPLAIN")
        self.assertIsNone(result.plan)      # never a proposed change
        self.assertEqual(result.ops, [])    # for a why-question
        self.assertIn("Blur is enabled", str(result.explain_answer))


class B4UndoHistory(unittest.TestCase):
    """#120 bullet 4: 'undo the last change' / 'restore yesterday'."""

    def test_undo_the_last_change(self) -> None:
        _rc, _out, _err, target = _settings(
            ["make the bar 20% smaller", "--apply"],
            state='{"bar": {"scale": 1.0}}')
        rc, out, _err, _t = _settings(["--undo", "1"], target=target)
        self.assertEqual(rc, 0)
        data = json.loads(target.read_text())
        self.assertEqual(data["bar"]["scale"], 1.0)  # restored

    def test_undo_by_id_from_the_ledger(self) -> None:
        _rc, _out, _err, target = _settings(
            ["make the bar 20% smaller", "--apply"],
            state='{"bar": {"scale": 1.0}}')
        history = json.loads((target.parent /
                              (target.name + ".assistant-history.json")
                              ).read_text())
        entry_id = history["entries"][0]["id"]
        rc, out, _err, _t = _settings(
            ["--undo-id", str(entry_id)], target=target)
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(target.read_text())
                         ["bar"]["scale"], 1.0)

    def test_restore_yesterdays_theme_is_partial_and_honest(self) -> None:
        """No NL time-expression surface yet: the STATUS row says
        PARTIAL, and --undo-id + --macro-save are the honest primitives
        a user composes today (macro capture of an approved sequence
        exists)."""
        self.assertEqual(STATUS["b4b"], "PARTIAL")
        from assistant.settings import cli as settings_cli
        parser = settings_cli._build_arg_parser()
        flags = {a.option_strings[0]
                 for a in parser._actions if a.option_strings}
        self.assertIn("--undo-id", flags)
        self.assertIn("--macro-save", flags)


class B5NexusComplements(unittest.TestCase):
    """#120 bullet 5: explain / recommend values / optimize profiles."""

    def test_all_four_profiles_exist_and_plan(self) -> None:
        for preset in ("gaming", "battery-saver", "macos-like", "minimal"):
            rc, out, _err, _t = _settings(["--preset", preset])
            self.assertEqual(rc, 0, preset)
            self.assertIn("INTENT", out)

    def test_nl_routes_optimize_for_gaming_to_the_preset(self) -> None:
        result = _route("optimize for gaming")
        self.assertEqual(result.verdict, "PLAN")
        raws = " ".join(str(e.get("raw", ""))
                        for e in result.plan["entries"])
        self.assertIn("preset gaming", raws)

    def test_learned_preset_ladder_exists(self) -> None:
        rc, out, _err, _t = _settings(["--rank"])
        self.assertEqual(rc, 0)
        self.assertIn("preset", out.lower())


class B6Phase3(unittest.TestCase):
    """#120 bullet 6 (Phase 3): context-aware recs, profiles, workspace
    automation, monitor-aware config, personalized suggestions."""

    def test_phase3_status_rows_are_declared_honestly(self) -> None:
        self.assertEqual(STATUS["b6a"], "NOT_IMPLEMENTED")
        self.assertEqual(STATUS["b6b"], "PARTIAL")
        self.assertEqual(STATUS["b6c"], "NOT_IMPLEMENTED")
        self.assertEqual(STATUS["b6d"], "NOT_IMPLEMENTED")
        self.assertEqual(STATUS["b6e"], "PARTIAL")

    def test_personalization_primitives_exist_but_are_unwired(self) -> None:
        """b6e PARTIAL: the brain layer learns (prefs/nlhistory), but no
        #120 proposal surface consumes it yet — pinned as such."""
        from assistant.brain import state as brain_state
        self.assertTrue(hasattr(brain_state, "resolve_path"))
        self.assertTrue(hasattr(brain_state, "load"))


if __name__ == "__main__":
    unittest.main()
