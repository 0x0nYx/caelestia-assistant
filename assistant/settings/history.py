"""Bounded undo history for the settings layer (issue #120).

Issue #120 asks for "a small history" so that "Undo the last change",
"Restore yesterday's theme" and "Revert my last customization" are all
answerable — not just the single most recent write. This module is the
data half: a ring of the last MAX_ENTRIES applies (oldest evicted first),
persisted as a sibling of the target file at
``<target>.assistant-history.json``.

The WRITE half stays in applier.py (the package's only writer):
- applier.apply(..., label=...) records an entry after every successful
  write;
- undo()/undo_by_id() build the reverse plan and hand it back to
  applier.apply with record_history=False, so an undo never appears in
  the history as a new apply (undo consumes; redo is deliberately not
  offered — the issue asks for undo).

Entry schema: {"id": int, "at": ISO-8601, "label": str,
               "ops": [{"path": str, "old": value, "new": value}]}
File schema: {"next_id": int, "entries": [entry, ...]} (newest first).

Pure data + JSON I/O on exactly one sibling path; no execution, no
network, no other file is touched.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .registry import tool_by_path

HISTORY_SUFFIX = ".assistant-history.json"
MAX_ENTRIES = 12  # >= the required 10; oldest evicted first

FileTarget = Union[str, Path]


class HistoryError(RuntimeError):
    """Raised when the history cannot be read or an undo is impossible."""


def _resolved(file_path: FileTarget) -> Path:
    return Path(os.path.realpath(str(file_path)))


def history_path(target: FileTarget) -> Path:
    return _resolved(target).with_name(_resolved(target).name + HISTORY_SUFFIX)


def _load(target: FileTarget) -> Dict[str, Any]:
    path = history_path(target)
    if not path.exists():
        return {"next_id": 1, "entries": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HistoryError(
            f"history file {path} is unreadable ({exc}); undo is refused, "
            "nothing was written"
        ) from exc
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise HistoryError(
            f"history file {path} is not a valid history document; undo is "
            "refused, nothing was written"
        )
    data.setdefault("next_id", len(data["entries"]) + 1)
    return data


def _save(target: FileTarget, data: Dict[str, Any]) -> None:
    path = history_path(target)
    data["entries"] = data["entries"][:MAX_ENTRIES]  # FIFO: oldest evicted
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def record(target: FileTarget, label: str,
           ops: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Append one apply to the ring (called by applier.apply only, after a
    successful write). Oldest entries are evicted beyond MAX_ENTRIES."""
    data = _load(target)
    entry = {
        "id": int(data["next_id"]),
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "label": str(label or ""),
        "ops": [
            {"path": str(op["path"]),
             "old": op.get("old"),
             "new": op.get("new")}
            for op in ops
        ],
    }
    data["next_id"] = int(data["next_id"]) + 1
    data["entries"].insert(0, entry)
    _save(target, data)
    return entry


def entries(target: FileTarget) -> List[Dict[str, Any]]:
    """The undo history, newest first (a copy)."""
    return [dict(e) for e in _load(target)["entries"]]


def _reverse_plan(entry: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Build an applier plan that restores the entry's old values."""
    plan_entries: List[Dict[str, Any]] = []
    skipped: List[str] = []
    for op in entry.get("ops", []):
        path = str(op.get("path", ""))
        spec = tool_by_path(path)
        if spec is None:
            skipped.append(path)
            continue
        plan_entries.append({
            "tool": spec.name,
            "path": path,
            "action": "set",
            "raw": f"undo #{entry.get('id')} {path}",
            "new": op.get("old"),
            # old=None means the key was ABSENT before that apply: the undo
            # removes it again (applier._deep_unset) instead of writing null.
            "unset": op.get("old") is None,
        })
    plan = {"entries": plan_entries, "apply_blocked": False}
    return plan, skipped


def _consume(target: FileTarget, data: Dict[str, Any],
             index: int) -> Dict[str, Any]:
    entry = data["entries"].pop(index)
    _save(target, data)
    return entry


def undo(target: FileTarget, steps: int = 1) -> Dict[str, Any]:
    """Undo the newest `steps` applies (default 1). Returns the applier's
    result for the combined reverse plan. Consumed entries are removed."""
    from .applier import apply as apply_plan  # local import: applier writes

    if steps < 1:
        raise HistoryError("undo steps must be >= 1")
    data = _load(target)
    if not data["entries"]:
        return {"restored": False,
                "message": "nothing to undo (the history is empty)"}
    steps = min(steps, len(data["entries"]))
    combined: List[Dict[str, Any]] = []
    labels: List[str] = []
    for _ in range(steps):
        entry = data["entries"][0]
        plan, skipped = _reverse_plan(entry)
        combined.extend(plan["entries"])
        labels.append(str(entry.get("label") or f"#{entry.get('id')}"))
        data["entries"].pop(0)
    if not combined:
        _save(target, data)
        return {"restored": False,
                "message": "the history entries reference no registry paths; "
                           "they were consumed without a write"}
    result = apply_plan({"entries": combined, "apply_blocked": False},
                        target, write=True, record_history=False)
    _save(target, data)
    note = f"undid {steps} apply entr{'y' if steps == 1 else 'ies'} ({'; '.join(labels)})"
    result["message"] = f"{note}; {result.get('message', '')}".strip("; ")
    return result


def undo_by_id(target: FileTarget, entry_id: int) -> Dict[str, Any]:
    """Revert one specific history entry ('restore yesterday's theme'):
    the entry's old values are written back and the entry is consumed.
    Entries applied AFTER it are left as they are — reverting an old entry
    can produce a state that never existed if later applies touched the
    same keys; that is inherent to per-entry undo and stated plainly."""
    from .applier import apply as apply_plan

    data = _load(target)
    index = next((i for i, e in enumerate(data["entries"])
                  if int(e.get("id", -1)) == int(entry_id)), -1)
    if index == -1:
        raise HistoryError(
            f"no history entry with id {entry_id}; see --history"
        )
    entry = data["entries"][index]
    plan, skipped = _reverse_plan(entry)
    data["entries"].pop(index)
    if not plan["entries"]:
        _save(target, data)
        return {"restored": False,
                "message": f"entry #{entry_id} references no registry paths; "
                           "consumed without a write"}
    result = apply_plan(plan, target, write=True, record_history=False)
    _save(target, data)
    label = entry.get("label") or "unlabelled"
    at = entry.get("at", "?")
    n = len(entry.get("ops", []))
    result["message"] = (
        f"reverted '{label}' ({n} change(s), applied {at}); "
        + result.get("message", "")
    ).strip("; ")
    if skipped:
        result["skipped_paths"] = skipped
    return result
