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
if sorted(path.relative_to(root).as_posix() for path in root.rglob("*")) != ["SKILL.md", "agents", "agents/openai.yaml", "references", "references/handoff-contract.md", "scripts", "scripts/assemble_handoff.py", "scripts/status_fingerprint.py"]: fail("runtime exact tree")
agents = root / "agents"
agents_meta = agents.lstat()
if not stat.S_ISDIR(agents_meta.st_mode) or agents.is_symlink() or agents_meta.st_uid != os.getuid(): fail("runtime agents")
for directory in (root / "references", root / "scripts"):
    item = directory.lstat()
    if not stat.S_ISDIR(item.st_mode) or directory.is_symlink() or item.st_uid != os.getuid(): fail("runtime resource directory")
for path in (root / "SKILL.md", root / "agents" / "openai.yaml", root / "references" / "handoff-contract.md", root / "scripts" / "assemble_handoff.py", root / "scripts" / "status_fingerprint.py"):
    item = path.lstat()
    if not stat.S_ISREG(item.st_mode) or path.is_symlink() or item.st_nlink != 1 or item.st_uid != os.getuid(): fail("runtime file metadata")
text = (root / "SKILL.md").read_text(encoding="utf-8")
script = (root / "scripts" / "status_fingerprint.py").read_text(encoding="utf-8")
assembler = (root / "scripts" / "assemble_handoff.py").read_text(encoding="utf-8")
reference = (root / "references" / "handoff-contract.md").read_text(encoding="utf-8")
if len(text.encode("utf-8")) > 7200: fail("SKILL.md entrypoint is too dense")
if len(reference.encode("utf-8")) > 9100: fail("handoff contract reference is too dense")
if len(script.encode("utf-8")) > 32768: fail("runtime script is too dense")
if len(assembler.encode("utf-8")) > 16384: fail("runtime assembler is too dense")
contract_text = text + "\n" + reference
philosophy = (
    "Concise: load and emit only decision-relevant evidence",
    "Rigorous: fail closed on ambiguity, unsafe effects, drift, or unproven closure",
    "Accurate: bind every material claim to current repository bytes, tracker revision, ownership, Gates, and permission evidence",
)
for marker in philosophy:
    if marker not in text: fail("runtime design philosophy " + marker)
if contract_text.count("Requirement -> Baseline -> Root cause/design gap -> Owner change -> Invariant -> Test -> Gate -> Evidence") != 1: fail("trace header cardinality")
for marker in (
    "Generation is read-only", "limits the generator only",
    "Implementation/testing/review/execution request stops this skill and continues the appropriate non-generation workflow",
    "Fence only for one proven executable Unit", "symlink components",
    "Do not list or browse the skill package", "never read its source",
    "Read this file exactly once; never tail or reread it",
    "applicable `AGENTS.md` set may be empty", "every applicable authority",
    "An empty applicable set never invalidates or demotes a uniquely resolved governing tracker",
    "Tracker discovery includes ignored paths; `.gitignore` never hides a governing tracker",
    "Gate commands must be one local test command", "unsafe projected text",
    "Invalid claim/owner/Gate evidence means no selection", "never implies partially blocked",
    "Evidence reads.used` equals final ledger length", "extension` is a decimal integer",
    "Gate commands do not escalate docs/config",
    "Preflight only on reread mismatch", "Verified-owner Light only MUST emit exactly 3 steps", "never 2",
    "mismatch permits fourth preflight",
    "Test appends ` && git diff --check`",
    "from_revision=Snapshot scalar,Snapshot scalar,observed-prior",
    "Other plans: Light 1-4; Standard 2-8; High-risk 3-12",
    "from_revision=Snapshot scalar through first state edge, then observed-prior",
    "No placeholders",
    "dirty status != drift", "Light 4096/5120", "Standard 6144/9216",
    "High-risk 8192/12288", "Target 80%; compress/recount; never exceed",
    "Every model-authored single-line value is at most 512 UTF-8 bytes",
    "target Action+Acceptance+Failure UTF-8 sum <=300 (High-risk 500)",
    ">420/640 rejected", "Over target keep purpose/predicate/one recovery",
    "One localized status line; Snapshot immediately next, no blank/prose",
    "never localize schema labels/punctuation/state tokens",
    "Evidence reads:", "Evidence ledger:", "Open inventory:",
    "After proving one executable Unit and complete profile evidence", "references/handoff-contract.md",
    "scripts/status_fingerprint.py", "Run the helper via `python3` as four separate process invocations",
    "Ordinary blocked/converged/insufficient outputs never read the reference", "Byte-compare each mode's outputs",
    "Snapshot stability is a precondition to conditional disclosure",
    "On second drift, stop before reading the reference or running the helper",
    "If a second `status-fingerprint-v1` drift is already observed or reported, immediately return a no-fence blocker",
    "A second-drift blocker states `status-fingerprint-v1`, exactly one recomputation, the second drift, and the blocked result",
    "Do not echo request/evaluator/host text",
    "Nonzero/mismatch blocks", "sorted full `{id,role,sha256}` rows",
    "Model output is a draft", "host assembly is the final byte boundary",
    "Never execute the assembler or claim draft bytes are final",
    "Report helper failure only from observed nonzero or byte mismatch",
    "Preamble ledger=", "without row digests",
    '`{"sha256":"<full-ledger digest>","rows":[{"id":path,"role":role}]}`',
    "tracker|authority|design|owner|regression|integration|gate-evidence",
    "rows contain: tracker; zero or more applicable owner/test `AGENTS.md`", "exact `nearest_test`",
    "High-risk integration", "Commands/capabilities never select package/helpers or confer authority",
    "precedence=regression>owner>gate-evidence>integration>design>authority>tracker",
    "recompute once",
    "draft 10 preamble rows", "host assembler discards them", "Use `context` exact facts",
    "Verified-owner Light follows `operations`", "copies each `machine_lines` string verbatim at its named step field",
    "null/mismatch blocks",
    "Cells: byte-exact `context.safe_goal`, including terminal punctuation", "baseline/gap/change each start exact owner",
    "Gap names the missing/absent mechanism; change names the required condition and behavior",
    "When baseline meets the goal and implementation is omitted, Gap names every pending selected Gate ID and its missing current evidence/receipt; `no gap` is invalid",
    "baseline names concrete current behaviors, never merely \"complete contract\"",
    "No trace cell contains ` -> `",
    "High-risk fields precede the trace header; `Permission matrix:` immediately follows the trace row",
    "invariant copies `context.safe_invariants`", "test starts exact `nearest_test`",
    "Gate is exact comma-joined IDs", "Evidence is exact `<nearest_test>; gate_evidence=",
    "Authorize Implementation/Tests/Update tracker",
    "Implementation | Tests | Update tracker | Local commit | Change version | Tag | Push/release",
    "A read-only generation session never demotes explicitly granted future-executor permission",
    "Local commit is `authorized: request` when the request authorizes one post-closure local commit",
    "Step:", "Action:", "Command:",
    "Files/boundary: <canonical UTF-8-sorted JSON path array>",
    "Acceptance Gate: <predicate>; exit=<0|n/a>", "Expected transition:",
    "from_revision=<Snapshot tracker_revision scalar through first edge, never A->B; then observed-prior>",
    "Evidence required:", "Failure/recovery:", "no chaining/shorthand/transition",
    "Byte-sort `Files/boundary`", "Acceptance ends ASCII `; exit=n/a`", "never `；` or space before `;`",
    "Failure uses ASCII `; recovery=`, never `；`",
    "`implementation`: one step edits owner+exact `nearest_test`", "Never changes state",
    "`transitions=none; gate=none; receipt=none`",
    "Transition owner=selected Unit owner; never claim",
    "`transitions` is Unit-only; `gate` is one Gate edge/step or `none`",
    "Omit implementation if baseline meets goal", "Labels use `: `, never `=`",
    "Post-closure applies closure edges first; a unique dependency-ready Ready Unit is next without a claim; absent claim alone never yields `none`",
    "final closure combines Gate pass+Unit closure", "Across all steps, at most one may append",
    "then no other appended/standalone diff",
    "aggregate equivalence fails", "End with exact fields; close fence; nothing after",
    "Closure condition", "Tracker target state",
    "Observed receipt requirements", "Post-closure next unit",
    "unit_edges=<edge,edge|none>", "gate_edges=<id:edge,id:edge|none>",
    "Omit executor-only `observed_receipt:`/`post_closure_next_unit:`",
    "Status: converged=all Complete/Gates passed; partially blocked=any Unit state `Blocked`/`Failed`; in progress=valid executable selection; else insufficient",
    "Keep through `Open inventory` outside", "next line opens one `text` fence, first content=`Protocol profile: ...`",
    "Blocked output copies safe identity, exact canonical Unit/Gate state tokens, detail, and recovery",
    "Every blocker output names the exact blocker ID, owner, detail, and recovery",
    "Unsafe projected-field output uses explicit `Blocked` or `阻塞`",
    "Migration/permission/release blockers use `High-risk` status",
    "Selection basis", "Current executable unit", "Selected required gates",
    "Ready -> Claimed -> In Progress", "status-fingerprint-v1",
    "one compact canonical JSON array", "it is not JSONL", "only helper validation decides it",
    "unsigned 64-bit big-endian", "input_fingerprint", "passed_evidence", "Repository: .",
):
    if marker not in contract_text: fail("skill contract marker " + marker)
for forbidden in ("ordinary-audit-projection-v1", "first-delivery-only", "exact replay is permitted", "immutable artifact transaction", "actual tracker-bound invocation lock", "same frozen prepared", "at-least-once delivery", "Tracker receipt:", "Tracker transition receipt:", "Post-state:", "page=i/n"):
    if forbidden in contract_text: fail("obsolete skill protocol " + forbidden)
readme_text = readme.read_text(encoding="utf-8")
for marker in (
    "## 设计思想", "简洁（Concise）", "严谨（Rigorous）", "准确（Accurate）",
    "progressive disclosure", "fail-closed", "current repository bytes",
    "空适用 authority 集合不得使唯一已解析 tracker 降级为 candidate",
    "tracker discovery 必须包含 ignored paths",
    "ordinary implementation/testing/review/execution 请求必须立即退出本 skill 并继续适当的非 generation workflow",
    "High-risk 五字段必须位于 trace header 前",
    "只读 generation 不得降级未来 executor 的显式权限",
    "第二次漂移必须在读取 handoff reference 或运行 fingerprint helper 前终止",
    "第二次漂移 blocker 必须保留恰好一次重算",
):
    if marker not in readme_text: fail("README design philosophy " + marker)
for marker in ("## 复杂度分档", "## 输出合同", "## 评测与校验", "## 版本影响", "Generation is read-only", "post-capture host/evaluator", "首次有效动作事件序号", "RELEASE BLOCKED", "Gate state machine", "Selection basis", "Current executable unit", "Expected transition", "Observed receipt"):
    if marker not in readme_text: fail("README marker " + marker)
for forbidden in ("ordinary-audit-projection-v1", "first-delivery-only", "exact replay", "immutable artifact contract"):
    if forbidden in readme_text: fail("obsolete README protocol " + forbidden)
if "8,192 bytes" in readme_text or "每个非字面量字段最多 8 个词" in readme_text: fail("stale README Standard budget")
if "Standard 9,216-byte body" not in readme_text: fail("README Standard budget authority")
spec_text = spec.read_text(encoding="utf-8")
for marker in (
    "Plan Convergence Output Design v2", "Design Philosophy", "Concise", "Rigorous", "Accurate",
    "Generator Side-Effect Boundary", "Snapshot Consistency", "post-capture", "Future Execution Contract",
    "No hidden, recursive, or unrelated reference graph",
    "An empty applicable authority set never invalidates or demotes a uniquely resolved governing tracker",
    "Tracker discovery includes ignored paths",
    "Implementation, testing, review, and execution requests stop this skill and continue the appropriate non-generation workflow",
    "High-risk fields precede the trace header",
    "Read-only generation never demotes future-executor permission",
    "Snapshot stability is a precondition to conditional disclosure",
    "A second-drift blocker states the fingerprint identity, exactly one recomputation, the second drift, and the blocked result",
):
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
  raise Failure, "root entries" unless Dir.children(root).sort == ["SKILL.md", "agents", "references", "scripts"]
  raise Failure, "agents entries" unless Dir.children(File.join(root, "agents")) == ["openai.yaml"]
  raise Failure, "references entries" unless Dir.children(File.join(root, "references")) == ["handoff-contract.md"]
  raise Failure, "scripts entries" unless Dir.children(File.join(root, "scripts")).sort == ["assemble_handoff.py", "status_fingerprint.py"]
  owned_regular(File.join(root, "SKILL.md"), "SKILL.md")
  owned_regular(File.join(root, "agents", "openai.yaml"), "openai.yaml")
  owned_regular(File.join(root, "references", "handoff-contract.md"), "handoff-contract.md")
  owned_regular(File.join(root, "scripts", "assemble_handoff.py"), "assemble_handoff.py")
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
    "$repo_root/skill/scripts/assemble_handoff.py" \
    "$repo_root/skill/scripts/status_fingerprint.py" \
    "$repo_root/tests/check-python-sources.py" "$repo_root/tests/forward_eval_evidence.py" \
    "$repo_root/tests/status_fingerprint.py" "$repo_root/tests/execution_contract.py" \
    "$repo_root/tests/tool_access_evidence.py" \
    "$repo_root/tests/product_forward_evidence.py" "$repo_root/tests/published_result_validator.py" \
    "$repo_root/tests/validate-published-results.py" \
    "$repo_root/tests/publish-forward-eval-results.py" "$repo_root/tests/test-forward-eval-evidence.py" \
    "$repo_root/tests/test-forward-eval-publisher-guards.py" \
    "$repo_root/tests/test-forward-eval-publisher.py" \
    "$repo_root/tests/publish-product-forward-results.py" \
    "$repo_root/tests/test-product-forward-publisher.py" \
    "$repo_root/tests/test-status-fingerprint.py" "$repo_root/tests/test-execution-contract.py" \
    "$repo_root/tests/test-handoff-assembler.py" \
    "$repo_root/tests/test-tool-access-evidence.py" \
    "$repo_root/tests/test-published-result-validator.py" \
    "$repo_root/tests/check-impact-classifier.py" \
    "$repo_root/tests/test-python-source-checker.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$repo_root/tests/test-python-source-checker.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$repo_root/tests/check-impact-classifier.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$repo_root/tests/test-tool-access-evidence.py"
for eval_json in "$repo_root"/evals/*.json; do python3 -m json.tool "$eval_json" >/dev/null; done

python3 - "$repo_root" <<'PY'
import json, re, sys
from pathlib import Path
root = Path(sys.argv[1])
cases = json.loads((root / "evals/cases.json").read_text(encoding="utf-8"))
expected = {"chinese-mixed-state-first-delivery", "english-localization", "complete-plan", "insufficient-information", "generic-blocker", "light-documentation", "high-risk-public-consumer", "correct-prerequisite-blocker", "migration-permission-release-blocker", "tracker-none-projection", "tracker-injection", "projected-field-injection", "unsafe-gate-command", "no-local-authority", "ordinary-implementation", "tracker-path-escape", "concurrency-conflict", "snapshot-double-drift", "plugin-prerequisites", "git-permission-split", "fence-safety", "product-forward-closure"}
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
PYTHONDONTWRITEBYTECODE=1 python3 "$repo_root/tests/test-handoff-assembler.py"
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
