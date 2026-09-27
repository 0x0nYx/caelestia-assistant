# assistant/devflow — developer-workflow drafting tools

> **Scope disclaimer, deliberately first:** this package exists for the
> developer's OWN workflow — commit-message skeletons, PR-description
> skeletons, TODO/FIXME triage over source trees. It has **no
> relationship to caelestia-kde issue #120 or the KDE shell**, it is not
> part of the assistant's shell-facing feature surface, and it must
> **never be included in any upstream-bound pull request** under any
> framing. If a #120-scoped task ever seems to need this package, that is
> a signal the partition is wrong — stop and re-scope, don't cross it.
> Nothing in `assistant/settings/` (or any other #120-bound surface)
> imports or references this package, and a unittest pins that.

## What it is

Three deterministic, templated helpers. No generation, no model, no
invented "why" — the judgment is always left to the human, marked with
explicit placeholders.

### `diffstat.commit_message` — a commit skeleton from `git diff --numstat`

```bash
git diff --numstat dev... > /tmp/numstat
python3 -m assistant.devflow commit < /tmp/numstat
```

```
feat(scan): <describe the what and why> [14 file(s), +1200/-40]

<why this change — one or two sentences a reviewer needs>

- scan: 2 file(s) (+410/-2)
    scan/simhash.py
    scan/tests/test_simhash.py
...
```

The conventional-commit type comes from a deterministic keyword table
(tests → `test`, docs → `docs`, CI paths → `ci`, new-files-only → `feat`,
deletion-dominated → `refactor`, fallback `chore`); the scope from the
common top-level directory; the deltas are the real counts. The
`<describe the what and why>` slots are yours.

### `diffstat.pr_skeleton` — a PR-description skeleton

```bash
python3 -m assistant.devflow pr --base dev --head my-branch < /tmp/numstat
```

Shaped like the receiving project's PR template (What does this change /
Changes by area with real deltas / How did you test it / Type / Notes),
with the Type checkbox pre-filled by the same classification — and an
explicit "uncheck and correct if wrong" note, because a keyword table
does not know your intent.

### `todo.triage_tree` — TODO/FIXME triage via Aho-Corasick

```bash
python3 -m assistant.devflow todo ~/my-checkout
```

Reuses the scan layer's Aho-Corasick automaton (built for one-pass
matching over huge logs — a source tree is the same problem, smaller)
to list every `TODO` / `FIXME` / `XXX` / `HACK` / `BUG` marker with
file, line and the comment's own text, grouped by marker. Bounded: file
cap, per-file size cap, no symlink following, hidden/build dirs skipped.

## Safety posture

Stdlib only, like the rest of the assistant. Reads only the text and the
tree you name; writes nothing, ever — not even the ledger. It drafts; you
decide.
