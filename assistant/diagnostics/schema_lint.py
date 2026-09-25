"""Safety lint for Layer 1: the checks that go beyond structure.

Structural validation lives in engine.validate_rule (run at load time).
This module adds the safety-specific layer:

1. Forbidden-key scan — a rule cannot even *express* auto-execution: keys
   matching auto_run/exec/execute/invoke/spawn/eval are rejected.
2. Risk consistency — every fix step that carries a command must declare a
   command_risk tier at least as severe as what the risk classifier infers
   from the command text (over-declaring is allowed, under-declaring is a
   lint failure); PRIVILEGED/DESTRUCTIVE steps must carry a warning.
3. Import policy — the assistant's own Python must not import subprocess,
   os.system, sockets, or anything else that could execute or transmit;
   see ALLOWED_IMPORTS.txt for the single allow-list.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any, Dict, List

from . import engine
from . import risk

ASSISTANT_DIR = Path(__file__).resolve().parent.parent
ALLOWED_IMPORTS_FILE = ASSISTANT_DIR / "ALLOWED_IMPORTS.txt"

FORBIDDEN_KEY_RE = re.compile(r"(auto_?run|exec|execute|invoke|spawn|eval)", re.IGNORECASE)

FORBIDDEN_IMPORTS = (
    "subprocess",
    "socket",
    "http",
    "urllib",
    "urllib2",
    "requests",
    "pty",
    "shutil",
    "ctypes",
    "multiprocessing",
    "asyncio",
    "ftplib",
    "telnetlib",
    "smtplib",
    "xmlrpc",
    "webbrowser",
)

FORBIDDEN_OS_ATTRS = ("system", "popen", "execv", "execve", "execvp", "spawnv", "spawnve", "fork")


def validate_rule_safety(rule: Dict[str, Any], source: str) -> List[str]:
    """Safety checks on one rule beyond structural validation."""
    failures: List[str] = list(engine.validate_rule(rule, source=source))
    rule_id = rule.get("id", "<no-id>")

    for key in rule:
        if FORBIDDEN_KEY_RE.search(str(key)):
            failures.append(
                f"{source} {rule_id}: forbidden key {key!r} (rules cannot express auto-execution)"
            )

    try:
        leaves = engine._walk_matchers(rule["matchers"])
    except ValueError:
        leaves = []
    for leaf in leaves:
        for key in leaf:
            if FORBIDDEN_KEY_RE.search(str(key)):
                failures.append(f"{source} {rule_id}: forbidden matcher key {key!r}")

    for step in rule.get("fix", []):
        if not isinstance(step, dict):
            continue
        command = step.get("command")
        if command is None:
            continue
        if not isinstance(command, str):
            failures.append(f"{source} {rule_id}: command must be a string")
            continue
        declared = step.get("command_risk")
        if declared not in risk.RISK_ORDER:
            continue  # structural check already reported this
        classified = risk.classify(command)
        if not risk.at_least_as_severe(declared, classified):
            failures.append(
                f"{source} {rule_id}: declared risk {declared} is weaker than classified "
                f"{classified} for command {command[:60]!r}"
            )
        if declared in ("DESTRUCTIVE", "PRIVILEGED") and not step.get("warning"):
            failures.append(f"{source} {rule_id}: {declared} command requires a warning")
    return failures


def check_rule_files() -> List[str]:
    """Validate every rules.d/*.json file; also ensures ids are unique."""
    failures: List[str] = []
    seen: Dict[str, str] = {}
    rule_files = sorted(engine.RULES_DIR.glob("*.json"))
    if not rule_files:
        return ["no rule files found"]
    for path in rule_files:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                envelope = json.load(handle)
        except json.JSONDecodeError as exc:
            failures.append(f"{path}: invalid JSON: {exc}")
            continue
        if envelope.get("schema_version") != 1:
            failures.append(f"{path}: schema_version must be 1")
        for rule in envelope.get("rules", []):
            failures.extend(validate_rule_safety(rule, source=path.name))
            rid = rule.get("id", "?")
            if rid in seen:
                failures.append(f"{path}: duplicate rule id {rid} (also in {seen[rid]})")
            seen[rid] = path.name
    return failures


def _iter_py_files() -> List[Path]:
    root = ASSISTANT_DIR
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def load_allowed_imports() -> List[str]:
    with open(ALLOWED_IMPORTS_FILE, "r", encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip() and not line.startswith("#")]


def check_import_policy() -> List[str]:
    """AST-scan assistant/**/*.py against the allow-list and danger list."""
    failures: List[str] = []
    allowed = set(load_allowed_imports())
    for py in _iter_py_files():
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except SyntaxError as exc:
            failures.append(f"{py.name}: syntax error: {exc}")
            continue
        for node in ast.walk(tree):
            # An allow-list entry may be dotted (e.g. "http.client", Layer 3):
            # it then matches ONLY that exact full dotted name. The bare root
            # ("http") stays forbidden unless separately allow-listed.
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_mod = alias.name.split(".")[0]
                    if root_mod not in allowed and alias.name not in allowed:
                        failures.append(f"{py.name}: import {alias.name} not in ALLOWED_IMPORTS.txt")
            elif isinstance(node, ast.ImportFrom):
                full_mod = node.module or ""
                root_mod = full_mod.split(".")[0]
                if node.level > 0:
                    continue  # relative import inside the assistant package
                if root_mod == "__future__":
                    continue  # compiler directive, not a capability
                if root_mod == "assistant":
                    continue  # intra-package import; that module is scanned too
                if root_mod and root_mod not in allowed and full_mod not in allowed:
                    failures.append(f"{py.name}: from {node.module} import ... not in ALLOWED_IMPORTS.txt")
            elif isinstance(node, ast.Attribute):
                # os.system / os.popen style calls are forbidden even though
                # `os` itself is allowed (os.path + os.environ only).
                if isinstance(node.value, ast.Name) and node.value.id == "os":
                    if node.attr in FORBIDDEN_OS_ATTRS:
                        failures.append(f"{py.name}: os.{node.attr} is forbidden")
    return failures


def run_all_checks() -> List[str]:
    """Run every lint; returns the combined failure list."""
    failures: List[str] = []
    failures.extend(check_rule_files())
    failures.extend(check_import_policy())
    return failures


if __name__ == "__main__":
    problems = run_all_checks()
    for problem in problems:
        print(f"LINT FAIL: {problem}")
    raise SystemExit(1 if problems else 0)
