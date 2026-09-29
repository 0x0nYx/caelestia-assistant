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
| `preset_bandit.py` | Thompson sampling over named Beta arms (presets, individual tools); optional battery-drain secondary reward at 0.25 weight (never replaces the approve/reject signal) | Which settings/presets do you actually approve, hour by hour — and did they help your battery? |
| `prefs.py` | Beta-Binomial posteriors per (group, direction, hour-bucket), exact binomial-sum credible intervals | What do you usually approve, and when? |
| `placement.py` | Token-Jaccard between free text and a caller-supplied target registry | Which existing setting/tag/project does this sentence resemble? (ISS-120-safe: ranks only, never writes) |
| `calibrate.py` | Beta-Binomial acceptance rate per proposal kind; two-armed budget bandit | Which proposal kinds do I actually approve? How many should I be shown today? |
| `rhythm.py` | Day-of-week / hour-of-day histograms vs. a uniform-baseline deviation | When do scheme switches / settings applies actually happen? |
| `workspace.py` | k-means (k-means++, OKLab-agnostic) over (app, workspace, monitor, hour) session vectors; cluster-purity filter | Which apps/monitors/workspaces co-occur consistently enough to become a named profile proposal? (issue #120 phase 3) |
| `topology.py` | sha256 fingerprint over the per-monitor override directory set; delta memory keyed by that hash | This monitor set reconnected — which overrides were active last time? (proposed, never applied) |
| `forecast.py` | Holt linear trend; 1-D Kalman filter | Where is this series going; what is its smoothed level? |
| `anomaly.py` | z-score, deferral flag, Shannon entropy of switches | Is this unusual? Is my attention fragmented? |
| `bandit.py` | Thompson sampling over hour-of-day Beta arms (the engine `preset_bandit.py` generalizes) | Per-hour Beta arms for any caller-supplied reward stream |
| `meta_bandit.py` | Hierarchical meta-bandit (Thompson sampling per Chapelle & Li 2011) over caller-supplied recommendation engines — per-context Beta posteriors pooled upward through `pooling.py` (Efron & Morris 1975, reused), contexts matched via `features.py`'s signed hashing, regret audited through `regret.py` | Which recommendation engine should be trusted in THIS context — and did the meta level beat always trusting one engine? (library-first: the live routing path is untouched; `choose()` returns the engine, the caller executes it) |
| `naive_bayes.py` | Multinomial NB with a null-hypothesis class | Generic incremental text classifier (utility library) |
| `minhash.py` | MinHash + LSH banding, Jaccard verification | Generic near-duplicate detection (utility library) |
| `nlp.py` | stopwords-filtered tokens, char shingles | Shared tokenizer used by the text learners |
| `textmine.py` | TF-IDF; TextRank (weighted PageRank over sentences) | Generic keyword/summary extraction (utility library) |
| `spellfix.py` | SymSpell-style delete-index over a supplied vocabulary | Generic typo detection (utility library) |
| `kneser_ney.py` | Kneser-Ney smoothed n-grams (Kneser & Ney 1995; interpolated form + leaving-one-out discounts per Chen & Goodman 1999) — word flavor (n=3) completes, char flavor (n=4) corrects; continuation counts, not raw frequency, are the backoff | What word comes next / is this the word you meant — with an evidence gate ("confident"/"thin"/"abstain") so it only speaks when the vault supports it, and a fallback contract that never overrides SymSpell's answer |
| `preference_prompts.py` | Idle-time paired-comparison invitations riding the dreamtime cadence: the pair with the fewest recorded comparisons and the closest Elo ratings (the most ranking-information per answer), frequency-capped (one unanswered at a time, 7-day spacing, 14-day expiry) | Which comparison would teach the preference ladder the most right now? (a prompt RECORD — surfaces in `settings --rank`, answered by the ordinary `--prefer`) |
| `sequences.py` | PrefixSpan sequential-pattern mining (Pei et al. 2001, prefix-projected growth) over caller-supplied session records — one app sequence per date, frequent subsequences with day-support and share; the top patterns file as `launch_pattern` ledger proposals (approve/reject only) | Which app sequences are habitual (“terminal after editor”)? (read-only mining; the consent surface is the existing ledger) |
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
python3 -m assistant.brain rhythm --settings-file ~/.config/caelestia/shell.json   # shell-event rhythm (issue #120)
python3 -m assistant.brain workspace sessions.json            # k-means profiles (dry-run)
python3 -m assistant.brain workspace sessions.json --propose  # write ledger proposals
python3 -m assistant.brain topology --propose                 # monitor-topology memory
python3 -m assistant.brain calibration                        # per-kind approval rate
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
