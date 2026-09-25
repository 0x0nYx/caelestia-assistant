# assistant.brain — lean intelligence layer

Stdlib-only, no LLM, no network, no executor. Learns from your own decisions
and turns them into proposals. Nothing writes to notes: every change is a
proposal in a ledger until you approve it.

## Modules

| Module | Algorithm | What it answers |
| --- | --- | --- |
| `naive_bayes.py` | Multinomial NB, one class per tag, null-hypothesis class | Which tags fit this note? |
| `minhash.py` | MinHash + LSH banding, Jaccard verification | Which notes are near-duplicates? |
| `graph.py` | Wiki-link graph, PageRank, orphans, label propagation | What is connected, what is isolated, what clusters? |
| `priority.py` | Logistic score over urgency, importance, quickness; fit from approvals | What should I do first? |
| `duration.py` | Bayesian log-normal per category | How long will this actually take (median, p80)? |
| `planner.py` | 0/1 knapsack over minutes; Critical Path Method | What fits today, and what gates the project? |
| `survival.py` | Kaplan-Meier on task age with censoring | Which open tasks are unlikely to ever finish? |
| `forecast.py` | Holt linear trend; 1-D Kalman filter | Where is this series going; what is its smoothed level? |
| `srs.py` | FSRS-inspired stability/difficulty scheduling | When should I review this again? |
| `bandit.py` | Thompson sampling over hour-of-day Beta arms | When do I actually act on reminders? |
| `anomaly.py` | z-score, deferral flag, Shannon entropy of switches | Is this unusual? Is my attention fragmented? |
| `ledger.py` | JSON proposal ledger (pending / approved / rejected) | What is waiting for my decision? |
| `textmine.py` | TF-IDF; TextRank (weighted PageRank over sentences) | Which words define this note? Can you summarize it in N sentences? |
| `linkrec.py` | Adamic-Adar over the link graph; shingle-Jaccard cold-start fallback | Which unlinked notes should probably link to each other? |
| `spellfix.py` | SymSpell-style delete-index, scored against the vault's own vocabulary | Is this rare word actually a typo of a word I use often? |
| `ghost.py` | Checkbox/action-phrase heuristics minus overlap with known task titles | What did I write down as a to-do but never actually track? |
| `journal.py` | Brier score; confidence-bucketed calibration curve | Are my "I'm 80% sure" calls actually right 80% of the time? |
| `rhythm.py` | Day-of-week / hour-of-day histograms vs. a uniform-baseline deviation | Is there a day or hour I'm consistently busier or quieter? |
| `placement.py` | Token-Jaccard between free text and a caller-supplied target registry | Which existing setting/tag/project does this sentence resemble? (ISS-120-safe: ranks only, never writes) |
| `calibrate.py` | Beta-Binomial acceptance rate per proposal kind; two-armed budget bandit | Which proposal kinds do I actually approve? How many should I be shown today? |
| `drift.py` | Set diff + minhash-Jaccard on shared ids | What's new, gone, or meaningfully reworded since the last snapshot? |
| `health.py` | Combines survival + orphan + duplicate signals into one score | Which notes need attention most urgently? |
| `dreamtime.py` | Idle/power/load gate; reuses `planner.knapsack` for job selection | Is now a good time for heavier batch jobs, and which ones fit? |

All twelve follow the same rule as the first round: stdlib-only, deterministic,
JSON-serialisable, and never a write — `service.py` wraps every one of them as
a plain-data function, and `bridge.py`/`cli.py` expose them the same way the
first round is exposed.

## Commands

```bash
python3 -m assistant.brain organize ~/notes/vault          # dedup, orphans, tag proposals, communities
python3 -m assistant.brain tag ~/notes/vault "text"        # which tag fits, renormalised over tags
python3 -m assistant.brain plan tasks.json --minutes 240 --propose
python3 -m assistant.brain estimate observe writing 50 && python3 -m assistant.brain estimate query writing
python3 -m assistant.brain review grade CARD 3 --days 2 && python3 -m assistant.brain review due --days 5
python3 -m assistant.brain remind feedback 10 1 && python3 -m assistant.brain remind choose --allowed 8-22
python3 -m assistant.brain forecast 3,4,5,6,7,8 --horizon 7
python3 -m assistant.brain cull history.json
python3 -m assistant.brain focus work,work,email,code,email
python3 -m assistant.brain ledger list | approve ID | reject ID | learn

python3 -m assistant.brain links ~/notes/vault --propose        # suggest new wiki-links
python3 -m assistant.brain keywords ~/notes/vault note.md       # top TF-IDF terms
python3 -m assistant.brain summarize ~/notes/vault note.md      # TextRank extractive summary
python3 -m assistant.brain spellcheck ~/notes/vault             # rare-word / common-word near-misses
python3 -m assistant.brain ghosts ~/notes/vault --known "renew passport"
python3 -m assistant.brain journal record d1 "the migration will finish today" 0.8
python3 -m assistant.brain journal resolve d1 1 && python3 -m assistant.brain journal report
python3 -m assistant.brain rhythm --weekdays 0,1,1,1,2,3 --hours 9,9,14,14,20
python3 -m assistant.brain calibration                          # per-kind approval rate
python3 -m assistant.brain health ~/notes/vault                 # worst-health notes first
```

State lives in `~/.local/state/caelestia-brain/` (`state.json`, `ledger.json`).

## Honesty notes

- The tagger's confidence is calibrated against a "no tag" class, so it is
  low when a note barely resembles your tagged notes. It is not a probability
  of truth; it is a ranking signal.
- The spaced-review scheduler is FSRS-*inspired*. It uses the same retrievability
  form and the same target-retention interval logic, but not the published
  FSRS weights.
- Duration and priority models are cold-start priors until you generate data:
  `estimate observe` and `ledger approve/reject` are what make them personal.
- Nothing here understands free text the way an LLM does. Phrasing that shares
  no vocabulary with your history will score low, by design.
- `placement.py` is deliberately narrow: it ranks a registry the caller supplies
  and never writes a config value itself. That is the ISS-120-safe slice of
  "natural-language settings" — see `assistant/retrieval/corpus/ISS-120.md` for
  why that boundary exists and who owns the rest of that proposal.
- `dreamtime.py` decides *whether* and *what*, never *how*: it returns a job
  list, and running those jobs is left to a caller outside this package, since
  `ALLOWED_IMPORTS.txt` bans `subprocess` for the assistant entirely.
