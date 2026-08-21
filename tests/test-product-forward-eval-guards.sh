#!/bin/sh
set -eu

[ "$#" -eq 1 ] || {
    printf '%s\n' "usage: test-product-forward-eval-guards.sh RUNNER" >&2
    exit 2
}
runner=$1
[ -f "$runner" ] && [ ! -L "$runner" ] || {
    printf '%s\n' "FAIL: product runner is not a regular file" >&2
    exit 1
}

require_text() {
    grep -F "$1" "$runner" >/dev/null || {
        printf '%s\n' "FAIL: product runner missing: $1" >&2
        exit 1
    }
}

require_text 'Do not implement the task, run its acceptance test, modify repository or tracker state, commit, or publish.'
require_text 'Execute the following generated handoff in the current repository.'
require_text 'Do not add authority or use facts not present in the repository or handoff.'
require_text 'repository-relative plain paths only; never emit host, evaluator, or temporary absolute paths.'
require_text 'Persist structured tracker keys observed_receipt: and post_closure_next_unit: at column 1 with no Markdown bullets, fences, or decoration.'
require_text 'parsed["profile"] != "Standard" or parsed["selected"] != "U1"'
require_text 'from execution_contract import ContractError, parse_handoff'
require_text 'validate_generated_grounding'
require_text 'generation changed the target repository'
require_text 'snapshot_fixture'
require_text 'generation wrote an obsolete audit record'
require_text 'src/normalize_label.py'
require_text 'tests/test_normalize_label.py'
require_text 'python3 -m unittest discover -s tests -v'
require_text 'from product_forward_evidence import derive_product_result, write_capture_manifest'
require_text 'generation-response.txt'
require_text 'execution-response.txt'
require_text 'owner-before.py'
require_text 'agents-before.md'
require_text 'design-before.md'
require_text 'lessons-before.md'
require_text 'git-branch-before.txt'
require_text 'git-head-before.txt'
require_text 'git-status-before-z.bin'
require_text 'owner-after.py'
require_text 'tracker-before.md'
require_text 'tracker-after.md'
require_text 'acceptance-output.txt'
require_text 'git-status-z.bin'
require_text 'git-diff.patch'
require_text 'closure_rate'
require_text 'observed_receipt:'
require_text 'post_closure_next_unit:'
require_text 'PRODUCT_FORWARD_CAPTURE_DIR'
require_text 'product forward eval stopped during'
require_text '.code-review-graph/'
require_text 'cleanup_evaluator_graph'
require_text 'unexpected evaluator graph entry'

if grep -F 'product-result.json' "$runner" >/dev/null; then
    printf '%s\n' "FAIL: product runner must not aggregate metrics" >&2
    exit 1
fi

for forbidden in \
    'revision_after: r2' \
    'Append these exact bare receipt lines' \
    'page=1/1; units=' \
    'Evidence reads: used=5' \
    'This is Standard because'; do
    if grep -F "$forbidden" "$runner" >/dev/null; then
        printf '%s\n' "FAIL: product runner leaks answer: $forbidden" >&2
        exit 1
    fi
done

session_count=$(grep -F -c 'codex exec --ephemeral --sandbox workspace-write' "$runner")
[ "$session_count" -eq 2 ] || {
    printf '%s\n' "FAIL: product runner must use exactly two fresh sessions" >&2
    exit 1
}

printf '%s\n' "PASS: product forward runner closure guards"
