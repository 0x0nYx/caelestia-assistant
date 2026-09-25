# assistant.genius — the universal local intelligence layer (no LLM)

Fifteen algorithm modules and one router that make the assistant able to
*do* any kind of task on the shell — calculate, prove, decide, analyze,
summarize, forecast, mine, decompose, reflect — using classical, auditable
algorithms only. **No language model, no network, no executor, no pip
dependencies.** It is the extension of issue #120's core interaction to
every domain: the assistant proposes and explains, the human decides.

```bash
caelestia-assist do "what is 15% of 80"            # the front door
caelestia-assist do "solve x^2 - 2 = 0"
caelestia-assist do "is (p and q) -> (p or r) a tautology"
caelestia-assist do "sentiment of: this update is terrible"
caelestia-assist do "how do i fix the flaky test"
python3 -m assistant.genius --help                   # direct domain access
```

## The map

| Module | What it holds | Representative algorithms |
|---|---|---|
| `mathengine.py` | expression engine | precedence-climbing parser; rule-based **symbolic differentiation**; **bisection / Newton-Raphson / secant** root finding; **trapezoid / Simpson / adaptive Simpson** quadrature; **Euler + RK4** ODEs; **Taylor series** via repeated symbolic diff; **Lagrange + Newton divided-difference** interpolation |
| `linalg.py` | matrix algebra | Gaussian elimination with partial pivoting; determinant, inverse, rank, RREF; **power iteration** (dominant eigenpair — reused by AHP); **least squares** via normal equations |
| `probability.py` | chance | Bayes chains (single, multi-hypothesis, sequential); combinatorics (stars & bars, Catalan, derangements); distributions (binomial, Poisson, geometric, hypergeometric, exponential, normal with **Wichura AS241 quantile**); **Monte Carlo with antithetic variates**; **Markov chains** — stationary distribution, absorbing-chain fundamental matrix |
| `stats.py` | statistics | **regularized incomplete gamma and beta** (series + continued fractions — the scipy internals, reimplemented); one/two-sample (pooled + Welch) and paired **t tests** with real p-values; **Mann-Whitney U** (tie-corrected), **Wilcoxon signed-rank**, sign test; **chi-square independence**, **one-way ANOVA**, **Jarque-Bera**; Pearson/Spearman/**Kendall tau**; **OLS regression** with standard errors, t-statistics, adjusted R²; **bootstrap CIs**, **permutation tests**; outliers by IQR / z / MAD; effect sizes (Cohen's d, Hedges' g, odds ratio) |
| `data.py` | tables + series | CSV parsing with type inference and full column profiling; group-by, cross-tab; correlation matrices; moving averages, EWMA, autocorrelation; **Yule-Walker AR(p)** via the **Levinson-Durbin recursion** with forecasting; additive trend/seasonal decomposition; **CUSUM changepoints with a bootstrap significance call**; **k-means (k-means++ seeding)**, agglomerative clustering, silhouette |
| `logic.py` | deduction | propositional parser + truth tables; tautology/contradiction classification; equivalence and entailment; **DPLL SAT** with unit propagation + pure-literal elimination; **forward chaining** with proof traces; **CSP** — backtracking with MRV + forward checking + **AC-3** |
| `baysnet.py` | belief | discrete **Bayesian networks** (exact enumeration inference, diagnostic ranking); **Hidden Markov Models** — forward algorithm + **Viterbi decoding** + next-state prediction; **naive Bayes** with Laplace smoothing and evidence |
| `decision.py` | choice | **WSM/WPM**; **AHP** with consistency ratio (Saaty RI table, eigenvector via power iteration); **TOPSIS**; expected-value decision trees with **EVPI**; **minimax regret**; **Pareto frontier**; **minimax with alpha-beta pruning**; weight **sensitivity swings** |
| `language.py` | text | sentiment with negation/intensifiers/dampeners (VADER-style compound); **six readability formulas** (Flesch, F-K, Fog, SMOG, ARI, Coleman-Liau); **RAKE + YAKE-lite** keywords; entity-lite (dates, IPs, hashes, versions, emails, URLs, money, paths); **extractive QA** over supplied text (who/what/when/where/why/how); query-focused **TextRank summarization**; **language detection** (14-language trigram profiles); a **self-learning centroid classifier** |
| `markov.py` | generation + prediction | order-N Markov text generation with temperature; **n-gram sequence prediction with Katz-style backoff and escape mass**; per-event **surprise (-log2 p)** anomaly detection; template grammars; constrained generation (must-contain / must-not) |
| `sysintel.py` | system (read-only) | shell-history mining (bash/zsh/fish) — frecency, association rules with **lift**, next-command prediction, hour heat; duplicate detection (size shortlist + streamed **SHA-256**); disk hotspot aggregation; **Drain-style log template mining** with z-scored template anomalies; JSON config linting (duplicate keys, nulls, mixed types) |
| `creative.py` | color + ideation | exact **sRGB ↔ OKLab ↔ OKLch** (Björn Ottosson constants); **dE-OK** perceptual distance; **WCAG contrast** with AA/AAA verdicts; harmony palettes (complementary/analogous/triadic/tetradic/split) in OKLch; accent derivation with contrast reasoning; bisociation; tagline grammars |
| `tasks.py` | decomposition | **HTN-lite**: 12 goal archetypes × ordered methods with dependencies, effort priors and a `why` per step; topological scheduling (cycles refused loudly); **critical path (CPM)**; **dependency-aware 0/1 knapsack** for today-fit; blocked/stale/urgent triage with saturating age urgency |
| `metacog.py` | self-knowledge | **ID3-lite rule induction** over your approve/reject history (honest thin-data verdicts); **active learning** — entropy-ranked question selection; coverage map with per-domain acceptance; **leader clustering** of past requests named by top shared terms |
| `meta.py` | the front door | a 16-domain **task router**: word-boundary cue lexicons, structural pattern floors (grammar beats statistics, exactly like the cortex), arithmetic-shape detection, **learned token weights from your feedback**, AMBIGUOUS clarifying questions, honest ABSTAIN, parameter extraction, dispatch |

## How `do` works

```
your text
   │
   ▼
classify(): 16 domains scored by cue lexicon
             + structural boosts (derivative/integral/tautology/solve...)
             + structural penalties (a calculus question is not a sum)
             + learned token weights (from your accept/reject feedback)
   │
   ▼
verdict: ROUTE (margin real) | AMBIGUOUS (asks which) | ABSTAIN (says so)
   │
   ▼
_run_domain(): extracts the parameters the domain needs
               (expressions, number lists, formulas, hex colors, goals)
   │
   ▼
result + evidence + confidence + honest errors, never a crash
```

Every domain that proposes *changes* still goes through the brain's
ledger. The genius layer itself only ever **computes and reports**.

## The self-improvement loop

1. **`genius learn --text "..." --domain X --decision approve`** (or the
   `genius_learn` bridge op) updates per-domain token weights in the
   brain's `state.json` — the same atomic-write path as every other
   learner in the assistant.
2. **`genius report`** reads the ledger back: coverage per kind,
   ID3-induced decision rules over your past approvals, and the
   clusters of things you keep asking about.
3. The cortex delegates: `caelestia-assist chat "what is 15% of 80"`
   routes (settings surface says not-mine) → **genius answers inline**,
   read-only, with its evidence.
4. The shell's sidebar can call the deterministic ops directly: five
   `caelestia_genius_*` tools (math, stats, logic, decide, palette) are
   registered in `AiAssistant.qml`'s existing tool registry and dispatch
   through the JSON bridge — the Ollama model constructs the request, the
   classical algorithms compute the answer (see the sidebar section in
   the top-level README and `assistant/brain/tests/test_ai_assistant_qml.py`
   for the args-parity guards).

## Commands (highlights)

```
genius do "any request"                # classify + dispatch + evidence
genius math "2^10 + sqrt(144)"         # arithmetic with functions
genius solve "cos(x) = x" --method newton --x0 1
genius calc --derivative "sin(x)*x" | --integral "x^2" --a 0 --b 3 | --taylor "exp(x)"
genius stats "3, 9, 12, 1, 44"        # describe + ACF (+ JB when n >= 8)
genius matrix "[[2,1],[1,3]]" --b 4,5 # det/rank/eigen/solve
genius prob --bayes 0.01,0.95,0.05 | --ncr 40,3 | --mc "u1+u2" | --markov '[[.9,.1],[.5,.5]]'
genius logic "(p and q) -> p" | --sat "..." | --equivalent "A | B"
genius decide --matrix '[[8,256],[6,512]]' --labels air,pro --criteria battery,storage --weights .5,.5 [--method topsis|ahp|pareto|regret]
genius tree '{"type":"choice","children":[...]}'        # expected value
genius data --csv file.csv [--profile|--groupby city:salary:mean|--corr]
genius data --series "10,12,13,11,14" [--forecast 5|--changepoints|--cluster 2]
genius text "..." [--sentiment|--readability|--keywords|--entities|--language]
genius qa "who made caelestia" --from-file doc.txt
genius summarize --file doc.txt --query "what is it built with"
genius classify "text" --train examples.txt           # lines of 'text|label'
genius palette "#3b7dd8" --harmony triadic            # OKLch palettes
genius palette "#777777" --contrast "#ffffff"         # WCAG ratios
genius gen --name 5 | --tagline "second brain" | --corpus notes.txt | --ideas "memory"
genius sys --duplicates ~/Downloads | --disk /var | --logs build.log | --lint shell.json
genius history ~/.bash_history                        # mining, read-only
genius plan "learn rust" --fit 120                    # HTN + today-fit
genius report                                         # self-reflection
genius learn --text "..." --domain math_eval --decision approve
```

## JSON bridge ops (for QML / scripts)

```
{"op": "genius_do", "text": "..."}            # classify + run
{"op": "genius_math", "expr": "2^10"}         # allow-listed capability calls
{"op": "genius_stats", "numbers": [...]}
{"op": "genius_logic", "formula": "p or not p"}
{"op": "genius_decide", "matrix": [[8,256],[6,512]], "labels": ["air","pro"], "criteria": ["battery","storage"], "weights": [0.5,0.5], "benefits": [true,false], "method": "topsis"}
{"op": "genius_palette", "hex": "#3b7dd8", "harmony": "triadic"}
{"op": "genius_plan", "goal": "fix the flaky test"}
{"op": "genius_sentiment", "text": "..."}
{"op": "genius_summarize", "text": "...", "query": "..."}
{"op": "genius_learn", "text": "...", "domain": "math_eval", "accepted": true}
{"op": "genius_report"}
```

`_genius_safe` dispatches over an explicit allow-list of (module, function)
pairs — the bridge can never be pointed at arbitrary code. `genius_decide`
rides the same allow-list through `decision.compare`, the one-entry method
dispatcher (wsm | wpm | topsis | pareto | regret) shared with the CLI's
`genius decide`; `ahp` stays CLI-only because its pairwise input shape
differs from the decision-matrix ops.

## Safety posture (inherited, not renegotiated)

- **stdlib-only**, enforced by the same AST import scan as the rest of
  the assistant (`csv` was the one addition to the allow-list — a
  read-only parser).
- **No executor, no network, no writes** anywhere in the package: the
  only write is `genius learn`, which touches the brain's own state
  file through its existing atomic path.
- **Honest verdicts**: AMBIGUOUS asks which domain you meant; ABSTAIN
  says so plainly; execution errors are reported with hints, never
  swallowed, never crashed.
- **Evidence on every answer**: p-values, iteration traces, matched
  terms, proof steps, consistency ratios — the assistant shows its work.
- The tests pin textbook values (the rain/sprinkler posterior 0.3577,
  Wichura's 1.959964, the Wikipedia HMM decode, WCAG 21:1) so the
  numbers stay honest as the code evolves.

## Tests

```bash
python3 -m unittest discover -s assistant/genius/tests   # 161 tests
```

Covers every module's algorithms against known values, the routing
matrix, AMBIGUOUS/ABSTAIN behavior, the learning loop, bridge ops,
cortex delegation, import-policy cleanliness, and sampled regressions
of the pre-existing layers.
