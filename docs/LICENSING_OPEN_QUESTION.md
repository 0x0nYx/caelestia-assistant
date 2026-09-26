# Licensing open question — AGPLv3 here vs GPL-3.0-or-later upstream

**Status: OPEN. This document resolves nothing and is not legal advice.
Only a human — ideally in conversation with upstream — can resolve it.**

## The situation, stated plainly

1. This repository (`0x0nYx/caelestia-assistant`) is licensed
   **AGPL-3.0-or-later**. The AGPLv3 relicense shipped in CHANGELOG
   0.1.0 ("initial baseline") and the LICENSE file carries the full
   GNU Affero General Public License v3.0 text.

2. The upstream shell this repository extends — `ladybug-me/caelestia-kde`,
   specifically its `shell/` tree — is distributed under
   **GPL-3.0-or-later**.

3. This repository therefore COMBINES AGPLv3-covered code with code
   received under GPL-3.0-or-later. That combination is permitted by
   **GPLv3 §13** ("Additional Permission... notwithstanding... you may
   convey a work based on the Program... under terms of your choice,
   provided that... for material you add to a covered work, you may...
   [impose] any further restrictions"), read together with the FSF's
   documented position that GPL-3.0 code may be incorporated into
   AGPL-3.0 works (the AGPL-3.0 license text itself states in section 7
   that additional permissions may allow incorporation into works under
   other licenses — and GPLv3 §13 is exactly such an allowance for
   network-server use).

## Why it is an open question anyway

- The combination has **not been confirmed with upstream**
  (ladybug-me / 0xSolanaceae). No recorded decision in the captured
  issue thread (`assistant/retrieval/corpus/ISS-120.md`) addresses
  licensing at all.
- The direction of combination matters to the upstream project's
  options: if any of this repo's AGPL-covered material were ever merged
  into the shell's GPL-3.0-only-not-later tree (if upstream's files are
  ever pinned to "GPL-3.0-only"), §13's one-way door closes. Today
  upstream's files are GPL-3.0-**or-later**, which keeps the door open —
  but "or-later" trusts future license versions, which is a choice
  upstream's maintainers own, not this repo's.
- GPLv3 §13's network-use provision is the FSF's intended bridge, but
  its application to a *specific* project combination is the kind of
  call that deserves an explicit "yes" from the humans who hold the
  copyright, not a solo reading.

## The rule this repo follows until it is resolved

**No pull request to upstream may reference, import, or include any
AGPLv3-covered file from this repository.** Concretely:

- PRs to `ladybug-me/caelestia-kde` must not copy or link code from
  `assistant/` while this question is open;
- discussion PRs/issue comments may describe the approach and link the
  repo as a reference implementation, clearly labeled AGPLv3;
- if upstream ever wants material from this repo, the paths are: (a)
  upstream agrees the combination is fine and the file lands as
  AGPL-3.0-or-later with headers intact, or (b) the specific material
  is rewritten/relicensed by its authors with their consent.

This document intentionally does NOT attempt to resolve the question,
contact upstream on the repo's behalf, or relicense anything.
