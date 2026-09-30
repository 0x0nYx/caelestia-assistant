# Verification — how the claims were checked

Every headline claim in the README and CHANGELOG traces to a method
below. The rule of the house: a claim without a method is marketing.

## Test suite

`python3 -m unittest discover -s . -p "test_*.py"` — 2,501 tests green,
12 skipped (the skips are the opt-in DBus and generative surfaces,
which refuse honestly when their hardware or server is absent).
`python3 -m assistant.hub selfcheck` validates the rule schema, risk
tiers, settings lint rules and the import policy on every run; the
bash gate (`tests/test_assistant.sh`, 13 checks) adds the
process-boundary guarantees the in-process suite cannot see (lazy
imports, no-executor import policy at spawn level, the byte lock).

## The arenas

- **Dev arena** — `python3 -m assistant.hub eval --json` over frozen
  dev sets: routing top-1 0.9556 [0.9111, 0.9889], confident-wrong
  1/95 = 1.5% (target ≤ 2%), nlplan exact 1.0, abstention 1.0,
  calibration ECE 0.0444. Every rate carries a seeded bootstrap
  interval; `assistant/eval/baseline.json` ratchets the floors, and a
  regression fails the suite.
- **Sealed arena** — `eval --sealed` over a set looked at only at
  stage boundaries (six-look limit per suite, looks recorded in the
  build state). Reported as measured on the boundary look of
  2026-09-29: routing top-1 0.7778 [0.7014, 0.8403], top-3 0.8889,
  confident-wrong 13/95 = 13.7%; nlplan exact 0.5366 / tool 0.7073;
  abstention 0.9688; calibration ECE 0.2222.
  **The dev-vs-sealed gap is real and reported, not tuned away** —
  sealed discipline forbids iterating against it. The planned
  response is the sanctioned one: mine new dev items over the missed
  intents via `eval grow`, improve, and spend a fresh sealed look
  after this baseline. Four of the thirteen confident-wrongs target
  tools upstream removed from the registry (sr27/sr128/sr129/sr130,
  dual-reported against both the original and the resync-adjusted
  expectation); the remaining nine are genuine misses that seed the
  next dev items.
- **Calibration** — Brier/ECE re-measured on dev and sealed; the CRF
  vs perceptron comparison reproduces deterministically (Brier 0.0521
  vs 0.1673 on the build fixture, winner CRF) across hash seeds; the
  conformal calibrator's coverage guarantee was re-verified
  empirically on a seeded stream.

## Determinism

Three `PYTHONHASHSEED` values × two interpreters (3.12, 3.13) × seven
surfaces (five arena suites plus two live routes): **byte-identical
output** in all 42 runs (`scripts/stageb3_determinism.py`). The
footprint suite is excluded by design — it measures wall clock and
RSS, which legitimately vary. One real determinism defect was caught
and fixed en route: the router's matched-term evidence iterated a
bare `set`, so hash order decided which evidence line survived the
pipeline's four-line cap; emission is now sorted, with a regression
test.

## Fuzzing

`scripts/stageb2_fuzz.py`: 900 seeded mutations (truncation, type
swaps, unicode injection, brace swaps, huge numbers, null bytes)
across seven import surfaces (settings planner target reader,
environment import, profile parse/compose, history reader, brain
state reader, eval-grow promotion loader, archetype-pack import).
**Zero leaks** outside each surface's documented refusal shapes
(707 honest refusals recorded and classified). Two harness defects
and one product crash were found and fixed during the sweep; the
surfaces now each take their real documented error contract.

## The behavior lock

`scripts/regen_goldens.py` probes 316 read-only hub commands (every
dev routing/abstention/nlplan text, settings planner cards, genius
math/stats/matrix/solve, `do`, the arena suites, accessibility
checks, graph queries, dashboards), each run twice from an isolated
HOME; only byte-identical results are kept, so timing-dependent
surfaces drop out on their own. `scripts/golden_check.py` re-runs all
316 at the bash gate and compares sha256(stdout); the unittest tree
pins manifest integrity (≥ 300 cases, sample files hash-consistent).
The golden probe itself caught the evidence-order defect above and a
`gcd`/`lcm` float-args crash in the math engine — both fixed before
the lock was sealed. Update protocol: regenerate + a reviewed commit
stating the behavior change that justified it.

## Dead code

AST scan of all 388 modules (reference universe = the whole package
including tests; string-literal dispatch respected; `noqa: F401`
honored): 13 unreferenced defs and 92 dead import names removed;
layering audit found **zero upward imports** (no engine imports a CLI
or the hub); the residual exact-duplicate function groups are
deliberate layer isolation, documented in the audit.

## Budgets

Measured on this sandbox (which runs ~2.2–2.5× slower than the
reference 1-vCPU Xeon the gates assume): warm route p50 13.45 ms /
p95 14.45 ms (gate: p50 ≤ 15 ms); cold `--help` 302 ms and RSS
28.6 MB at Stage A on this machine — reference-machine cold calls
measured 105–130 ms against the 250 ms gate; RSS stays well under the
45 MB cap. `assistant.hub doctor` re-probes the budget path on
device, reporting UNAVAILABLE rather than a fake PASS when a probe
cannot run.

## Registry freshness

`gen_adapter --verify` byte-compares the generated registry against
the pinned upstream checkout (dev @ 200ea777, 272 tools — five tools
removed upstream, adopted here with the affected eval expectations
re-scoped honestly). The sealed set's four affected items are
dual-reported rather than silently re-authored; the sealed manifest's
sha256 entries pin its content.

## The mean-pooling experiment (Group E3, 2026-09-30)

The last Group E hypothesis — that a static-embedding channel (mean
pooling of per-token vectors) could back or beat the router's lexical
ranker — was measured on the same 121-item dev arena the shipped
baseline is recorded on, under a decision rule written BEFORE
measuring (adopt only if top1 exceeds the shipped 0.8843 AND p50 fits
the 15 ms budget). Three honest instantiations of "static embedding"
for a stdlib-only repo with no pretrained vectors:

| Variant | top1 (all 121) | top1 (107 routable) | p50 | build |
| --- | --- | --- | --- | --- |
| one-hot mean (= normalized TF / VSM) | 0.5702 | 0.6449 | 0.33 ms | 36 ms |
| tf-idf mean | 0.5785 | 0.6542 | 0.33 ms | 37 ms |
| PPMI-profile mean | 0.3306 | 0.3738 | 0.96 ms | 132 ms |

Shipped router (fused, abstention included): **0.8843**. The best
embedding variant loses by more than 30 points on the arena's own
scoring, and structurally cannot abstain on the 14 honest-refusal rows
(it always names a tool). DECISION: **CUT** — numbers recorded in
`scripts/measure_meanpool.py` (rerunnable). This is the measured
confirmation of RATIONALE.md's BM25-first claim on the current corpus,
not an assumption carried over from it.
