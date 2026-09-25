# assistant.brain — shell-native intelligence layer

Stdlib-only, no LLM, no network, no executor. Learns from your own decisions
and turns them into proposals. Nothing writes to shell.json or notes: every
change is a proposal in a ledger until you approve it.

## Scope split (issue #120)

This package is split in two, deliberately:

- **Root (`assistant/brain/`, this page)** — shell-native: the proposal
  ledger, the settings bridge for issue #120, engines fed by shell events
  (rhythm over scheme-switch/apply events), placement, calibration, drift,
  forecast/focus analytics, the filesystem organizer, and the daily brief.
  This is what `python3 -m assistant.brain` and the JSON bridge expose.
- **`assistant/brain/personal/`** — opt-in personal-knowledge-management
  tools (vault organization, spaced repetition, task survival, decision
  journal, day planning). They have **zero** shell linkage, are NOT part of
  the caelestia-kde issue #120 feature surface, and are exposed only through
  their own entry point: `python3 -m assistant.brain.personal --help`.
  See [personal/README.md](personal/README.md).

## Root modules

| Module | Algorithm | What it answers |
| --- | --- | --- |
| `ledger.py` | JSON proposal ledger (pending / approved / rejected) | What is waiting for my decision? |
| `settings_bridge.py` | dry-run plan → ledger proposal → approve-then-apply via the settings applier | Issue #120's "Apply these changes?" loop, with the bandit fed on every decision |
| `preset_bandit.py` | Thompson sampling over named Beta arms (presets, individual tools) | Which settings/presets do you actually approve, hour by hour? |
| `prefs.py` | Beta-Binomial posteriors per (group, direction, hour-bucket), exact binomial-sum credible intervals | What do you usually approve, and when? |
| `placement.py` | Token-Jaccard between free text and a caller-supplied target registry | Which existing setting/tag/project does this sentence resemble? (ISS-120-safe: ranks only, never writes) |
| `calibrate.py` | Beta-Binomial acceptance rate per proposal kind; two-armed budget bandit | Which proposal kinds do I actually approve? How many should I be shown today? |
| `rhythm.py` | Day-of-week / hour-of-day histograms vs. a uniform-baseline deviation | When do scheme switches / settings applies actually happen? |
| `forecast.py` | Holt linear trend; 1-D Kalman filter | Where is this series going; what is its smoothed level? |
| `anomaly.py` | z-score, deferral flag, Shannon entropy of switches | Is this unusual? Is my attention fragmented? |
| `bandit.py` | Thompson sampling over hour-of-day Beta arms (the engine `preset_bandit.py` generalizes) | Per-hour Beta arms for any caller-supplied reward stream |
| `naive_bayes.py` | Multinomial NB with a null-hypothesis class | Generic incremental text classifier (utility library) |
| `minhash.py` | MinHash + LSH banding, Jaccard verification | Generic near-duplicate detection (utility library) |
| `nlp.py` | stopwords-filtered tokens, char shingles | Shared tokenizer used by the text learners |
| `textmine.py` | TF-IDF; TextRank (weighted PageRank over sentences) | Generic keyword/summary extraction (utility library) |
| `spellfix.py` | SymSpell-style delete-index over a supplied vocabulary | Generic typo detection (utility library) |
| `drift.py` | Set diff + minhash-Jaccard on shared ids | What's new, gone, or meaningfully reworded since the last snapshot? |
| `tidy.py` | size-bucketed crc32 fingerprints + byte-exact confirmation, age-quartile staleness, collision-safe renames, journaled os.rename with rollback | How should this folder be organized? (moves only — never deletes) |
| `brief.py` | pure assembler over the other modules' outputs | What matters today, on one honest page? |
| `state.py` | one atomic JSON state file | Where the learned weights live |
| `dreamtime.py` | Idle/power/load gate; reuses the `personal/planner.py` knapsack engine for job selection | Is now a good time for heavier batch jobs, and which ones fit? |

All follow the same rule: stdlib-only, deterministic, JSON-serialisable, and
never a write — `service.py` wraps every one of them as a plain-data
function, and `bridge.py`/`cli.py` expose the same surface.

## Commands (shell-native surface)

```bash
python3 -m assistant.brain forecast 3,4,5,6,7,8 --horizon 7
python3 -m assistant.brain focus work,work,email,code,email
python3 -m assistant.brain rhythm --weekdays 0,1,1,1,2,3 --hours 9,9,14,14,20
python3 -m assistant.brain calibration                          # per-kind approval rate
python3 -m assistant.brain ledger list | approve ID | reject ID
python3 -m assistant.brain settings propose shell.json --preset minimal --reason "try it"
python3 -m assistant.brain settings decide 1 approve
python3 -m assistant.brain settings recommend [--tools]
python3 -m assistant.brain brief
python3 -m assistant.brain tidy survey ~/Downloads
python3 -m assistant.brain prefs
```

Personal-PKM commands (vault, plan, review, remind, journal, …) live behind
`python3 -m assistant.brain.personal` — see its README. They are not routed
by `caelestia-assist`.

State lives in `~/.local/state/caelestia-brain/` (`state.json`, `ledger.json`).

## Honesty notes

- The spaced-review scheduler (now in `personal/`) is FSRS-*inspired*. It
  uses the same retrievability form and the same target-retention interval
  logic, but not the published FSRS weights.
- Learners here are cold-start priors until you generate data: ledger
  approve/reject decisions are what make them personal.
- Nothing here understands free text the way an LLM does. Phrasing that shares
  no vocabulary with your history will score low, by design.
- `placement.py` is deliberately narrow: it ranks a registry the caller supplies
  and never writes a config value itself. That is the ISS-120-safe slice of
  "natural-language settings" — see `assistant/retrieval/corpus/ISS-120.md` for
  why that boundary exists and who owns the rest of that proposal.
- `dreamtime.py` decides *whether* and *what*, never *how*: it returns a job
  list, and running those jobs is left to a caller outside this package, since
  `ALLOWED_IMPORTS.txt` bans `subprocess` for the assistant entirely.
- `prefs.py` learns exclusively from ledger decisions (approve/reject = the
  same training signal every learner here uses). `tidy.py` applies only behind
  the agent's consent gate with a rollback journal written before the first move.
