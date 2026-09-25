"""Persistent model state (learned weights, counts, bandit arms) as one JSON file."""
import json
import os
import pathlib

DEFAULT_STATE = pathlib.Path(os.path.expanduser("~/.local/state/caelestia-brain/state.json"))


def load(path=DEFAULT_STATE):
    p = pathlib.Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def save(state, path=DEFAULT_STATE):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, p)
