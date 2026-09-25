# Contributing

Thanks for helping make caelestia-assistant better. This project has an
unusual set of constraints — they are its identity, and pull requests are
reviewed against them first.

## The non-negotiables

1. **Stdlib only.** No pip dependencies in the assistant itself. The
   allow-list is `assistant/ALLOWED_IMPORTS.txt`, enforced by an AST scan
   (`python3 -m assistant.hub selfcheck`) and pinned by tests across five
   packages. If you need a new stdlib module (e.g. `heapq`, `zlib`), add it
   to the allow-list **with a one-line justification** in the same PR.
2. **Never execute, never phone home.** `subprocess`, `socket`, `shutil`,
   `ctypes`, `eval`, auto-exec rule keys — rejected by the lint. Suggested
   commands are inert `SUGGESTED_NOT_EXECUTED:` strings with a risk tier.
   The only network surface is the optional loopback Ollama client in
   `assistant/generative/client.py`, which hard-rejects non-loopback hosts.
3. **Every write is enumerated and gated.** New write paths need: dry-run
   default, explicit consent gate, a journal/ledger entry, and a rollback
   story. Deletion is not implemented anywhere and should not be.
4. **Honest verdicts.** A module that is unsure says `AMBIGUOUS`/`ABSTAIN`
   with evidence. No silent clamping, no silent fallbacks, no fake
   confidence. Uncertainty machinery (calibration, conformal) is preferred
   over bare scores.
5. **Deterministic and reproducible.** Same input → same output bytes.
   Stochastic algorithms take a fixed seed and say so.

## Adding a settings tool (issue #120 registry)

Tools live in `assistant/settings/tools.json`, generated from the shell's
sources by `assistant/settings/build_registry.py`. Each tool needs its C++
declaration citation, its shipped Nexus control, and a live QML reader.
After rebuilding `tools.json`, regenerate the QML table
(`scripts/assemble_settings_tools.py`) — a unittest asserts byte-identity,
so a stale table fails CI.

## Tests

```bash
python3 -m unittest discover -s . -p "test_*.py"   # everything, ~10 s
python3 -m assistant.hub selfcheck                 # rule schema + import lint
```

Every new module ships with tests pinning it to known values (a solved
example, a brute-force cross-check, or a bound check). Tests must not
require network, a display, or a KDE session.

## Commits

Small, focused commits; the subject line names the layer. Reference issues
(`(#120)`) when the work implements or extends one. Documentation
(`README`, layer `README.md` files, `RATIONALE.md`, `DESIGN.md`) is updated
in the same PR as the behaviour it describes — docs that lag are bugs.

## Licensing

The project is licensed under the **GNU Affero General Public License v3.0**
(or any later version, at your option). By submitting a pull request you
agree that your contribution is licensed under AGPL-3.0-or-later, so it can
be distributed with the project. There is no CLA and no copyright
reassignment — your work stays yours; the license only guarantees it stays
open.

A practical note for contributors: AGPLv3 is stricter than MIT about
combination. Keep third-party code out of `assistant/` (the stdlib-only
policy already demands this), and if you fork, the license text in
`LICENSE` must travel with your copy.
