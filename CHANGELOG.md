# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
[SemVer](https://semver.org)-flavoured.

## [0.1.0] — 2026-09-29 — initial public baseline

The caelestia-assistant: an offline-first, on-device intelligence layer
for [caelestia-kde](https://github.com/ladybug-me/caelestia-kde), built
as a working answer to issue #120 — how much of what we ask a frontier
LLM can be answered by classical algorithms, deterministic pipelines,
and careful engineering, at zero model cost, on a low-end machine?

This entry consolidates the complete development series into the one
reviewed baseline shipped here. Everything below is in this tree, gated
by one test suite.

### The shape

- Ten cooperating layers (`diagnostics`, `retrieval`, `generative`
  [optional, off], `issues`, `brain`, `cortex`, `settings`, `genius`,
  `scan`, `agent`, plus the opt-in `brain.personal` PKM subpackage),
  each replaceable, each honestly scoped — see the README's layer
  table for the machinery inventory.
- A 272-tool settings registry, every tool carrying its C++
  declaration citation, shipped Nexus control, and live QML reader,
  generated from the upstream checkout by a byte-identity-guarded
  adapter (`gen_adapter --verify`).
- One CLI (`python3 -m assistant.hub`) over every layer, with a
  verbless front door: `caelestia-assist "make my bar thinner"`.

### Routing that learns, and settings that never surprise

- Router: BM25 + PPMI + char-ngram over the registry, AdaGrad online
  logistic, Thompson-sampling strategy bandit, Beta calibration,
  conformal gating, episodic memory, SVD/LSA and
  distributional-lexicon views alongside the default projection
  embedder, CRF and perceptron slot taggers as selectable equals, and
  type-gated cue constraints (polarity verbs gate candidate KIND —
  the D1/D2 fix class).
- Plans: dry-run → plan → consent → backup → bounded undo, always.
  Out-of-range values are rejected, never clamped. Multi-clause
  requests compose into one all-or-nothing plan (D7). Cold-start
  confidences are labeled uncalibrated (D8). Free text that names
  nothing in the registry gets the honest OUT_OF_ONTOLOGY verdict
  (D4/D5). Absence explanations describe what a setting really is
  (D3). The quadratic solver returns all roots with exact radicals,
  answer first (D6).
- Learning that asks first: `eval grow` mines candidate phrases into
  a quarantine that promotes ONLY to caller-named dev sets; taught
  concepts and learned weights ride the same review gates; the
  re-fit ratchet adopts a candidate weight set only on no measured
  regression.

### The broader surface (highlights)

- Composite commands: profile algebra, NL time-expression restore
  ("restore yesterday's theme"), composite what-if previews with
  blast radius and projected-state sanity verdicts.
- Knowledge graph & personalization: shell knowledge graph with
  provenance, noisy config bisect (Bayesian blame + ddmin), causal
  why-chains, taught concepts, context- and habit-aware proposals —
  all landing in one pending-decisions inbox, never auto-applied.
- Environment management: hash-pinned snapshots, portable
  export/import (review-only import), pull-based schedules (nothing
  runs by itself), monitor-aware planning over the upstream forScreen
  override layers, one-pass environment audit.
- Genius: a 17-domain meta-router over stdlib engines (symbolic and
  numeric math with differential verification, bounded DPLL SAT,
  graphs, scheduling, data, text), plus the filesystem second brain.
- Scan: one-pass bounded-memory stream analysis (Aho-Corasick,
  Bloom, Count-Min, HyperLogLog, reservoir, Page-Hinkley, SimHash).
- Accessibility: WCAG 2.x contrast findings with Machado (2009)
  color-vision simulation; a test-enforced plain-output contract; a
  reduced-motion recipe.
- Community: a zero-drift generated tool catalog and shell
  completion, DP-noised cold-start priors, a signed archetype-pack
  import format (review-only by construction), fixture-based tests
  that need no caelestia-kde installation.
- Optional model tiers, both DEFAULT OFF: the loopback-only local
  Ollama client, and a model-assisted drafting path whose drafts are
  validated by the ordinary planner and labeled MODEL_SUGGESTED,
  never executed.

### The generalization groups (A-E)

- **Group A — the dev-vs-sealed gap, attacked honestly.** A
  metamorphic arena auto-generates paraphrase/synonym/unit/typo/
  polarity variants of the dev items with ratcheted floors
  (`eval metamorphic`); the arena grew from 90 to 121 items mined
  from the SEALED baseline look's failure classes (no sealed text
  copied; phrasings new), including items whose honest answer is a
  clarifying question (`expect_verdict: AMBIGUOUS`); a
  confusable-pair clarifier asks the one question that separates
  ranked sibling tools; Dawid-Skene label fusion demotes contested
  routes (demote-ONLY — a correct route was never demoted);
  Venn-Abers intervals cut out-of-sample ECE 0.1038 -> 0.0462.
- **Group B — the shell employee** (`shellkb`, everything it prints
  is SUGGESTED_NOT_EXECUTED): CLI syntax induced from upstream
  completion/man-page FILE TEXT (nothing executed), a PEG-style
  token-by-token command explainer with read-only glob preview and
  destructive-pattern marking, offline how-to retrieval over a
  self-authored CC0 cheat sheet (40 entries; the existing
  time-expression parser handles the temporal half of a question),
  Myers-diff + tree-edit-distance three-way merge for shell.json with
  conflict explanations, and PubGrub-style dependency-conflict
  derivations over a bounded DPLL search.
- **Group C — environment intelligence** (`brain`, proposals only):
  matrix-profile + SAX recurring patterns, PELT changepoints and
  Holt-Winters seasonality ('does this happen every night?'); Hawkes
  burst detection for crash loops and notification storms
  (correlation, never causation); Gaussian-process preference
  learning from pairwise answers (Cholesky, bounded at 50) emitting
  ONE registry-validated setter proposal; user-authored
  event-condition-action rules on a Rete network (the rules FILE is
  the opt-in); Space-Saving heavy hitters + t-digest quantiles for
  disk/log sizing with counts labeled as estimates.
- **Group D — language without an LLM**: template NLG that renders a
  plan as a human writer would ('2 spacing changes and 1 color
  change in the bar' — discourse plan, aggregation, real
  morphology), and extractive QA over the repo docs and user notes
  (BM25 passages + answer-type detection + verbatim spans with
  doc/section/line provenance; a when-answer must carry a date, a
  count a number, a yes/no a polarity; thin evidence says THIN).
- **Group E — the optional model tier, OFF, and honest about its
  size**: the 8B-scale recommendation is WITHDRAWN (it contradicted
  the README's own hardware statement, and the recommended family had
  no Ollama library listing — 404 when checked); the only model role
  this project recommends is a sub-1B reranker over the router's OWN
  candidates (output constrained to candidate names, MODEL_SUGGESTED,
  plan/apply gates untouched; candidates verified live in the Ollama
  library: smollm2:135m/360m, qwen2.5:0.5b, all Apache 2.0); the
  static mean-pooling embedding experiment was measured and CUT —
  best variant 0.5785 vs shipped 0.8843 on the same arena
  (scripts/measure_meanpool.py, rerunnable).

### Safety contract (enforced by AST lint, pinned by tests)

- No executor imports (`subprocess`/`socket`/`ctypes`/… rejected by
  name) — with exactly two quarantined, kill-switched,
  fixed-argument carve-outs (the read-only package probe and the
  DBus surface), each pinned by test and OFF by default.
- Write paths enumerated: gated applier, proposal ledger, journaled
  tidy moves, learned-state JSON. Nothing else writes.
- No training, no embeddings pipeline, no auto-merge of external
  data; every model is a named classical algorithm with a citation.

### Verification (docs/VERIFICATION.md carries the full method)

- The bash gate is 14/14 (module suites, property tests, issue-#120
  conformance, lazy-import check, and the byte-level behavior lock —
  354 golden CLI outputs, byte-identical).
- Dev arena (grown, 121 items): routing top-1 0.8843 with
  confident-wrong 8/83 after demote-only fusion; the metamorphic
  arena ratchets paraphrase/synonym/typo/polarity floors.
- Sealed arena, reported as measured at the stage-boundary look:
  routing top-1 0.7778. The dev-vs-sealed generalization gap is
  real and stated rather than tuned away — sealed discipline forbids
  iterating against it.
- Determinism: 3 hash seeds × 2 interpreters × 7 surfaces,
  byte-identical; the importer fuzz battery runs at every stage
  boundary, zero leaks outside documented refusal shapes.
- Budgets (this sandbox measures ~2.2–2.5× slower than the reference
  1-vCPU machine; reference-machine figures are the gate): warm
  route p50 ≈ 13 ms (≤ 15 ms), cold call within the 250 ms gate on
  reference hardware, RSS under the 45 MB cap.
