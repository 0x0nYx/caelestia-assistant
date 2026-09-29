# The Cortex Layer — learned intelligence, no LLM

The cortex package is the assistant's **learned routing and reasoning layer**:
it takes any natural-language request and decides what the assistant should do
about it — using classical, auditable machine learning instead of a language
model. It is the intelligence half of issue #120's architecture; the existing
deterministic spine (planner validation, single-writer applier, ledger
approve/reject) remains the safety half, unchanged.

```
user phrase
   │
   ▼
session.py          anaphora / ellipsis / clarification answers
   │
   ▼
compound.py         "disable blur and move the dock left" -> clauses
   │
   ▼
router.py           rank ALL registry tools + presets + coarse surfaces
   │                 (BM25+ lexical, PPMI semantic, char-ngram fuzzy,
   │                  frozen-noun grammar, pattern floors, cue-kind
   │                  agreement, name-atom coverage)
   ▼
pipeline.py         cues -> ops -> settings.planner (validation, ranges)
   │
   ▼
{ PLAN, QUESTION, ABSTAIN, EXPLAIN, UNDO, LIST, INERT, DELEGATE }
   │
   ▼  (only ever via the existing gates)
chat y/N ──► applier.apply ──► history/undo ──► learn.py observes the outcome
```

## Why this beats a frozen grammar (and where it deliberately doesn't)

The frozen grammar of `settings/parser.py` covers 18 hand-verified tools and
honestly refuses everything else. The cortex extends addressability to every
registry tool (272 at this writing — tools.json is the count's home) plus
presets, explain, undo, history, and the other layers
(diagnose / search / brain / issue) — mechanically:

- every tool's **name atoms** (`setGreeterMorningStart` → "greeter morning
  start"), path segments, group, enum values, and (for the core 18) its frozen
  nouns become addressable vocabulary;
- a seeded **domain lexicon** maps user words onto registry vocabulary
  ("see-through" → transparency, "gaps" → spacing);
- **typo correction** (unique edit-distance-1 matches only) and **stemming**
  make the match robust;
- two **deterministic structural layers** (pattern floors and cue-kind
  agreement) keep grammar beating statistics, so a why-question can never
  lose to a coincidental noun overlap.

The router **agrees with the frozen parser top-1 on every phrase the parser
can parse** (pinned by `RouterParserAgreementTests`); it only adds coverage
where the parser says NO_INTENT.

## The algorithms (every one real, named, and stdlib-only)

| Where | Algorithm |
|---|---|
| `lexicon.stem` | domain-reduced Porter suffix stripping (idempotent rule set) |
| `lexicon.levenshtein` | two-row DP edit distance with bounded early exit |
| `lexicon.jaro_winkler` | Jaro similarity + Winkler prefix boost |
| `lexicon.ngram_similarity` | character 3-gram cosine (compound-name matching) |
| `vectorize.TfidfIndex` | Okapi **BM25+** (delta lower-bound, k1/b tuned) |
| `vectorize.PpmiEmbedder` | **PPMI** co-occurrence matrix + **Achlioptas sparse random projection** (Johnson–Lindenstrauss), sublinear-tf text embedding — the "poor man's word2vec" |
| `router` | hybrid scoring + softmax-with-temperature + margin-based honest verdicts |
| `router` typo fix | unique-candidate bounded Levenshtein correction |
| `compound` | conjunction/contrast clause segmentation with content guards |
| `session` | anaphora/ellipsis resolution + ordinal/yes/no answer grammar |
| `nlhistory` | number-words/time-window grammar + recency/scope resolution |
| `memory` | Ebbinghaus-style exponential decay recall, market-basket **lift** co-change analysis, hour/weekday habit histograms |
| `learn.OnlineLogistic` | **AdaGrad** online logistic regression over router features |
| `learn.Calibration` | Beta-Binomial posterior acceptance per confidence bucket |
| `learn.CortexLearner` | **Thompson sampling** bandit over routing strategies (reuses brain's NamedBandit), acceptance-rate drift report |
| `corpus` | deterministic paraphrase generation — self-supervised training data with no LLM |

## The self-learning loop

Every routed request whose outcome the assistant can observe feeds three
learners (persisted in the brain's `state.json`, same atomic-write path as
every other learned model):

1. **the router weights** — accepted routes reinforce the signals that found
   them; rejected routes damp them (online logistic regression);
2. **the strategy bandit** — lexical-heavy / semantic-heavy / balanced weight
   profiles compete per query; outcomes reward arms;
3. **the calibration** — Beta-Binomial posteriors per softmax-confidence
   bucket; the pipeline reports the *calibrated* probability, not the raw
   softmax.

The **episodic memory** records every interaction with a forgetting curve,
computes co-change lift, and powers the proactive follow-up ("you usually
also tighten spacing when you shrink the bar"), which surfaces as a ledger
proposal — never an auto-apply.

## Commands

```
caelestia-assist chat                      # conversational REPL (y/N gated applies)
caelestia-assist route "make my bar thinner"   # one-shot, read-only, --json
caelestia-assist cortex report             # learning + memory dashboard
caelestia-assist cortex recall "bar"       # episodic recall
caelestia-assist cortex reset-learning     # weights back to priors
caelestia-assist cortex suggest setBarScale [--apply]   # co-change follow-up
```

JSON bridge ops (for the shell / scripts):

```
{"op": "route", "text": "...", "file": "..."}
{"op": "chat_turn", "text": "...", "session": {...}}       # session round-trips
{"op": "cortex_report"}
{"op": "memory_recall", "query": "...", "k": 10}
{"op": "learn_feedback", "text": "...", "surface": "...", "features": {...},
 "p": 0.6, "outcome": "applied", "strategy": "balanced"}
```

## Safety posture (inherited, not reinvented)

- **Nothing writes from the cortex.** Routing, ranking, planning — all
  read-only. The only write paths remain `settings.applier.apply` (behind
  `--apply` / the chat y/N gate) and the ledger-approved brain bridge.
- **Honest verdicts everywhere.** AMBIGUOUS asks a question with candidates;
  ABSTAIN says no match; NOT_FOUND for scoped undo refuses to fall back to
  undo-the-latest; out-of-range values stay planner-REJECTED, never clamped.
- **Determinism where it matters.** The router is a pure function of
  (text, state); the embedder's random projection is fixed-seed; the strategy
  bandit's RNG is seeded. Learned state changes only through observed
  outcomes.
- **Evidence for every route.** Matched terms, synonym and typo fixes, noun
  hits, pattern hits, and coverage — shown to the user next to the plan.
- **stdlib-only**, enforced by the same ALLOWED_IMPORTS AST scan as the rest
  of the assistant (`caelestia-assist selfcheck`).

## Tests

`python3 -m unittest discover -s assistant/cortex/tests` — 103 tests covering
every module, the router↔parser agreement regression, end-to-end pipeline
plans against temp files, apply/undo round-trips, learning convergence,
persistence round-trips, and the y/N consent gate.

## Round three: conformal honesty (`conformal.py`)

| Where | Algorithm |
|---|---|
| `ConformalCalibrator` | **split-conformal prediction** over accepted-route scores — a verdict at/above the threshold carries a distribution-free guarantee ("routes this confident were right >= 1-alpha of the time historically"); empty calibration says so instead of pretending |
| `query_by_committee` | **active learning**: when the router's weight profiles disagree (score std across strategies), the request is surfaced as a teach-me candidate — one label buys the most information |
| `PageHinkleyDrift` | Page-Hinkley change detection over the acceptance stream (negated-stream variant, so it detects DROPS in your approval rate), latched with an explicit reset |

These compose with the existing learners: the logistic learns the route, the
bandit learns the strategy, the calibration maps softmax to acceptance, and
the conformal layer turns all of it into a statement you can hold it to.

## Drift: Page-Hinkley + ADWIN behind a consensus gate (`adwin.py`)

`PageHinkleyDrift` (conformal.py) was previously defined-and-tested but not
surfaced anywhere. `adwin.py` adds the second detector AND the surface:

| Where | Algorithm |
|---|---|
| `ADWIN` | **Adaptive Windowing** (Bifet & Gavaldà 2007, SIAM SDM — the compressed bucket-list variant: exponential-histogram buckets of (total, variance) over runs of 2^i elements, M=5 per row; cut when two subwindows' means differ beyond the Hoeffding bound with the paper's m = 1/(1/n0+1/n1) effective size, delta=0.002). Mirrors `PageHinkleyDrift`'s update/to_dict/from_dict/reset shape so callers can hold both. Warmup (width < 32) is labelled, never silent |
| `DriftConsensus` / `consensus` | the gate: drift is FLAGGED to the user only when BOTH detectors have alarmed — dual agreement suppresses single-detector false alarms; each detector's own state is always reported individually |
| `CortexLearner.ph_adwin_consensus` | the read-only wiring: the example log's accept/reject stream replayed through both detectors, surfaced in `report()` as `drift_ph_adwin` (beside `drift` and `drift_bocpd`) and rendered by the cortex report — PH itself is unchanged, nothing new is persisted |

## Lexicon-diff sharing: optional Laplace DP on the export (`dp.py`)

The community lexicon-diff export carries exact per-phrase evidence
(`n=4, p=0.86`); an aggregator collecting many users' diffs could
reconstruct one contributor's raw behavior. The opt-in fix:

| Where | Algorithm |
|---|---|
| `dp.laplace_noise` | the **Laplace mechanism** (Dwork, McSherry, Nissim & Smith 2006, "Calibrating Noise to Sensitivity in Private Data Analysis", TCC): noise ~ Laplace(0, b), b = sensitivity/epsilon, sampled EXACTLY by the inverse CDF from one uniform draw of the injected rng — deterministic given the rng |
| `dp.noise_diff` | the noising pass over the export artifact: per-row `n` (sensitivity 1 per phrase event) and `p` (sensitivity 1 worst case) noised; negative counts floored at zero AND counted; `p` clipped to [0,1] AND the clips counted; every row carries a `(dp: epsilon=X)` provenance marker that round-trips through `lexicon_diff.parse` (additive regex group); re-noising an already-noised diff is refused (it would compose epsilon while claiming one); same (diff, epsilon, seed) → byte-identical output |
| `cortex lexicon export --dp [EPSILON] [--dp-seed N]` | the CLI surface; **default behavior byte-identical when the flag is absent** (pinned by test) |

Default epsilon = 1.0 **per export**: per single release a user's
phrase-level contributions are bounded by the export cap
(`lexicon_diff.MAX_PAIRS` = 200 rows; the underlying example log is
capped at `learn.MAX_EXAMPLES` = 500), and one phrase event moves a
row's `n` by 1 / its `p` by at most 1. Composition (Dwork & Roth 2014):
k sequential exports compose to ~k·epsilon — the export is
user-initiated and manual, so the practical bound is how often you
export. Honest boundary: row **presence is exact** (only counts/rates
are noised) — the guarantee is labeled *noised-evidence DP, not full
row-level DP*; the opt-in `presence_keep` subsampling amplifies but
does not change that label. The default seed derives from the diff's
content id (reproducible noise — NOT independent across exports; the
tradeoff is stated in `cortex/dp.py`'s docstring, which the tests pin).

## Predictive power advice (`power_advisor.py`)

Holt 1957 trend extrapolation over caller-supplied battery/thermal
series, with the internals the forecast library discards: one-step
residuals (for the iid-residual normal interval — an indication, never
a calibrated prediction interval, and labeled as such), the final
level/trend pair, and an Adams & MacKay 2007 BOCPD changepoint check
over the series' first differences (a drain-regime change is a mean
shift in the deltas). The point forecasts are cross-checked
byte-identical against `brain/forecast.py::holt` by test — the
duplicated recursion cannot drift.

Two calibration choices are load-bearing and documented in the module:
the BOCPD observation variance is estimated from the pre-shift
baseline half (the default whole-series estimate is contaminated by
the shift it should reveal — a blatant −2→−20 drain step scores
p=0.17 under the default and p=1.0 under the baseline estimate), and
the thermal variance floor is 1 °C² because a sharper floor makes the
Gaussian underflow on gross shifts and MISS them entirely.

Every suggestion is an inert `SUGGESTED_NOT_EXECUTED` string naming
the preset preview command (`settings --preset battery-saver` /
`--preset minimal`) — this module applies nothing; charging series get
"no drain estimate" instead of a negative time-to-low; already-past
thresholds are said out loud; thin series (<4 samples) abstain;
out-of-range values are refused. Surface: `caelestia-assist cortex
power --battery P,P,... --thermal M,M,...` (read-only).

## Opt-in engine telemetry (`engine_telemetry.py`)

Coverage/accuracy-only metrics over the router's own bounded example
log — per surface: n, decided, accepted, rejected, coverage
(decided/n), accuracy (accepted/decided). Abstains and clarifies
count in n but NOT in decided (abstaining is the honest no-answer,
not a wrong one); a surface with zero decided turns carries NO
accuracy claim ("-", never 0.0). Nothing else can leave the machine
through this module — no text, no phrases, no features — by
construction.

The opt-in export rides the B4 Laplace mechanism (`dp.py`): n and
decided noised at sensitivity 1 (floored at 0), rates noised and
clipped to [0,1], every row carrying an explicit `(dp: epsilon=X)`
marker, and the exact vs noised artifacts are byte-distinct with
different headers. Composition: k exports ~ k·epsilon (Dwork & Roth
2014). Surface: `caelestia-assist cortex telemetry [--export]
[--dp EPSILON] [--dp-seed N]`, behind the capability manifest's
`engine_telemetry` flag (read-only, ON by default, one file edit to
disable).
