# Tier C Proposal 3 — Pairwise Elo/Bradley-Terry preference ranking over presets

**Status: PROPOSAL ONLY — no implementation without explicit sign-off.**
The question it answers: "which preset does THIS user actually prefer?"
— currently unanswerable, because presets are never compared head-to-head;
the NamedBandit (preset_bandit.py) learns per-preset acceptance rates,
which confound "good preset" with "offered at the right moment".

## Approach

Bradley-Terry (the logistic twin of Elo — Bradley & Terry 1952; Elo is a
Bernoulli(1) online special case) over PAIRWISE outcomes only:

- Every real decision that rejects preset A while a preset B proposal sits
  pending (or was applied the same day) counts as one implicit comparison
  B > A — the ledger already records enough to reconstruct these pairs
  without any new capture surface.
- Explicit comparisons, opt-in: `settings prefer` offers two preset
  previews side by side (dry-run plans of both), the user picks one;
  one comparison each. No batch mode — each pair is a deliberate choice.
- Model: one latent strength θ per preset, logistic pairwise likelihood
  P(B beats A) = σ(θ_B − θ_A); fit by 20 iterations of online logistic —
  the exact `OnlineLogistic`/AdaGrad machinery already in
  `cortex/learn.py`, reused, with a two-feature trick (θ as free
  parameters) or plain Newton sweeps on 5 presets (trivial at this size).
- Output: `settings rank` prints the ladder with uncertainty (± via the
  AdaGrad diagonal), and `recommend` may expose
  `--rank-aware` (opt-in, default off) to tie-break profile
  recommendations by learned strength when scores are otherwise equal.

## Footprint (§2.6)

5 presets × 1 float + a 5×5 comparison count matrix: ~zero. Fitting is
20 Newton steps over ≤ 5 parameters: microseconds. No new imports; no
new write paths (state rides the existing brain state file's atomic
write).

## Safety-contract implications

- None structurally: read-only model over existing ledger data; the only
  new surface is a CLI question ("prefer: compact or minimal?") whose
  answer writes one comparison row into the existing state file.
- Behavior risk: rank-aware recommendations must never apply anything —
  they re-order PROPOSALS, and the planner/applier gates are untouched
  (the same line optimize.py already holds). Default remains rank-blind
  until the user opts in (§2.7 toggle discipline).

## Verification plan

1. Synthetic-recovery test: simulate 300 pairwise outcomes from known
   θ's, fit, assert recovered ordering matches ground truth ordering
   (Kendall τ ≥ 0.8) and that uncertainty shrinks with comparisons.
2. Pair-extraction test: from a fixed ledger fixture, assert the
   extracted implicit pairs are exactly the hand-counted ones.
3. Determinism: fixed seed, byte-identical ladder across runs.
4. Sparsity honesty: presets with < 3 comparisons render "not enough
   data" instead of a default rank.
5. Ablation: rank-aware vs blind recommendations on the synthetic ladder
   — numbers printed, not claimed.
