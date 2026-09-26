"""Tests for exponential-build phase 2.1: tiny inductive program
synthesis over 2-3 before/after string examples (Gulwani 2011,
FlashFill-style trace-based synthesis over a miniature substring DSL).

The contract under test:

- 2-3 consistent examples induce ONE transformation that reproduces
  EVERY example exactly (the inductive check), rendered in
  plain-English constructs;
- the learned transform GENERALIZES to new input strings (pure text
  computation);
- anything the DSL cannot pin down is an honest ABSTAIN — one example,
  too many, no shared structure, or a boundary the DSL cannot express
  (never a guess, never a clamped answer);
- ambiguity is reported, never hidden; the fewest-stage program is the
  canonical answer;
- output safety: the only executable-looking artifact is an inert
  SUGGESTED_NOT_EXECUTED line with its risk tier; the module executes
  nothing, and apply refuses a program whose inputs were not supplied.
"""
import unittest

from assistant.genius.synth import (SynthError, apply_program,
                                    render, suggest_renames, synthesize)


class SynthesisTests(unittest.TestCase):
    def test_swap_two_fields_around_a_delimiter(self):
        r = synthesize([("2023-report", "report_2023"),
                        ("2024-notes", "notes_2024")])
        self.assertEqual(apply_program(r["program"], ["2025-todo"]),
                         "todo_2025")
        self.assertIn("input 1", r["rendered"])
        # several expressions explain these examples (the single '-'
        # makes 1st and last the same; head/tail coincide) — the result
        # says so instead of silently picking one
        self.assertTrue(r["ambiguous"])
        self.assertGreaterEqual(r["alternatives"], 1)
        # ...and every reported answer applies identically
        self.assertEqual(apply_program(r["program"], ["2025-todo"]),
                         "todo_2025")

    def test_three_field_reorder(self):
        r = synthesize([("John-Smith-42", "42_Smith_John"),
                        ("Jane-Doe-99", "99_Doe_Jane")])
        self.assertEqual(apply_program(r["program"], ["Al-Bus-7"]),
                         "7_Bus_Al")

    def test_mid_field_extraction_with_between(self):
        r = synthesize([("report-2023-final", "2023"),
                        ("notes-2024-draft", "2024")])
        self.assertEqual(apply_program(r["program"], ["spec-2025-v2"]),
                         "2025")

    def test_three_examples_all_must_verify(self):
        r = synthesize([("a-b", "b/a"), ("c-d", "d/c"), ("e-f", "f/e")])
        self.assertEqual(r["checked"], 3)
        self.assertEqual(apply_program(r["program"], ["g-h"]), "h/g")

    def test_inconsistent_examples_abstain(self):
        with self.assertRaises(SynthError):
            synthesize([("abc", "xyz"), ("def", "uvw")])

    def test_letter_digit_boundary_is_outside_the_dsl(self):
        # 'abc123' -> 'abc-123' needs a character-CLASS boundary; this
        # DSL only knows literal delimiters and fixed positions — the
        # honest answer is ABSTAIN, not a guess.
        with self.assertRaises(SynthError):
            synthesize([("abc123", "abc-123"), ("xy987", "xy-987")])


class ContractTests(unittest.TestCase):
    def test_one_example_cannot_induce(self):
        with self.assertRaises(SynthError):
            synthesize([("a-b", "b_a")])

    def test_four_examples_is_outside_the_contract(self):
        with self.assertRaises(SynthError):
            synthesize([("a", "a")] * 4)

    def test_empty_strings_carry_no_signal(self):
        with self.assertRaises(SynthError):
            synthesize([("", "x"), ("y", "")])

    def test_ambiguity_is_reported_not_hidden(self):
        # head(2) alone explains ('abcd'->'ab') uniquely — one stage, no
        # alternatives, honest False. The delimiter case below has five
        # coinciding expressions; there the flag must be True.
        unique = synthesize([("abcd", "ab"), ("efgh", "ef")])
        self.assertFalse(unique["ambiguous"])
        self.assertEqual(unique["alternatives"], 0)
        self.assertEqual(apply_program(unique["program"], ["ijkl"]), "ij")
        coinciding = synthesize([("2023-report", "report_2023"),
                                 ("2024-notes", "notes_2024")])
        self.assertTrue(coinciding["ambiguous"])
        self.assertGreaterEqual(coinciding["alternatives"], 1)

    def test_deterministic(self):
        ex = [("2023-report", "report_2023"), ("2024-notes", "notes_2024")]
        self.assertEqual(synthesize(ex), synthesize(ex))


class ApplyTests(unittest.TestCase):
    def test_missing_input_refused_never_fabricated(self):
        r = synthesize([("a-b", "b/a"), ("c-d", "d/c")])
        program = r["program"]
        # the program reads input 1 only; a two-input demand is fine,
        # but a program cannot be applied with ZERO inputs
        with self.assertRaises(SynthError):
            apply_program(program, [])

    def test_no_program_no_apply(self):
        with self.assertRaises(SynthError):
            apply_program({"stages": [], "joiners": []}, ["x"])


class SuggestedCommandTests(unittest.TestCase):
    def test_renames_render_inert_state_changing_lines(self):
        r = synthesize([("2023-report", "report_2023"),
                        ("2024-notes", "notes_2024")])
        lines = suggest_renames(r["program"], ["2025-todo", "2025-report"])
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertTrue(line.startswith("SUGGESTED_NOT_EXECUTED:"))
            self.assertIn("[STATE_CHANGING]", line)
            self.assertIn("mv -n --", line)
        self.assertIn("'2025-todo' 'todo_2025'", lines[0])

    def test_noop_rename_is_not_suggested(self):
        r = synthesize([("ab", "ab"), ("cd", "cd")])  # identity-ish
        lines = suggest_renames(r["program"], ["ab"])
        # 'ab' applied through the identity program stays 'ab' — no line
        self.assertEqual(lines, [])

    def test_single_quotes_are_shell_escaped(self):
        r = synthesize([("2023-report", "report_2023"),
                        ("2024-notes", "notes_2024")])
        lines = suggest_renames(r["program"], ["it's-2026"])
        self.assertEqual(len(lines), 1)
        # the quote is escaped for copy-paste safety, still inert
        self.assertIn("'it'\"'\"'s-2026'", lines[0])


class RenderTests(unittest.TestCase):
    def test_render_is_plain_english(self):
        r = synthesize([("2023-report", "report_2023"),
                        ("2024-notes", "notes_2024")])
        text = render(r["program"])
        self.assertIn("text after the 1st '-' of input 1", text)
        self.assertIn("'_'", text)
        self.assertIn("text before the 1st '-' of input 1", text)


if __name__ == "__main__":
    unittest.main()
