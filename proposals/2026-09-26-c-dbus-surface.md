# Tier C Proposal 1 — DBus-based surface expansion (kwriteconfig6, kscreen-doctor, powerdevil, KWin scripting)

**Status: IMPLEMENTED behind the kill-switch (2026-09-26, phase 2.7) —
the maintainer decision this document escalates remains open: the
surface ships DISABLED by default (capabilities.json `dbus_surface:
false`), quarantined by a per-module lint carve-out pinned to exactly
this module, and nothing enables it without a deliberate file edit.**
The safety contract forbids `subprocess`/`socket`/`ctypes` in
`assistant/` (ALLOWED_IMPORTS.txt, enforced by `schema_lint.py`). The
relaxation is scoped to `settings/dbus_surface.py` ALONE through the
per-module quarantine (the same carve-out pattern `agent/pkgprobe.py`
established); every other module keeps the zero-tolerance rule, and a
test pins the exemption set to exactly {pkgprobe.py, dbus_surface.py}.
The maintainer may still veto the whole surface by deleting the module
and its two carve-out lines — nothing else depends on it.

## Approach

A single new module `assistant/settings/dbus_surface.py`, quarantined from
the rest of the package by a lint rule that scopes the relaxation to it
alone (`schema_lint.py` gains an per-module exemption list — the allow-list
stays a reviewable diff). The module shells out to exactly four allow-listed
binaries via `subprocess.run` with fixed argument arrays (never
shell=True, never interpolated strings — the upstream CONTRIBUTING.md's own
"pass arguments as an array" rule):

| Capability | Binary | Why it needs a process |
|---|---|---|
| kwinrc companion writes | `kwriteconfig6` | no Python DBus dep wanted; the target repo's own precedent (lock-screen section, CONTRIBUTING.md) |
| display topology | `kscreen-doctor --outputs` (read) / `--output ... --mode ...` (write) | KScreen DBus API is version-fragile; the CLI is the stable contract |
| power profiles | `powerprofilesctl` | small, allow-listed, prints machine-readable rows |
| KWin scripting | `kwin --script` + `dbus-send` to `org.kde.KWin` | the only scripting entry point that survives across KDE releases |

Every write goes through the existing proposal spine: dry-run default →
ledger proposal → `--apply` gate → bounded undo where the underlying tool
supports revert (kwriteconfig6: yes, via the recorded old value; kscreen
mode changes: yes, via the topology snapshot; KWin scripts: no — flagged
`reversible: false` and requiring a second confirmation).

## Footprint (§2.6)

No resident process, no daemon: one short-lived `subprocess.run` per tool
call (~15-30 ms fork+exec each), zero steady-state memory. The QML service
keeps its in-process write path for shell.json; this module only covers the
surfaces the watched file cannot reach. Worst case on a 4 GB laptop:
indistinguishable from the user typing the command once.

## Safety-contract implications

- `schema_lint.py`: FORBIDDEN_IMPORTS gains a per-module carve-out
  (`_DBUS_SURFACE_EXEMPT = {"dbus_surface.py"}`) — every other module in
  `assistant/` remains scanned with today's zero-tolerance rule, and a test
  asserts the exemption list never grows without a matching change to this
  proposal's status line.
- Risk classification: every generated command is pre-classified by the
  existing `risk.py` static classifier BEFORE execution is offered; DESTRUCTIVE
  classifications (e.g. `kscreen-doctor` with `--remove`) are withheld
  entirely, same as Layer 1 suggestions.
- Kill-switch: `dbus_surface.py` refuses to run unless
  `settings.dbus.enabled` is true — default **false** (the §2.7/CONTRIBUTING
  experimental-off rule), settable only in the file, not via NL request.

## Verification plan

1. Unit tests against a fake `subprocess.run` (recorded calls, no process):
   argument-array shape, allow-list enforcement, risk classification, undo
   records.
2. Integration test gated behind an env var (`CAELESTIA_ASSIST_DBUS_TESTS=1`)
   that is NOT set in CI — runs only on a real KDE session, manually.
3. Lint parity: `schema_lint` output identical for every module except the
   exemption entry; a test pins the exemption set to exactly one module.
4. Upstream-PR extraction: none of this ships upstream — it is
   caelestia-assistant's own surface expansion, gated on the maintainer
   sign-off this document requests.
