#!/bin/sh
set -eu

# Opt-in product-behavior eval: generate a handoff, execute it in a fresh
# session, and verify owner, regression, acceptance, and tracker closure.
repo_root=$(CDPATH= cd "$(dirname "$0")/.." && pwd -P)
product_case=product-forward-label-validation
command -v codex >/dev/null 2>&1 || {
    printf '%s\n' "BLOCKED: codex executable is unavailable" >&2
    exit 2
}
eval_timeout_seconds=${PRODUCT_FORWARD_TIMEOUT_SECONDS:-600}
case $eval_timeout_seconds in
    '' | *[!0-9]*)
        printf '%s\n' "FAIL: PRODUCT_FORWARD_TIMEOUT_SECONDS must be a positive integer" >&2
        exit 2
        ;;
    0)
        printf '%s\n' "FAIL: PRODUCT_FORWARD_TIMEOUT_SECONDS must be positive" >&2
        exit 2
        ;;
esac

run_root=$(mktemp -d /tmp/gci-product-forward-XXXXXX)
chmod 0700 "$run_root"
capture_root=${PRODUCT_FORWARD_CAPTURE_DIR:-}
if [ -n "$capture_root" ]; then
    case "$capture_root" in
        /tmp/*) ;;
        *) printf '%s\n' "FAIL: PRODUCT_FORWARD_CAPTURE_DIR must be below /tmp" >&2; exit 2 ;;
    esac
    [ ! -e "$capture_root" ] && [ ! -L "$capture_root" ] || {
        printf '%s\n' "FAIL: PRODUCT_FORWARD_CAPTURE_DIR already exists" >&2
        exit 2
    }
    mkdir "$capture_root"
    chmod 0700 "$capture_root"
fi
stage=fixture-setup
cleanup() {
    exit_status=$?
    trap - EXIT HUP INT TERM
    if [ "$exit_status" -ne 0 ]; then
        printf '%s\n' "FAIL: product forward eval stopped during $stage (exit $exit_status)" >&2
    fi
    if [ -n "$capture_root" ] && [ -d "$run_root" ]; then
        if [ "$exit_status" -eq 0 ] && [ -d "$run_root/product-capture" ]; then
            cp -R "$run_root/product-capture/." "$capture_root/"
        else
            cp -R "$run_root/." "$capture_root/"
        fi
        chmod -R u-w,go-rwx "$capture_root" 2>/dev/null || :
    fi
    chmod -R u+w "$run_root" 2>/dev/null || :
    rm -rf "$run_root"
    exit "$exit_status"
}
trap cleanup EXIT HUP INT TERM

fixture=$run_root/fixture
product_capture=$run_root/product-capture
snapshot_fixture() {
    python3 - "$fixture" "$1" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

root = Path(sys.argv[1])
entries = []
for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix().encode("utf-8")):
    relative = path.relative_to(root).as_posix()
    if relative == ".git" or relative.startswith(".git/"):
        continue
    metadata = path.lstat()
    if stat.S_ISREG(metadata.st_mode):
        value = path.read_bytes()
        entries.append({"path": relative, "kind": "file", "mode": stat.S_IMODE(metadata.st_mode), "sha256": hashlib.sha256(value).hexdigest()})
    elif stat.S_ISDIR(metadata.st_mode):
        entries.append({"path": relative, "kind": "directory", "mode": stat.S_IMODE(metadata.st_mode)})
    elif stat.S_ISLNK(metadata.st_mode):
        entries.append({"path": relative, "kind": "symlink", "target": os.readlink(path)})
    else:
        entries.append({"path": relative, "kind": "special"})
Path(sys.argv[2]).write_text(json.dumps(entries, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
PY
}
cleanup_evaluator_graph() {
    graph_dir=$fixture/.code-review-graph
    [ -e "$graph_dir" ] || [ -L "$graph_dir" ] || return 0
    python3 - "$graph_dir" <<'PY'
import os
from pathlib import Path
import stat
import sys

root = Path(sys.argv[1])
metadata = root.lstat()
if (
    not stat.S_ISDIR(metadata.st_mode)
    or root.is_symlink()
    or metadata.st_uid != os.getuid()
    or stat.S_IMODE(metadata.st_mode) != 0o700
):
    raise SystemExit("FAIL: unsafe evaluator graph directory")
entries = sorted(path.name for path in root.iterdir())
if entries != [".gitignore", "graph.db"]:
    raise SystemExit("FAIL: unexpected evaluator graph entry")
for name in entries:
    path = root / name
    item = path.lstat()
    if (
        not stat.S_ISREG(item.st_mode)
        or path.is_symlink()
        or item.st_nlink != 1
        or item.st_uid != os.getuid()
        or stat.S_IMODE(item.st_mode) != 0o600
    ):
        raise SystemExit("FAIL: unsafe evaluator graph file")
PY
    rm -- "$graph_dir/.gitignore" "$graph_dir/graph.db"
    rmdir -- "$graph_dir"
}
validate_generator_log() {
    PYTHONDONTWRITEBYTECODE=1 python3 "$repo_root/tests/tool_access_evidence.py" \
        "$product_case" "$1" "$product_capture/generation-tool-access-evidence.json" --executable
}
mkdir -p "$fixture/docs" "$fixture/src" "$fixture/tests" "$fixture/.project/development"
mkdir "$product_capture"
cat >"$fixture/.gitignore" <<'EOF'
.project/
.code-review-graph/
EOF
cat >"$fixture/AGENTS.md" <<'EOF'
# Product forward fixture

- The sole tracker is `.project/development/`.
- Its plan anchor is `.project/development/task_plan.md`.
- Generation is strictly read-only; `.project/development/progress.md` is executor-owned evidence only.
- The selected owner is `src/normalize_label.py`; the nearest regression test is `tests/test_normalize_label.py`.
- Branch, HEAD, and raw status are fingerprint inputs, not generation Evidence ledger rows; add helper IDs only when the selected unit explicitly requires them.
- The executor must record `Ready->Claimed,Claimed->In Progress` immediately before the first implementation write, implement the selected unit, run its tests, and record gate/completion closure only after the gate passes.
- Each state-changing tracker checkpoint increments the numeric revision suffix by one and appends `observed_receipt: unit=<id>; owner=<path>; transitions=<state>-><state>,<state>-><state>|none; revision=<actual before>-><actual after>; gate=<actual transition|none>; evidence=<relative path>` to progress.
- Claim checkpoints use `.project/development/progress.md` as receipt evidence; closure checkpoints use `.project/development/task_plan.md` after the tracker fields are persisted.
- After closure append `post_closure_next_unit: <id|none>` based on the resulting dependency graph.
- Do not commit, change versions, tag, push, release, deploy, or access providers.
EOF
cat >"$fixture/docs/design.md" <<'EOF'
# Label normalization contract

`normalize_label` accepts a string and returns its trimmed form. Empty and
whitespace-only labels must raise `ValueError`; non-string values must keep
raising `TypeError`. The public function name and module path are stable.
EOF
cat >"$fixture/src/normalize_label.py" <<'EOF'
def normalize_label(value):
    if not isinstance(value, str):
        raise TypeError("label must be a string")
    return value.strip()
EOF
cat >"$fixture/src/__init__.py" <<'EOF'
EOF
cat >"$fixture/tests/test_normalize_label.py" <<'EOF'
import unittest

from src.normalize_label import normalize_label


class NormalizeLabelTest(unittest.TestCase):
    def test_trims_valid_label(self):
        self.assertEqual(normalize_label("  alpha  "), "alpha")

    def test_rejects_non_string(self):
        with self.assertRaises(TypeError):
            normalize_label(None)


if __name__ == "__main__":
    unittest.main()
EOF
cat >"$fixture/.project/development/progress.md" <<'EOF'
# Progress

- revision: r1
  event: fixture baseline established
  transition: baseline -> Ready
EOF
cat >"$fixture/.project/development/lessons.md" <<'EOF'
# Lessons

- Keep the public function path stable and add the nearest regression test.
EOF
cat >"$fixture/.project/development/task_plan.md" <<'EOF'
# Development tracker

schema_version: 2
tracker_revision: r1
goal: Enforce the documented empty-label validation contract.

## Unit registry

### U1

state: Ready
selected: true
priority: 1
independently_executable: true
goal: Reject empty and whitespace-only labels at the owner boundary.
owner: src/normalize_label.py
authoritative_design: docs/design.md
nearest_test: tests/test_normalize_label.py
scope: Change only the normalization owner and its focused regression test.
next_step: Add the ValueError guard and regression test, then run the focused unittest gate.
next_convergence_condition: G1 passes at the current tracker revision and the owner records U1 Complete.
gate_refs: G1
invariants: Valid labels remain trimmed; non-string values still raise TypeError; the public function path stays stable.
non_goals: API redesign, dependencies, packaging, version, commit, release, or unrelated refactor.

## Required gate registry

### G1

required: true
status: pending
gate_type: acceptance
owners: U1
command: python3 -m unittest discover -s tests -v
inputs_json: __SELECTED_INPUTS_JSON__
input_fingerprint: __SELECTED_INPUT_FINGERPRINT__
passed_evidence: none
evidence: The executor must run the acceptance command after the owner and regression test changes.
recovery_condition: Implement U1, run the exact acceptance command, and record the current passing result.

## Decisions and blockers

selection_decision: Select U1 because it is the sole Ready, independently executable unit and has no unmet dependency.
EOF

python3 - "$fixture" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
tracker = root / ".project/development/task_plan.md"
text = tracker.read_text(encoding="utf-8")
paths = ["src/normalize_label.py", "tests/test_normalize_label.py"]
records = [
    {"path": relative, "sha256": hashlib.sha256((root / relative).read_bytes()).hexdigest()}
    for relative in paths
]
inputs_json = json.dumps(paths, ensure_ascii=False, separators=(",", ":"))
input_fingerprint = hashlib.sha256(
    (json.dumps(records, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
).hexdigest()
tracker.write_text(
    text.replace("__SELECTED_INPUTS_JSON__", inputs_json).replace("__SELECTED_INPUT_FINGERPRINT__", input_fingerprint),
    encoding="utf-8",
)
PY

git -C "$fixture" init -q -b product-forward
git -C "$fixture" config user.name 'Product Forward Eval'
git -C "$fixture" config user.email 'product-forward@example.invalid'
git -C "$fixture" add -- .gitignore AGENTS.md docs src tests
GIT_AUTHOR_DATE='2000-01-01T00:00:00+0000' \
GIT_COMMITTER_DATE='2000-01-01T00:00:00+0000' \
    git -C "$fixture" commit -q -m 'fixture: establish label owner baseline'

cp "$fixture/src/normalize_label.py" "$product_capture/owner-before.py"
cp "$fixture/tests/test_normalize_label.py" "$product_capture/regression-before.py"
cp "$fixture/.project/development/task_plan.md" "$product_capture/tracker-before.md"
cp "$fixture/.project/development/progress.md" "$product_capture/progress-before.md"
cp "$fixture/.project/development/lessons.md" "$product_capture/lessons-before.md"
cp "$fixture/AGENTS.md" "$product_capture/agents-before.md"
cp "$fixture/docs/design.md" "$product_capture/design-before.md"
git -C "$fixture" symbolic-ref --quiet --short HEAD >"$product_capture/git-branch-before.txt"
git -C "$fixture" rev-parse --verify HEAD >"$product_capture/git-head-before.txt"
git -C "$fixture" status --porcelain=v1 -z --untracked-files=all >"$product_capture/git-status-before-z.bin"

PYTHONDONTWRITEBYTECODE=1 python3 - "$repo_root" "$product_capture/runtime-snapshot.json" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

repo = Path(sys.argv[1])
sys.path.insert(0, str(repo / "tests"))
from product_forward_evidence import RUNTIME_SNAPSHOT_FILES

files = []
for relative in RUNTIME_SNAPSHOT_FILES:
    value = (repo / relative).read_bytes()
    files.append({"path": relative, "bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()})
Path(sys.argv[2]).write_text(
    json.dumps({"schema_version": 1, "files": files}, ensure_ascii=False, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
PY

generation_prompt=$run_root/generation-prompt.txt
generation_raw_draft=$run_root/generation-raw-draft.txt
generation_draft=$run_root/generation-draft.txt
generation_output=$run_root/generation-output.txt
generation_log=$run_root/generation.log
generation_snapshot_before=$run_root/generation-snapshot-before.json
generation_snapshot_after=$run_root/generation-snapshot-after.json
snapshot_fixture "$generation_snapshot_before"
cat >"$generation_prompt" <<EOF
Use the generate-codex-instructions skill at $repo_root/skill/SKILL.md to generate the next Codex development handoff for this repository. Respond entirely in English. Do not implement the task, run its acceptance test, modify repository or tracker state, commit, or publish. Return only the final user-facing handoff.
EOF
stage=generation
PYTHONDONTWRITEBYTECODE=1 timeout "$eval_timeout_seconds" \
    codex exec --ephemeral --sandbox workspace-write --add-dir "$fixture" \
    -C "$fixture" -o "$generation_raw_draft" - <"$generation_prompt" \
    >"$generation_log" 2>&1
cleanup_evaluator_graph
validate_generator_log "$generation_log"
snapshot_fixture "$generation_snapshot_after"
python3 - "$generation_raw_draft" "$generation_draft" "$fixture" "$repo_root" <<'PY'
from pathlib import Path
import re
import sys

HOST_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._-])/(?:home|Users|root|etc|var|tmp)/[^\s`\"'<>|;,)\]}]+"
)

text = Path(sys.argv[1]).read_bytes().decode("utf-8")
text = text.replace("\r\n", "\n").replace("\r", "\n")
text = "\n".join(line.rstrip(" \t") for line in text.split("\n")).rstrip("\n") + "\n"
text = text.replace(sys.argv[3], "<disposable-fixture>").replace(sys.argv[4], "<skill-repository>")
text = HOST_PATH_PATTERN.sub("<host-path>", text)
Path(sys.argv[2]).write_text(text, encoding="utf-8")
PY
PYTHONDONTWRITEBYTECODE=1 python3 "$repo_root/skill/scripts/assemble_handoff.py" \
    --mode executable --repository "$fixture" \
    --tracker .project/development/task_plan.md --unit U1 --profile Standard \
    --draft "$generation_draft" --output "$generation_output" \
    --manifest "$product_capture/generation-assembly-manifest.json" \
    --preamble-output "$product_capture/generation-assembly-preamble.txt" \
    --context-output "$product_capture/generation-assembly-context.json"
sed "s|$repo_root|<skill-repository>|g" "$generation_prompt" >"$product_capture/generation-prompt.txt"
cp "$generation_draft" "$product_capture/generation-draft.txt"
cp "$generation_output" "$product_capture/generation-response.txt"

stage=generation-contract-validation
PYTHONDONTWRITEBYTECODE=1 python3 - "$repo_root/tests" "$generation_output" "$run_root/execution-prompt.txt" "$fixture" "$generation_snapshot_before" "$generation_snapshot_after" <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from execution_contract import ContractError, parse_handoff
from product_forward_evidence import ProductEvidenceError, validate_generated_grounding

output = Path(sys.argv[2]).read_text(encoding="utf-8")
fixture = Path(sys.argv[4])
tracker_before = Path(sys.argv[5]).read_bytes()
tracker_after = Path(sys.argv[6]).read_bytes()
if tracker_before != tracker_after:
    raise SystemExit("FAIL: generation changed the target repository")
if any(marker in output for marker in ("/tmp/", "/home/", "/Users/", "/root/", "/etc/", "/var/")):
    raise SystemExit("FAIL: generation output path contract")
try:
    parsed = parse_handoff(output)
except ContractError as error:
    raise SystemExit("FAIL: generated execution contract: " + str(error)) from error
if parsed["profile"] != "Standard" or parsed["selected"] != "U1":
    raise SystemExit("FAIL: product handoff selected the wrong profile or unit")
try:
    validate_generated_grounding(Path(sys.argv[3]).parent / "product-capture", parsed)
except ProductEvidenceError as error:
    raise SystemExit("FAIL: generated execution grounding: " + str(error)) from error
body_text = parsed["body"]
required = (
    "Closure condition", "Tracker target state", "Observed receipt requirements", "Post-closure next unit",
    "Requirement -> Baseline -> Root cause/design gap -> Owner change -> Invariant -> Test -> Gate -> Evidence",
    "Implementation | Tests | Update tracker | Local commit | Change version | Tag | Push/release",
    "src/normalize_label.py", "tests/test_normalize_label.py",
    "python3 -m unittest discover -s tests -v",
)
missing = [marker for marker in required if marker not in output]
if missing:
    raise SystemExit("FAIL: generated execution contract missing: " + ", ".join(missing))
progress = fixture / ".project/development/progress.md"
if b"ordinary-audit-projection-v1" in progress.read_bytes():
    raise SystemExit("FAIL: generation wrote an obsolete audit record")
Path(sys.argv[3]).write_text(
    "Execute the following generated handoff in the current repository. Follow its evidence, failure, scope, tracker, and permission rules exactly. Do not add authority or use facts not present in the repository or handoff. Return a truthful execution report using repository-relative plain paths only; never emit host, evaluator, or temporary absolute paths. Persist structured tracker keys observed_receipt: and post_closure_next_unit: at column 1 with no Markdown bullets, fences, or decoration.\n\n" + body_text,
    encoding="utf-8",
)
PY

cp "$run_root/execution-prompt.txt" "$product_capture/execution-prompt.txt"

execution_output=$run_root/execution-output.txt
execution_log=$run_root/execution.log
stage=execution
PYTHONDONTWRITEBYTECODE=1 timeout "$eval_timeout_seconds" \
    codex exec --ephemeral --sandbox workspace-write --add-dir "$fixture" \
    -C "$fixture" -o "$execution_output" - <"$run_root/execution-prompt.txt" \
    >"$execution_log" 2>&1
cleanup_evaluator_graph

stage=closure-validation
PYTHONDONTWRITEBYTECODE=1 python3 - "$repo_root/tests" "$fixture" "$execution_output" "$product_capture" <<'PY'
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, sys.argv[1])
from product_forward_evidence import derive_product_result, write_capture_manifest

fixture = Path(sys.argv[2])
execution_output = Path(sys.argv[3])
capture = Path(sys.argv[4])
shutil.copyfile(execution_output, capture / "execution-response.txt")
shutil.copyfile(fixture / "src/normalize_label.py", capture / "owner-after.py")
shutil.copyfile(fixture / "tests/test_normalize_label.py", capture / "regression-after.py")
shutil.copyfile(fixture / ".project/development/task_plan.md", capture / "tracker-after.md")
shutil.copyfile(fixture / ".project/development/progress.md", capture / "progress-after.md")
test_run = subprocess.run(
    ("python3", "-m", "unittest", "discover", "-s", "tests", "-v"),
    cwd=fixture,
    capture_output=True,
    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
)
acceptance_output = test_run.stdout + test_run.stderr
(capture / "acceptance-command.txt").write_text("python3 -m unittest discover -s tests -v\n", encoding="utf-8")
(capture / "acceptance-output.txt").write_bytes(acceptance_output)
(capture / "acceptance-exit.txt").write_text(str(test_run.returncode) + "\n", encoding="ascii")
status = subprocess.check_output(
    ("git", "-C", str(fixture), "status", "--porcelain=v1", "-z", "--untracked-files=all")
)
(capture / "git-status-z.bin").write_bytes(status)
patch = subprocess.check_output(
    (
        "git", "-C", str(fixture), "diff", "--no-ext-diff", "--binary", "--",
        "src/normalize_label.py", "tests/test_normalize_label.py",
    )
)
(capture / "git-diff.patch").write_bytes(patch)
write_capture_manifest(capture)
result = derive_product_result(capture)
print("case=" + result["case"] + " closure_rate=" + str(result["metrics"]["closure_rate"]))
PY
printf '%s\n' "capture_case=$product_case"
stage=complete
