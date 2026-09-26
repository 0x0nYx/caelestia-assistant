# Tier C Proposal 2 — Federated, opt-in, signed lexicon-diff sharing

**Status: PROPOSAL ONLY — no implementation without explicit sign-off.**
No server, no training, no network code inside the assistant (the import
allow-list stays exactly as it is). "Federated" here means: diffs travel
the way issues and PRs already travel — as reviewable text, by the user's
own hand or their fork's own CI.

## Approach

The shareable artifact is a **lexicon diff**: a plain-text, reviewable list
of `phrase -> tool` mappings a user's cortex has learned (reroute
corrections + approved routes, capped at the newest N=200, PII-stripped to
the same standard as the undo log — no timestamps, no file paths, no
values). Format:

```
CAELESTIA LEXICON DIFF v1  (corpus v1, learner v1, 2026-09-26)
+frosted glass            -> setBlurEnabled          (n=4, p=0.86)
+make the bar slim        -> setBarScale             (n=2, p=0.79)
-enable the blur          -> setBlurEnabled          (corrected)
```

- **Export**: `cortex lexicon export` prints the diff (stdout — no file
  writes, no network).
- **Import**: `cortex lexicon import < diff` applies it as SUPERVISED
  pairs into the embedder seam built in A2 (`labeled_pairs`, weight above
  the corpus prior) and as review-bucket candidates for the learner —
  never directly into the hand-seeded `SYNONYMS` (that table stays a
  reviewed diff, RATIONALE.md §5).
- **Signing**: an Ed25519 detached signature over the canonical diff text,
  produced and verified by an EXTERNAL tool the user already trusts
  (`minisign`, `sq`, or plain GPG) — the assistant itself never holds a
  private key and never grows crypto code. "Signed" means the importer
  can state whose corpus the diff came from; trust in that identity
  remains a human decision (pin known keys in a local file).
- **Federation mechanics**: users share diffs in issue threads, matrix
  rooms, or fork PRs — the same channels the shell's community already
  uses. A `lexicon/index.md` in this repo can curate links to vetted diffs,
  reviewed like any other PR.

## Footprint (§2.6)

Export/import are CLI-only, on-demand: zero resident cost. Import cost is
one embedder rebuild (~2 s for SVD, ~0.4 s for RP — measured this session)
applied to at most 200 pairs. No new imports beyond the existing allow-list
(Ed25519 verification happens in the external tool, not here).

## Safety-contract implications

- No network surface: nothing in `assistant/` can transmit; the user moves
  the text themselves. The lint allow-list is untouched.
- Prompt-injection surface: imported phrases become router supervision,
  not instructions — a malicious diff can at worst skew routing toward
  wrong tools, which the existing AMBIGUOUS/consent gates already bound.
  Mitigations: import caps (200), per-phrase length cap (already 120
  chars in the learner), a warning line in the import report listing every
  tool the diff would boost, and one-command rollback
  (`cortex lexicon forget <diff-id>` drops the imported set).
- Privacy: the same PII-strip rule as the undo log — a diff cannot carry
  a user's file paths, values, or schedule; phrases are the only content,
  and phrases are what the user chose to type at the assistant.

## Verification plan

1. Export determinism: same learner state -> byte-identical diff
   (snapshot test).
2. Import round-trip: export from learner A, import into learner B,
   assert B's routing of the diff's phrases matches A's (top-1 parity
   on the diff's phrase set, measured and printed).
3. Rollback: `forget` restores the pre-import embedder fingerprint
   (A2's fingerprint test extended).
4. Injection fuzz: diffs containing tool names for non-existent tools,
   over-long phrases, and empty lines import as no-ops with warnings —
   never as exceptions.
