#!/usr/bin/env bash
# On-device assistant: all five suites — Layer 1 (deterministic rules),
# Layer 2 (offline retrieval), Layer 3 (optional generative), Layer 4 (issue
# drafting), and the settings layer (#120 Phase 1: natural-language settings
# editing) — rule files valid, no-executor import policy holds, historical
# regression cases match, corpus/index/search behave, generative safety
# guarantees hold, issue drafting round-trips, settings intents validate and
# gated applies hold.

set -uo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$TESTS_DIR/.." && pwd)"

source "$TESTS_DIR/helpers.sh"

run_assistant_suite() {
    local suite_dir="$1"
    if ! command -v python3 >/dev/null 2>&1; then
        echo "python3 not available; skipping assistant tests" >&2
        return 0
    fi
    # -t "$REPO_ROOT" keeps `assistant` a proper package (relative imports
    # stay valid) while discovering only this suite's tests.
    PYTHONPATH="$REPO_ROOT" python3 -m unittest discover \
        -s "$REPO_ROOT/$suite_dir" -t "$REPO_ROOT" >/dev/null 2>&1
    assert_status 0 "$?" "assistant suite $suite_dir"
}

test_assistant_layer1() {
    run_assistant_suite "assistant/diagnostics/tests"
}

test_assistant_layer2() {
    run_assistant_suite "assistant/retrieval/tests"
}

test_assistant_layer3() {
    run_assistant_suite "assistant/generative/tests"
}

test_assistant_layer4() {
    run_assistant_suite "assistant/issues/tests"
}

test_assistant_layer5() {
    run_assistant_suite "assistant/settings/tests"
}

test_assistant_brain() {
    run_assistant_suite "assistant/brain/tests"
}

test_assistant_layer1
test_assistant_layer2
test_assistant_layer3
test_assistant_layer4
test_assistant_layer5
test_assistant_brain
test_agent_suite() { run_assistant_suite "assistant/agent/tests"; }
test_scan_suite()   { run_assistant_suite "assistant/scan/tests"; }
test_cortex_suite() { run_assistant_suite "assistant/cortex/tests"; }
test_genius_suite() { run_assistant_suite "assistant/genius/tests"; }
test_agent_suite
test_scan_suite
test_cortex_suite
test_genius_suite

finish
