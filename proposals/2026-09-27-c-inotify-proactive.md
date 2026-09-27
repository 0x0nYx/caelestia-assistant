# Tier C Proposal — Proactive filesystem-event triggering (inotify)

**Status: PROPOSED (design only, 2026-09-27, exponential-build-3 E3) —
NOTHING here is implemented. No module, no import, no lint change
ships with this document; the master prompt for this build explicitly
scoped the inotify direction to a proposal.** The safety fences this
document must respect are the standing ones: `assistant/` stays
executor-free (no subprocess/socket/ctypes outside the two quarantined
carve-outs `agent/pkgprobe.py` and `settings/dbus_surface.py`), the
import allow-list stays as-is, and the assistant remains on-demand —
`diagnostics/telemetry.py`'s own docstring says "no daemon, no
poller, no inotify", which this proposal is asking to revisit, not
quietly violate.

## The ask

Today every assistant surface is PULLED: a user command, a dreamtime
idle batch, or a diagnostic verb triggers work. The ask is a PUSH
surface: the assistant reacts when the filesystem changes —
"screenshots/ grew by three files, want a triage?", "downloads/ has
new files, want the tidy proposal?", "the config you asked about
changed on disk, re-running the lint found two stale keys". The
kernel interface for this on Linux is inotify(7): watch descriptors,
`read()` returning structured events, no polling loop.

## Why nothing can ship today (the honest constraints)

1. **No stdlib binding.** Python's standard library has no inotify
   wrapper (Linux-only, deliberately excluded). The three real routes
   are all fenced off for `assistant/`:
   - `ctypes` + `inotify_init/inotify_add_watch` syscalls — `ctypes`
     is rejected by name in `ALLOWED_IMPORTS.txt`'s header and by
     `schema_lint.py`, for good reason: it is arbitrary native-call
     surface, the exact class of risk the allow-list exists to cap;
   - a C extension — a build dependency and a binary artifact in a
     repo that ships pure Python;
   - `subprocess` to an external helper — `subprocess` is confined to
     the two quarantined carve-outs, and adding a third quarantine for
     a *watcher daemon* is the strongest possible precedent against
     the carve-out ceiling the dbus-surface proposal set.
2. **A watcher is a daemon.** inotify requires a blocked `read()` on
   the watch fd — a long-lived process. The assistant today has no
   long-lived process anywhere: even dreamtime's cadence loop is
   driven by user activity, not a resident thread. A resident watcher
   is a new always-on surface (memory, restart-on-crash policy,
   log growth), which is a maintainer decision, not a module.
3. **The events have no consent story yet.** A push surface that
   fires proposals into the ledger whenever a directory changes needs
   rate bounds and de-dup logic (the same event will fire for the
   file the assistant itself just proposed to move), or the ledger
   fills with noise and the approve/reject surface degrades.

## The three implementable shapes, ranked

**Shape A — shell-side watcher, assistant stays on-demand
(recommended).** The QML shell already runs as a resident process and
already owns the filesystem contexts in question (it takes the
screenshots, it reads the config). A small QML/JS `FileSystemWatcher`
(a Qt class, no new assistant code) in `shell/` calls the EXISTING
assistant CLI (`caelestia-assist agent` / `assistant.settings --lint`)
when a watched directory settles. The assistant keeps every fence:
it is still invoked on demand, just by the shell instead of a human.
The policy question ("should the shell poke the assistant about my
downloads?") moves to upstream, where watch-list defaults belong. This
is the clean split: the resident half lives where the resident
process already lives.

**Shape B — poll-on-idle inside the existing fences (the local
compromise).** No inotify at all: dreamtime's existing idle cadence
adds a bounded job that stats a fixed watch list (pathlib, already
allowed), keeps the last-seen (mtime, size, count) tuple in the brain
state JSON, and files a ledger proposal when the delta crosses a
threshold. Everything is inside existing surfaces (dreamtime cadence,
brain state, ledger consent); the cost is latency (idle-cadence
minutes, not kernel-instant) and one stat pass per idle tick. This
shape could ship TODAY without touching a single fence — it is a
policy add, not a mechanism add, which is exactly why it needs a
maintainer yes first: always-on-ish behavior by any other name.

**Shape C — quarantined inotify module (explicitly NOT
recommended).** A third carve-out (`assistant/diagnostics/inotify.py`,
ctypes, per-module lint exemption, kill-switched like
`dbus_surface`). Technically symmetric with the two existing
carve-outs and rejected on that very ground: the carve-out ceiling
was set at two precisely so a third would be a visible trend-line
decision, and a watcher daemon is a worse resident risk than either
existing probe (they run once and exit). Listed for completeness, not
advocacy.

## What this proposal decides nothing about

The watch-list defaults, the event-to-proposal mapping (which deltas
deserve a ledger proposal at all), and the rate bounds are all open
questions that belong to whichever shape the maintainer picks; this
document deliberately does not pre-design them.
