#!/bin/sh
set -eu

repo_root=$(CDPATH= cd "$(dirname "$0")/.." && pwd -P)
skill_dir=$repo_root/skill
validation_mode=${1:-}
case "$validation_mode" in
    ''|--release) ;;
    *) printf '%s\n' "FAIL: usage: tests/validate.sh [--release]" >&2; exit 2 ;;
esac
fail() { printf '%s\n' "FAIL: $*" >&2; exit 1; }
require_file() { [ -f "$1" ] && [ ! -L "$1" ] || fail "missing or unsafe file: $1"; }
require_text() { grep -F "$1" "$skill_dir/SKILL.md" >/dev/null || fail "missing skill marker: $1"; }
require_readme_text() { grep -F "$1" "$repo_root/README.md" >/dev/null || fail "missing README marker: $1"; }
require_file "$repo_root/tests/publish-product-forward-results.py"

validator=$(printenv SKILL_VALIDATOR || true)
if [ -z "$validator" ]; then
    home_value=$(printenv HOME || true)
    [ -n "$home_value" ] || fail "SKILL_VALIDATOR or HOME is required"
    validator=$home_value/.codex/skills/.system/skill-creator/scripts/quick_validate.py
fi
require_file "$validator"
python3 "$validator" "$skill_dir" >/dev/null

python3 - "$skill_dir" "$repo_root/README.md" "$repo_root/docs/superpowers/specs/2026-08-16-plan-convergence-output-design.md" <<'PY'
import os, stat, sys
from pathlib import Path
skill, readme, spec = map(Path, sys.argv[1:])
def fail(label): raise SystemExit("FAIL: contract: " + label)
root = skill
meta = root.lstat()
if not stat.S_ISDIR(meta.st_mode) or root.is_symlink() or meta.st_uid != os.getuid(): fail("skill root")
if sorted(path.relative_to(root).as_posix() for path in root.rglob("*")) != ["SKILL.md", "agents", "agents/openai.yaml", "scripts", "scripts/status_fingerprint.py"]: fail("runtime exact tree")
agents = root / "agents"
agents_meta = agents.lstat()
if not stat.S_ISDIR(agents_meta.st_mode) or agents.is_symlink() or agents_meta.st_uid != os.getuid(): fail("runtime agents")
for directory in (root / "scripts",):
    item = directory.lstat()
    if not stat.S_ISDIR(item.st_mode) or directory.is_symlink() or item.st_uid != os.getuid(): fail("runtime resource directory")
for path in (root / "SKILL.md", root / "agents" / "openai.yaml", root / "scripts" / "status_fingerprint.py"):
    item = path.lstat()
    if not stat.S_ISREG(item.st_mode) or path.is_symlink() or item.st_nlink != 1 or item.st_uid != os.getuid(): fail("runtime file metadata")
text = (root / "SKILL.md").read_text(encoding="utf-8")
script = (root / "scripts" / "status_fingerprint.py").read_text(encoding="utf-8")
if len(text.encode("utf-8")) > 12000: fail("SKILL.md entrypoint is too dense")
if len(script.encode("utf-8")) > 10000: fail("runtime script is too dense")
if text.count("Requirement -> Baseline -> Root cause/design gap -> Owner change -> Invariant -> Test -> Gate -> Evidence") != 1: fail("trace header cardinality")
for marker in (
    "Generation is read-only", "limits the generator only", "complete contract",
    "Fence only for one proven executable Unit",
    "do not inspect the skill package/source repository",
    "Evidence reads.used` equals the final ledger length exactly",
    "extension` is a decimal integer", "Steps: Light 1-4",
    "Verified-owner Light exactly test/closure/status; preflight only on reread mismatch",
    "dirty status != drift",
    "Light 4096/5632", "Standard 6144/10240", "Step Action+Acceptance+Failure <=420 bytes; High-risk=640",
    "Target 85%; compress/recount; never exceed", "one field/line; labels=`: `; Acceptance ends `; exit=n/a` iff Command starts `none:`; otherwise `; exit=0`. inner keys=`=`",
    "IDs/paths; no repeated rationale/schema/blanks",
    "UTF-8-sort JSON path arrays",
    "tests `gate=none`, never X->X",
    "merge metadata into that edge", "Light", "Standard", "High-risk",
    "One localized status line; Snapshot immediately next, no blank/prose",
    "keep schema labels/state tokens; copy full HEAD",
    "Evidence reads:", "Evidence ledger:", '`{"sha256":"<full-ledger digest>","rows":[{"id":path,"role":role}]}`', "Copy helper `evidence_ledger` whole; re-run and byte-compare; never reconstruct",
    "tracker|authority|design|owner|regression|integration|gate-evidence",
    "Precedence: regression>owner>gate-evidence>integration>design>authority>tracker",
    "Members: one tracker, authority, selected design/owner/exact `nearest_test`, passed-Gate evidence",
    "High-risk adds selected integration", "no unselected capability/package helpers",
    "no ledger substitution/executor receipts",
    "Gate commands don't escalate docs/config", "omit implementation when met", "exact `nearest_test`",
    "exclude fingerprint-only branch/HEAD/status unless selected", "ledger_sha256",
    "recompute once", "Step:", "Action", "Command:",
    "Files/boundary: <canonical UTF-8-sorted JSON path array>",
    "Acceptance Gate: <predicate>; exit=<0|n/a>",
    "Expected transition:", "from_revision=<snapshot through and including first Unit/Gate edge; observed-prior only afterward>",
    "transitions=<state>-><state>,<state>-><state>|none", "Evidence required:",
    "receipt=<safe relative path for state change|none>; artifacts=<nonempty comma-separated evidence>",
    "Failure/recovery:", "Verify: no ledger substitution",
    "Transition owner=selected Unit owner path, never claim",
    "Boundaries=nonempty normalized file arrays, UTF-8-sorted, never `.`",
    "labels literal `: `, never `=`",
    "state changes need safe receipts",
    "`transitions` is Unit-only; `gate` is one Gate edge/step or `none`",
    "Status: converged=all Complete/Gates passed; partially blocked=any Blocked/Failed; in progress=selected; else insufficient",
    "Keep through `Open inventory` outside", "next line opens fence; first content `Protocol profile: ...`",
    "Test command appends `&& git diff --check`",
    "`implementation`: edit only; `Command: none: <reason>`",
    "no shorthand/transition",
    "don't mix `none`/edges",
    "Baseline=current owner",
    "trace exact goal/punctuation", "Owner change starts owner",
    "Combine owner+nearest-test edits", "merge final Gate pass+unit closure",
    "Gate cell=bare comma-joined selected IDs",
    "Pre-trace only declared fields; High-risk exact: Consumer=affected_consumer; Compatibility=compatibility_gate; Rollback=rollback_evidence",
    "Closure condition", "Tracker target state", "Observed receipt requirements",
    "Never emit `observed_receipt:`/`post_closure_next_unit:`",
    "aggregate equivalence is insufficient",
    "Post-closure next unit", "Selected required gates",
    "Blocked output copies exact blocker/prerequisite identity, detail, recovery",
    "identity includes exact plugin/tool name",
    "Migration/permission/release blockers use `High-risk` status",
    "cells 6/8 start exact `nearest_test`",
    "using ` -> `, never ` | `", "`Permission matrix:` next",
    "Implementation, Tests, and Update tracker",
    "Implementation | Tests | Update tracker | Local commit | Change version | Tag | Push/release",
    "Selection basis", "Current executable unit", "Ready -> Claimed -> In Progress",
    "consumer/integration", "status-fingerprint-v1", "Open inventory:",
    "Inventory exact key order: top `units,gates,blockers`",
    "Exclude Complete units/passed Gates",
    "verbatim rows; unit.next=exact own next_convergence_condition, never next_step/recovery_condition",
    "Never alphabetize keys",
    "Gate value=own command else recovery; blocker recovery=own recovery",
    "unsigned 64-bit big-endian", "observed-prior", "Authoritative inputs",
    "input_fingerprint", "passed_evidence", "Repository: .",
    "Selected Gates are required, own selected Unit reciprocally",
):
    if marker not in text: fail("skill contract marker " + marker)
for forbidden in ("ordinary-audit-projection-v1", "first-delivery-only", "exact replay is permitted", "immutable artifact transaction", "actual tracker-bound invocation lock", "same frozen prepared", "at-least-once delivery", "Tracker receipt:", "Tracker transition receipt:", "Post-state:", "page=i/n"):
    if forbidden in text: fail("obsolete skill protocol " + forbidden)
readme_text = readme.read_text(encoding="utf-8")
for marker in ("## 复杂度分档", "## 输出合同", "## 评测与校验", "## 版本影响", "Generation is read-only", "post-capture host/evaluator", "首次有效动作事件序号", "RELEASE BLOCKED", "Gate state machine", "Selection basis", "Current executable unit", "Expected transition", "Observed receipt"):
    if marker not in readme_text: fail("README marker " + marker)
for forbidden in ("ordinary-audit-projection-v1", "first-delivery-only", "exact replay", "immutable artifact contract"):
    if forbidden in readme_text: fail("obsolete README protocol " + forbidden)
spec_text = spec.read_text(encoding="utf-8")
for marker in ("Plan Convergence Output Design v2", "Generator Side-Effect Boundary", "Snapshot Consistency", "post-capture", "Future Execution Contract"):
    if marker not in spec_text: fail("spec marker " + marker)
for forbidden in ("ordinary-audit-projection-v1", "exact replay", "pre-emission audit/replay protocol"):
    if forbidden in spec_text: fail("obsolete spec protocol " + forbidden)
PY

ruby - "$skill_dir" <<'RUBY'
require "psych"
class Failure < StandardError; end
expected_description = "Draft/refine repository-grounded Codex handoffs; route implementation, testing, review, and execution elsewhere."
expected_openai = {
  "interface" => {
    "display_name" => "Generate Codex Instructions",
    "short_description" => "Hand off repository-grounded Codex development prompts",
    "default_prompt" => "Use $generate-codex-instructions to draft a repository-grounded Codex development instruction from this project's design, code, tests, and development tracker.",
  },
  "policy" => {"allow_implicit_invocation" => true},
}
def reject_duplicate_keys(node)
  case node
  when Psych::Nodes::Mapping
    seen = {}
    node.children.each_slice(2) do |key, value|
      raise Failure, "yaml key type" unless key.is_a?(Psych::Nodes::Scalar)
      raise Failure, "yaml duplicate key" if seen.key?(key.value)
      seen[key.value] = true
      reject_duplicate_keys(value)
    end
  when Psych::Nodes::Sequence
    node.children.each { |child| reject_duplicate_keys(child) }
  when Psych::Nodes::Alias
    raise Failure, "yaml alias"
  end
end
def parse(text)
  stream = Psych.parse_stream(text)
  raise Failure, "yaml document" unless stream.children.length == 1
  reject_duplicate_keys(stream.children[0].root)
  value = Psych.safe_load(text, aliases: false, permitted_classes: [], permitted_symbols: [])
  raise Failure, "yaml mapping" unless value.instance_of?(Hash)
  value
rescue Psych::Exception => e
  raise Failure, "yaml parse #{e.class}"
end
def owned_regular(path, label)
  stat = File.lstat(path)
  raise Failure, "#{label} type" unless stat.file? && !File.symlink?(path)
  raise Failure, "#{label} links" unless stat.nlink == 1
  raise Failure, "#{label} owner" unless stat.uid == Process.uid
rescue Errno::ENOENT, Errno::ENOTDIR, Errno::ELOOP
  raise Failure, "#{label} missing"
end
begin
  root = ARGV.fetch(0)
  raise Failure, "root entries" unless Dir.children(root).sort == ["SKILL.md", "agents", "scripts"]
  raise Failure, "agents entries" unless Dir.children(File.join(root, "agents")) == ["openai.yaml"]
  raise Failure, "scripts entries" unless Dir.children(File.join(root, "scripts")) == ["status_fingerprint.py"]
  owned_regular(File.join(root, "SKILL.md"), "SKILL.md")
  owned_regular(File.join(root, "agents", "openai.yaml"), "openai.yaml")
  owned_regular(File.join(root, "scripts", "status_fingerprint.py"), "status_fingerprint.py")
  front = File.binread(File.join(root, "SKILL.md")).force_encoding(Encoding::UTF_8)
  match = /\A---\n(.*?)\n---\n/m.match(front)
  raise Failure, "frontmatter" unless match
  metadata = parse(match[1])
  raise Failure, "frontmatter keys" unless metadata.keys == ["name", "description"]
  raise Failure, "frontmatter name" unless metadata["name"] == "generate-codex-instructions"
  raise Failure, "frontmatter description" unless metadata["description"] == expected_description
  openai_text = File.read(File.join(root, "agents", "openai.yaml"))
  openai = parse(openai_text)
  tree = Psych.parse(openai_text).root
  interface_node = tree.children.each_slice(2).to_h { |key, value| [key.value, value] }.fetch("interface")
  string_nodes = interface_node.children.each_slice(2).to_h { |key, value| [key.value, value] }
  %w[display_name short_description default_prompt].each do |key|
    node = string_nodes.fetch(key)
    raise Failure, "openai metadata string quoting" unless node.is_a?(Psych::Nodes::Scalar) && node.style == Psych::Nodes::Scalar::DOUBLE_QUOTED
  end
  raise Failure, "openai metadata" unless openai == expected_openai
  puts "PASS: runtime tree and metadata"
rescue Failure => e
  warn "FAIL: runtime contract: #{e.message}"
  exit 1
end
RUBY

for script in "$repo_root/install.sh" "$repo_root/tests/run-forward-evals.sh" "$repo_root/tests/run-product-forward-eval.sh" "$repo_root/tests/test-forward-eval-runner-guards.sh" "$repo_root/tests/test-product-forward-eval-guards.sh"; do
    sh -n "$script"
    if command -v dash >/dev/null 2>&1; then dash -n "$script"; fi
    if command -v bash >/dev/null 2>&1; then bash --posix -n "$script"; fi
    if command -v busybox >/dev/null 2>&1; then busybox sh -n "$script"; fi
    if command -v shellcheck >/dev/null 2>&1; then shellcheck -s sh "$script"; fi
done

PYTHONDONTWRITEBYTECODE=1 python3 "$repo_root/tests/check-python-sources.py" \
    "$repo_root/skill/scripts/status_fingerprint.py" \
    "$repo_root/tests/check-python-sources.py" "$repo_root/tests/forward_eval_evidence.py" \
    "$repo_root/tests/status_fingerprint.py" "$repo_root/tests/execution_contract.py" \
    "$repo_root/tests/product_forward_evidence.py" "$repo_root/tests/published_result_validator.py" \
    "$repo_root/tests/validate-published-results.py" \
    "$repo_root/tests/publish-forward-eval-results.py" "$repo_root/tests/test-forward-eval-evidence.py" \
    "$repo_root/tests/test-forward-eval-publisher-guards.py" \
    "$repo_root/tests/test-forward-eval-publisher.py" \
    "$repo_root/tests/publish-product-forward-results.py" \
    "$repo_root/tests/test-product-forward-publisher.py" \
    "$repo_root/tests/test-status-fingerprint.py" "$repo_root/tests/test-execution-contract.py" \
    "$repo_root/tests/test-published-result-validator.py" \
    "$repo_root/tests/check-impact-classifier.py" \
    "$repo_root/tests/test-python-source-checker.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$repo_root/tests/test-python-source-checker.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$repo_root/tests/check-impact-classifier.py"
for eval_json in "$repo_root"/evals/*.json; do python3 -m json.tool "$eval_json" >/dev/null; done

python3 - "$repo_root" <<'PY'
import json, re, sys
from pathlib import Path
root = Path(sys.argv[1])
cases = json.loads((root / "evals/cases.json").read_text(encoding="utf-8"))
expected = {"chinese-mixed-state-first-delivery", "english-localization", "complete-plan", "insufficient-information", "generic-blocker", "light-documentation", "high-risk-public-consumer", "correct-prerequisite-blocker", "migration-permission-release-blocker", "tracker-none-projection", "tracker-injection", "ordinary-implementation", "tracker-path-escape", "concurrency-conflict", "snapshot-double-drift", "plugin-prerequisites", "git-permission-split", "fence-safety", "product-forward-closure"}
actual = {item["id"] for item in cases["cases"]}
if actual != expected: raise SystemExit("FAIL: eval corpus case IDs")
runner_source = (root / "tests/run-forward-evals.sh").read_text(encoding="utf-8")
for case_id in expected - {"product-forward-closure"}:
    if case_id not in runner_source: raise SystemExit("FAIL: forward runner missing case " + case_id)
if "product-forward-label-validation" not in (root / "tests/run-product-forward-eval.sh").read_text(encoding="utf-8"):
    raise SystemExit("FAIL: product runner missing product case")
version = (root / "VERSION").read_text(encoding="ascii").strip()
if re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version) is None: raise SystemExit("FAIL: VERSION")
print("PASS: corpus routing contract")
PY

release_state=$(PYTHONDONTWRITEBYTECODE=1 python3 "$repo_root/tests/validate-published-results.py" "$repo_root")

sh "$repo_root/tests/test-forward-eval-runner-guards.sh" "$repo_root/tests/run-forward-evals.sh"
sh "$repo_root/tests/test-product-forward-eval-guards.sh" "$repo_root/tests/run-product-forward-eval.sh"
PYTHONDONTWRITEBYTECODE=1 python3 "$repo_root/tests/test-forward-eval-evidence.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$repo_root/tests/test-forward-eval-publisher-guards.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$repo_root/tests/test-forward-eval-publisher.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$repo_root/tests/test-product-forward-publisher.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$repo_root/tests/test-status-fingerprint.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$repo_root/tests/test-execution-contract.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$repo_root/tests/test-published-result-validator.py"

install_root=$(mktemp -d /tmp/gci-install-check.XXXXXX)
chmod 0700 "$install_root"
trap 'chmod -R u+w "$install_root" 2>/dev/null || :; rm -rf "$install_root"' EXIT HUP INT TERM
CODEX_SKILLS_DIR="$install_root/skills" HOME= "$repo_root/install.sh" >/dev/null
[ -L "$install_root/skills/generate-codex-instructions" ] || fail "install link"
installed=$(CDPATH= cd "$install_root/skills/generate-codex-instructions" && pwd -P)
[ "$installed" = "$skill_dir" ] || fail "install target"
CODEX_SKILLS_DIR="$install_root/skills" HOME= "$repo_root/install.sh" >/dev/null
if CODEX_SKILLS_DIR=relative HOME= "$repo_root/install.sh" >/dev/null 2>&1; then fail "relative install target accepted"; fi
if env -u HOME -u CODEX_SKILLS_DIR "$repo_root/install.sh" >/dev/null 2>&1; then fail "missing HOME accepted"; fi
conflict_root=$install_root/conflict
mkdir -p "$conflict_root"
printf '%s\n' occupied >"$conflict_root/generate-codex-instructions"
if CODEX_SKILLS_DIR="$conflict_root" HOME= "$repo_root/install.sh" >/dev/null 2>&1; then fail "occupied install target accepted"; fi
other_root=$install_root/other
mkdir -p "$other_root" "$install_root/symlink-root"
ln -s "$other_root" "$install_root/symlink-root/generate-codex-instructions"
if CODEX_SKILLS_DIR="$install_root/symlink-root" HOME= "$repo_root/install.sh" >/dev/null 2>&1; then fail "foreign install symlink accepted"; fi
if [ "$release_state" = blocked ]; then
    printf '%s\n' "RELEASE BLOCKED: fresh behavior evidence is incomplete or not authorized" >&2
    [ "$validation_mode" = --release ] && exit 2
fi
printf '%s\n' "PASS: deterministic skill validation"
