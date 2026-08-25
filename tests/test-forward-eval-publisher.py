#!/usr/bin/env python3
"""End-to-end fresh aggregate publication and rollback regression."""

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from execution_contract import (
    canonical_ledger_sha256,
    evidence_ledger_projection,
    gate_input_fingerprint,
)
from forward_eval_evidence import derive_side_effect_evidence
from status_fingerprint import fingerprint


CASE_ID = "chinese-mixed-state-first-delivery"


def fail(message):
    raise SystemExit("FAIL: forward eval publisher end-to-end self-test: " + message)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def write_canonical(path, value):
    path.write_text(canonical(value) + "\n", encoding="utf-8")


def tracker_text():
    input_paths = ["src/normalize-label.js", "tests/normalize-label.test.js"]
    input_digests = {
        "src/normalize-label.js": digest(b"export function normalizeLabel(value) { return value.trim(); }\n"),
        "tests/normalize-label.test.js": digest(b"// focused normalization tests\n"),
    }
    input_fingerprint = gate_input_fingerprint(input_paths, input_digests)
    return (
        "# Development tracker\n\n"
        "tracker_revision: 17\n\n"
        "## Unit registry\n\n"
        "### U1\n\nstate: Complete\nnext_convergence_condition: converged\n\n"
        "### U2\n\nstate: In Progress\nclaim: worker-a\nselected: true\n"
        "goal: Reject blank normalized labels at the owner boundary\n"
        "owner: src/normalize-label.js\nauthoritative_design: docs/design.md\n"
        "nearest_test: tests/normalize-label.test.js\ndependency: none\n"
        "invariants: Preserve the public contract.\n"
        "next_convergence_condition: G2 passes with focused evidence\ngate_refs: G1, G2\n\n"
        "### U3\n\nstate: Ready\ndependency: U2\n"
        "next_convergence_condition: U2 is Complete, then claim U3\ngate_refs: G1\n\n"
        "### U4\n\nstate: Blocked\ndependency: none\nowner: schema-owner\n"
        "next_convergence_condition: schema approval and G3 status\n"
        "blocker_id: B1\nblocker_owner: schema-owner\n"
        "blocker: Missing schema approval.\n"
        "recovery_condition: The schema owner records approval and G3.\n\n"
        "gate_refs: G3\n\n"
        "## Required gate registry\n\n"
        "### G1\n\nrequired: true\nstatus: passed\nowners: U2, U3\n"
        "command: node --test tests/normalize-label.test.js\n"
        "inputs_json: " + canonical(input_paths) + "\n"
        "input_fingerprint: " + input_fingerprint + "\n"
        "passed_evidence: .project/development/evidence/G1.pass\n\n"
        "### G2\n\nrequired: true\nstatus: pending\nowners: U2\n"
        "command: node --test tests/normalize-label.test.js\n\n"
        "inputs_json: " + canonical(input_paths) + "\n"
        "input_fingerprint: " + input_fingerprint + "\npassed_evidence: none\n\n"
        "recovery_condition: Implement U2, run the exact focused Gate, and record fresh passing evidence.\n\n"
        "### G3\n\nrequired: true\nstatus: unknown-definition\nowners: U4\n"
        "recovery_condition: The schema owner records approval and G3.\n\n"
        "## Decisions and blockers\n\n"
        "selection_decision: U2 is the sole claimed In Progress critical-path unit.\n"
    )


def step(number, operation, action, command, boundaries, transition, receipt="none"):
    owner = "src/normalize-label.js"
    expected_exit = "0" if operation in {"observe", "test"} else "n/a"
    return "\n".join((
        "Step: " + str(number),
        "Action: " + operation + ": " + action,
        "Command: " + command,
        "Files/boundary: " + canonical(boundaries),
        "Acceptance Gate: G2 focused acceptance; exit=" + expected_exit,
        "Expected transition: " + transition,
        "Evidence required: receipt=" + receipt + "; artifacts=fresh bounded evidence",
        "Failure/recovery: stop=identity, command, or evidence failure; recovery=record new evidence and correct the bounded cause",
    ))


def response_and_artifacts():
    owner = "src/normalize-label.js"
    sources = {
        ".project/development/task_plan.md": tracker_text().encode("utf-8"),
        ".project/development/evidence/G1.pass": b"G1 passed at tracker revision 17 for the recorded input fingerprint.\n",
        "AGENTS.md": b"Implementation, tests, and tracker updates are authorized; Git publication is not.\n",
        "docs/design.md": b"Reject normalized empty labels while preserving the public export.\n",
        "src/normalize-label.js": b"export function normalizeLabel(value) { return value.trim(); }\n",
        "tests/normalize-label.test.js": b"// focused normalization tests\n",
    }
    roles = {
        ".project/development/task_plan.md": "tracker",
        ".project/development/evidence/G1.pass": "gate-evidence",
        "AGENTS.md": "authority",
        "docs/design.md": "design",
        "src/normalize-label.js": "owner",
        "tests/normalize-label.test.js": "regression",
    }
    ledger = [
        {"id": path, "role": roles[path], "sha256": digest(sources[path])}
        for path in sorted(sources, key=lambda item: item.encode("utf-8"))
    ]
    inventory = {
        "units": [
            {"id": "U2", "state": "In Progress", "claim": "worker-a", "dependency": "none", "next": "G2 passes with focused evidence"},
            {"id": "U3", "state": "Ready", "claim": "none", "dependency": "U2", "next": "U2 is Complete, then claim U3"},
            {"id": "U4", "state": "Blocked", "claim": "none", "dependency": "none", "next": "schema approval and G3 status"},
        ],
        "gates": [
            {"id": "G2", "state": "pending", "command_or_recovery": "node --test tests/normalize-label.test.js"},
            {"id": "G3", "state": "unknown-definition", "command_or_recovery": "The schema owner records approval and G3."},
        ],
        "blockers": [
            {"id": "B1", "owner": "schema-owner", "detail": "Missing schema approval.", "recovery": "The schema owner records approval and G3."},
        ],
    }
    selected_gates = [{"id": "G1", "state": "passed"}, {"id": "G2", "state": "pending"}]
    selected_evidence = {
        "unit": "U2",
        "owner": owner,
        "gates": ["G1", "G2"],
        "evidence": [entry["id"] for entry in ledger],
        "ledger_sha256": canonical_ledger_sha256(ledger),
    }
    head = "d" * 40
    status = fingerprint({
        "branch": "feature/mixed-plan",
        "head": head,
        "status": b"",
        "files": [{"path": entry["id"], "sha256": entry["sha256"]} for entry in ledger],
        "tracker_revision": "17",
        "selected_evidence": selected_evidence,
    })
    body = (
        "Protocol profile: Standard\nRepository: .\nUnit: U2\n"
        "Capability: repository-native Node tests; fallback=none\n"
        "Authoritative inputs: " + canonical([entry["id"] for entry in ledger]) + "\n"
        'Owner boundary: ["src/normalize-label.js","tests/normalize-label.test.js"]\n'
        "Invariants: Preserve the public contract.\n"
        "Non-goals: schema work, dependencies, commit, version, or publication\n"
        "Requirement -> Baseline -> Root cause/design gap -> Owner change -> Invariant -> Test -> Gate -> Evidence\n"
        "Reject blank normalized labels at the owner boundary -> src/normalize-label.js: returns empty text -> src/normalize-label.js: the documented guard is absent -> src/normalize-label.js: add the guard and update tests/normalize-label.test.js -> Preserve the public contract. -> tests/normalize-label.test.js: positive and negative test -> G1,G2 -> tests/normalize-label.test.js; gate_evidence=.project/development/evidence/G1.pass\n"
        "Permission matrix:\n"
        "Implementation | Tests | Update tracker | Local commit | Change version | Tag | Push/release\n"
        "authorized: user | authorized: user | authorized: AGENTS.md | not authorized: absent | not authorized: absent | not authorized: absent | not authorized: absent\n\n"
        + step(1, "tracker", "invalidate G1 before changing its recorded inputs", "none: authorized structured tracker edit", [".project/development/task_plan.md"], "unit=U2; owner=" + owner + "; transitions=none; from_revision=17; gate=G1:passed->pending", ".project/development/task_plan.md")
        + "\n\n"
        + step(2, "implementation", "apply the owner and focused regression changes", "none: authorized structured edits", [owner, "tests/normalize-label.test.js"], "unit=U2; owner=" + owner + "; transitions=none; from_revision=observed-prior; gate=none")
        + "\n\n"
        + step(3, "test", "run focused positive and negative acceptance", "node --test tests/normalize-label.test.js", [owner, "tests/normalize-label.test.js"], "unit=U2; owner=" + owner + "; transitions=none; from_revision=observed-prior; gate=none")
        + "\n\n"
        + step(4, "tracker", "persist fresh G1 evidence", "none: authorized structured tracker edit", [".project/development/task_plan.md"], "unit=U2; owner=" + owner + "; transitions=none; from_revision=observed-prior; gate=G1:pending->passed", ".project/development/task_plan.md")
        + "\n\n"
        + step(5, "tracker", "persist G2 and U2 closure", "none: authorized structured tracker edit", [".project/development/task_plan.md"], "unit=U2; owner=" + owner + "; transitions=In Progress->Complete; from_revision=observed-prior; gate=G2:pending->passed", ".project/development/task_plan.md")
        + "\n\nClosure condition: owner behavior, regression, G2, diff/status, and output are evidenced\n"
        "Tracker target state: U2 Complete and G1/G2 passed\n"
        "Observed receipt requirements: start 17; executor supplies changed revision and exact boundary evidence\n"
        "Post-closure next unit: U3; dependency U2 becomes Complete\n"
        "Out of scope: schema, unrelated code, commit, version, tag, push, release, deployment, and providers\n"
    )
    response = (
        "开发计划收敛情况：当前主线可执行。\n"
        "Snapshot: tracker_revision=17; branch=feature/mixed-plan; head=" + head + "; status_fingerprint=" + status + "\n"
        "Unit counts: Complete=1; In Progress=1; Claimed=0; Ready=1; Blocked=1; Failed=0\n"
        "Gate counts: passed=1; pending=1; failed=0; unknown-definition=1; conflicting=0\n"
        "Selection basis: U2 is the sole claimed In Progress critical-path unit.\n"
        "Current executable unit: U2; dependency_evidence=none\nSelected unit: U2\n"
        "Selected required gates: " + canonical(selected_gates) + "\n"
        "Evidence reads: used=6; ceiling=12; extension=0; reason=none\n"
        "Evidence ledger: " + canonical(evidence_ledger_projection(ledger))
        + "\nOpen inventory: " + canonical(inventory) + "\n"
        "```text\n" + body + "```\n"
    ).encode("utf-8")
    manifest = {
        "schema_version": 2,
        "case_id": CASE_ID,
        "git": {"branch": "feature/mixed-plan", "head": head, "status_hex": ""},
        "files": [
            {"path": path, "mode": "100644", "bytes": len(sources[path]), "sha256": digest(sources[path])}
            for path in sorted(sources, key=lambda item: item.encode("utf-8"))
        ],
    }
    grounding = {
        "schema_version": 1,
        "case_id": CASE_ID,
        "tracker_path": ".project/development/task_plan.md",
        "tracker_base64": base64.b64encode(sources[".project/development/task_plan.md"]).decode("ascii"),
    }
    return response, manifest, grounding, status


def response_parts(value):
    marker = b"```text\n"
    opening = value.index(marker)
    closing = value.rindex(b"```\n")
    return value[:opening], value[opening + len(marker):closing]


def copy_forward_sources(source, repo):
    for relative in (
        "skill/agents/openai.yaml",
        "tests/run-forward-evals.sh",
        "tests/publish-forward-eval-results.py",
        "tests/forward_eval_evidence.py",
        "tests/published_result_validator.py",
    ):
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)


def write_pending_indexes(repo):
    sys.path.insert(0, str(repo / "tests"))
    try:
        validator = runpy.run_path(str(repo / "tests/published_result_validator.py"))
    finally:
        sys.path.pop(0)
    core = validator["_current_bindings"](repo)
    result = {
        "schema_version": 4,
        "version": "0.0.0",
        "status": "pending-fresh-eval",
        "runtime": ["skill/SKILL.md", "skill/agents/openai.yaml", "skill/scripts/status_fingerprint.py"],
        "bindings": core,
        "cases": [],
        "metrics": None,
        "limitations": ["pending"],
        "release_authorized": False,
    }
    representative = {
        "schema_version": 1,
        "version": "0.0.0",
        "case": CASE_ID,
        "status": "pending-fresh-eval",
        "bindings": validator["representative_bindings"](core),
        "release_authorized": False,
    }
    (repo / "evals/results-v0.0.0.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (repo / "evals/representative-forward-results-v0.0.0.json").write_text(json.dumps(representative, indent=2) + "\n", encoding="utf-8")


def write_snapshot(run_root, repo):
    snapshot = run_root / "snapshot"
    entries = []
    mapping = {
        "skill/SKILL.md": repo / "skill/SKILL.md",
        "skill/scripts/status_fingerprint.py": repo / "skill/scripts/status_fingerprint.py",
        "runner.sh": repo / "tests/run-forward-evals.sh",
        "cases.json": repo / "evals/cases.json",
        "status_fingerprint.py": repo / "tests/status_fingerprint.py",
        "execution_contract.py": repo / "tests/execution_contract.py",
        "forward_eval_evidence.py": repo / "tests/forward_eval_evidence.py",
    }
    for relative, source in mapping.items():
        value = source.read_bytes()
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
        entries.append({"path": relative, "bytes": len(value), "sha256": digest(value)})
    write_canonical(snapshot / "manifest.json", {"schema_version": 1, "files": entries})
    return {path: digest(source.read_bytes()) for path, source in mapping.items()}


def without_passed_gate_invalidation(response):
    text = response.decode("utf-8")
    text = re.sub(r"(?ms)^Step: 1\n.*?(?=\n\nStep: 2\n)", "", text, count=1)
    text = re.sub(r"(?ms)^Step: 4\n.*?(?=\n\nStep: 5\n)", "", text, count=1)
    for before, after in ((2, 1), (3, 2), (5, 3)):
        text = text.replace("Step: " + str(before) + "\n", "Step: " + str(after) + "\n", 1)
    text = text.replace(
        "transitions=none; from_revision=observed-prior; gate=none",
        "transitions=none; from_revision=17; gate=none",
        2,
    )
    text = text.replace(
        "transitions=In Progress->Complete; from_revision=observed-prior; gate=G2:pending->passed",
        "transitions=In Progress->Complete; from_revision=17; gate=G2:pending->passed",
        1,
    )
    return text.encode("utf-8")


def write_case(run_root, source_digests, *, tamper_grounding=False, sensitive_grounding=False, stale_passed_gate=False, tamper_post_state=False):
    response, manifest, grounding, status = response_and_artifacts()
    if stale_passed_gate:
        response = without_passed_gate_invalidation(response)
    case = run_root / "cases" / CASE_ID
    case.mkdir(parents=True)
    (case / "prompt.txt").write_text("Generate the next repository-grounded handoff.\n", encoding="utf-8")
    write_canonical(case / "fixture-manifest.json", manifest)
    post_state = json.loads(json.dumps(manifest))
    if tamper_post_state:
        for entry in post_state["files"]:
            if entry["path"] == "src/normalize-label.js":
                entry["sha256"] = "f" * 64
                break
    write_canonical(case / "post-state-manifest.json", post_state)
    if tamper_grounding:
        grounding = dict(grounding, tracker_base64=base64.b64encode(b"fabricated tracker\n").decode("ascii"))
    if sensitive_grounding:
        grounding = dict(
            grounding,
            tracker_base64=base64.b64encode(b"SECRET-CANARY-NOT-A-CREDENTIAL\n").decode("ascii"),
        )
    write_canonical(case / "grounding-sources.json", grounding)
    (case / "response-1.txt").write_bytes(response)
    summary, body = response_parts(response)
    snapshot_manifest = (run_root / "snapshot/manifest.json").read_bytes()
    tracker_digest = digest(tracker_text().encode("utf-8"))
    generation = {
        "schema_version": 5,
        "case_id": CASE_ID,
        "generation_read_only": True,
        "lock_state": "absent",
        "response_fence_regions": [1],
        "response_sha256": [digest(response)],
        "response_bytes": [len(response)],
        "summary_sha256": [digest(summary)],
        "body_sha256": [digest(body)],
        "snapshot_manifest_sha256": digest(snapshot_manifest),
        "post_state_manifest_sha256": digest((case / "post-state-manifest.json").read_bytes()),
        "grounding_sources_sha256": digest((case / "grounding-sources.json").read_bytes()),
        "tracker_before_sha256": tracker_digest,
        "tracker_after_sha256": tracker_digest,
        "status_fingerprint_sha256": status,
        "snapshot_recomputations": 0,
        "second_drift_blocked": False,
        "post_capture_audit": "host/evaluator responsibility",
    }
    side_effect = derive_side_effect_evidence(CASE_ID, manifest, post_state)
    snapshot_evidence = {
        "schema_version": 1,
        "case_id": CASE_ID,
        "skill_sha256": source_digests["skill/SKILL.md"],
        "runner_sha256": source_digests["runner.sh"],
        "corpus_sha256": source_digests["cases.json"],
        "pre_integrity": True,
        "per_session_integrity": [True],
        "post_integrity": True,
    }
    write_canonical(case / "generation-evidence.json", generation)
    write_canonical(case / "side-effect-evidence.json", side_effect)
    write_canonical(case / "snapshot-evidence.json", snapshot_evidence)
    (case / ".complete").write_text("complete\n", encoding="ascii")


def make_environment(source, root, name, *, tamper_grounding=False, sensitive_grounding=False, stale_passed_gate=False, tamper_post_state=False):
    vectors = runpy.run_path(str(source / "tests/test-product-forward-publisher.py"))
    repo = vectors["make_repo"](source, root, name + "-repo")
    copy_forward_sources(source, repo)
    corpus = {
        "cases": [
            {"id": CASE_ID, "fixture": "mixed tracker", "expected": ["grounded"]},
            {"id": "product-forward-closure", "fixture": "two-session product", "expected": ["closure"]},
        ]
    }
    (repo / "evals/cases.json").write_text(
        json.dumps(corpus, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    capture = vectors["make_capture"](root, name + "-product-capture")
    product = vectors["publish"](repo, capture)
    if product.returncode != 0:
        fail("product precondition rejected: " + product.stderr)
    write_pending_indexes(repo)
    run_root = root / (name + "-run")
    run_root.mkdir(mode=0o700)
    source_digests = write_snapshot(run_root, repo)
    write_case(
        run_root,
        source_digests,
        tamper_grounding=tamper_grounding,
        sensitive_grounding=sensitive_grounding,
        stale_passed_gate=stale_passed_gate,
        tamper_post_state=tamper_post_state,
    )
    return repo, run_root


def publish(source_repo, repo, run_root):
    return subprocess.run(
        (sys.executable, str(repo / "tests/publish-forward-eval-results.py"), str(run_root), str(repo), "0.0.0"),
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
    )


def main():
    source = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix="gci-forward-publisher-", dir="/tmp") as temporary:
        root = Path(temporary)
        repo, run_root = make_environment(source, root, "valid")
        completed = publish(source, repo, run_root)
        if completed.returncode != 0:
            fail("complete fresh publication rejected: " + completed.stderr)
        result = json.loads((repo / "evals/results-v0.0.0.json").read_text(encoding="utf-8"))
        if result.get("status") != "fresh-eval-passed" or result.get("release_authorized") is not True:
            fail("fresh publication result")
        if not (repo / "evals/artifacts/v0.0.0" / CASE_ID / "grounding-sources.json").is_file():
            fail("published grounding artifact")

        tamper_repo, tamper_run = make_environment(source, root, "tamper", tamper_grounding=True)
        before = (tamper_repo / "evals/results-v0.0.0.json").read_bytes()
        rejected = publish(source, tamper_repo, tamper_run)
        if rejected.returncode == 0 or "generic grounding tracker binding" not in rejected.stderr:
            fail("tampered grounding accepted")
        if (tamper_repo / "evals/results-v0.0.0.json").read_bytes() != before:
            fail("failed publication changed pending result")
        if (tamper_repo / "evals/artifacts/v0.0.0").exists():
            fail("failed publication left aggregate artifacts")
        sensitive_repo, sensitive_run = make_environment(
            source, root, "sensitive-grounding", sensitive_grounding=True
        )
        rejected = publish(source, sensitive_repo, sensitive_run)
        if rejected.returncode == 0 or "grounding publication sensitive content" not in rejected.stderr:
            fail("base64-encoded sensitive grounding survived publication")
        stale_repo, stale_run = make_environment(
            source, root, "stale-passed", stale_passed_gate=True
        )
        rejected = publish(source, stale_repo, stale_run)
        if rejected.returncode == 0 or "passed gate was not invalidated" not in rejected.stderr:
            fail("stale passed Gate survived planned input changes")
        post_repo, post_run = make_environment(
            source, root, "tampered-post-state", tamper_post_state=True
        )
        rejected = publish(source, post_repo, post_run)
        if rejected.returncode == 0 or "read-only side-effect evidence" not in rejected.stderr:
            fail("raw post-state mutation survived read-only replay")
    print("PASS: complete fresh aggregate publication replays and rolls back grounding tamper")


if __name__ == "__main__":
    main()
