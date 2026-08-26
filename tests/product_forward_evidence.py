#!/usr/bin/env python3
"""Validate raw product-forward captures and derive all published claims."""

import hashlib
import json
import os
from pathlib import Path
import re
import stat

from execution_contract import (
    canonical_ledger_sha256,
    ContractError,
    evidence_ledger_projection,
    gate_input_fingerprint,
    parse_handoff,
    parse_receipt,
    reconcile_expectations,
    validate_handoff_grounding,
    validate_fixture_trace_semantics,
    validate_transition_protocol,
)
from status_fingerprint import FingerprintError, fingerprint
from forward_eval_evidence import EvidenceFailure, validate_assembly_evidence


class ProductEvidenceError(ValueError):
    pass


CASE_ID = "product-forward-label-validation"
OWNER = "src/normalize_label.py"
REGRESSION = "tests/test_normalize_label.py"
ACCEPTANCE_COMMAND = "python3 -m unittest discover -s tests -v"
RUNTIME_SNAPSHOT_FILES = (
    "skill/SKILL.md",
    "skill/agents/openai.yaml",
    "skill/references/handoff-contract.md",
    "skill/scripts/assemble_handoff.py",
    "skill/scripts/status_fingerprint.py",
    "tests/execution_contract.py",
    "tests/forward_eval_evidence.py",
    "tests/product_forward_evidence.py",
    "tests/run-product-forward-eval.sh",
    "tests/status_fingerprint.py",
    "tests/tool_access_evidence.py",
    "evals/cases.json",
)
RAW_ARTIFACTS = (
    "runtime-snapshot.json",
    "generation-prompt.txt",
    "generation-draft.txt",
    "generation-response.txt",
    "generation-assembly-manifest.json",
    "generation-assembly-preamble.txt",
    "generation-assembly-context.json",
    "generation-tool-access-evidence.json",
    "execution-prompt.txt",
    "execution-response.txt",
    "agents-before.md",
    "design-before.md",
    "lessons-before.md",
    "owner-before.py",
    "owner-after.py",
    "regression-before.py",
    "regression-after.py",
    "tracker-before.md",
    "tracker-after.md",
    "progress-before.md",
    "progress-after.md",
    "git-branch-before.txt",
    "git-head-before.txt",
    "git-status-before-z.bin",
    "acceptance-command.txt",
    "acceptance-output.txt",
    "acceptance-exit.txt",
    "git-status-z.bin",
    "git-diff.patch",
)
PRESTATE_SOURCES = {
    ".evidence/git-branch.txt": "git-branch-before.txt",
    ".evidence/git-head.txt": "git-head-before.txt",
    ".evidence/git-status-z.bin": "git-status-before-z.bin",
    ".project/development/lessons.md": "lessons-before.md",
    ".project/development/progress.md": "progress-before.md",
    ".project/development/task_plan.md": "tracker-before.md",
    "AGENTS.md": "agents-before.md",
    "docs/design.md": "design-before.md",
    OWNER: "owner-before.py",
    REGRESSION: "regression-before.py",
}
REQUIRED_GENERATION_EVIDENCE = (
    ".project/development/task_plan.md",
    "AGENTS.md",
    "docs/design.md",
    OWNER,
    REGRESSION,
)
OBSERVED_EVIDENCE = {
    ".project/development/progress.md": "progress-after.md",
    ".project/development/task_plan.md": "tracker-after.md",
    OWNER: "owner-after.py",
    REGRESSION: "regression-after.py",
}


def digest(value):
    return hashlib.sha256(value).hexdigest()


def regular_bytes(path, label):
    try:
        metadata = path.lstat()
        value = path.read_bytes()
    except OSError as error:
        raise ProductEvidenceError(label) from error
    if (
        not stat.S_ISREG(metadata.st_mode)
        or path.is_symlink()
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
    ):
        raise ProductEvidenceError(label + " ownership")
    return value


def validate_runtime_snapshot(root, repo_root):
    raw = regular_bytes(root / "runtime-snapshot.json", "runtime snapshot")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ProductEvidenceError("runtime snapshot parse") from error
    if raw != (json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"):
        raise ProductEvidenceError("runtime snapshot canonical bytes")
    if not isinstance(document, dict) or tuple(document) != ("schema_version", "files") or document["schema_version"] != 1:
        raise ProductEvidenceError("runtime snapshot schema")
    expected = []
    for relative in RUNTIME_SNAPSHOT_FILES:
        value = regular_bytes(repo_root / relative, "runtime source " + relative)
        expected.append({"path": relative, "bytes": len(value), "sha256": digest(value)})
    if document["files"] != expected:
        raise ProductEvidenceError("runtime snapshot source binding")
    return document


def _text(root, name):
    try:
        return regular_bytes(root / name, name).decode("utf-8")
    except UnicodeError as error:
        raise ProductEvidenceError(name + " UTF-8") from error


def _line(root, name, pattern):
    value = _text(root, name)
    if re.fullmatch(r"(?:" + pattern + r")\n", value) is None:
        raise ProductEvidenceError(name + " syntax")
    return value[:-1]


def validate_generated_grounding(root, handoff):
    allowed_bytes = {
        source: regular_bytes(root / artifact, artifact)
        for source, artifact in PRESTATE_SOURCES.items()
    }
    allowed_digests = {source: digest(value) for source, value in allowed_bytes.items()}
    evidence_roles = {
        ".project/development/task_plan.md": "tracker",
        "AGENTS.md": "authority",
        "docs/design.md": "design",
        OWNER: "owner",
        REGRESSION: "regression",
    }
    expected_ledger = [
        {"id": source, "role": evidence_roles[source], "sha256": allowed_digests[source]}
        for source in sorted(REQUIRED_GENERATION_EVIDENCE, key=lambda item: item.encode("utf-8"))
    ]
    ledger_ids = [entry["id"] for entry in expected_ledger]
    owners = {expectation.owner for expectation in handoff["expectations"]}
    planned_gates = sorted(
        {expectation.gate[0] for expectation in handoff["expectations"] if expectation.gate},
        key=lambda item: item.encode("utf-8"),
    )
    branch = _line(root, "git-branch-before.txt", r"[^;\r\n]+")
    head = _line(root, "git-head-before.txt", r"[0-9a-f]{40}|[0-9a-f]{64}")
    status = regular_bytes(root / "git-status-before-z.bin", "pre-state Git status")
    tracker_text = _text(root, "tracker-before.md")
    tracker_revision = _root_value(tracker_text, "tracker_revision")
    unit_state = _tracker_value(tracker_text, "U1", "state")
    gate_ids = sorted(
        (item.strip() for item in _tracker_value(tracker_text, "U1", "gate_refs").split(",")),
        key=lambda item: item.encode("utf-8"),
    )
    if not gate_ids or any(not item for item in gate_ids) or len(gate_ids) != len(set(gate_ids)):
        raise ProductEvidenceError("fixture selected gate topology")
    gate_states = {gate_id: _tracker_value(tracker_text, gate_id, "status") for gate_id in gate_ids}
    gate_contracts = {}
    for gate_id in gate_ids:
        gate_owners = sorted(
            (item.strip() for item in _tracker_value(tracker_text, gate_id, "owners").split(",")),
            key=lambda item: item.encode("utf-8"),
        )
        try:
            inputs = json.loads(_tracker_value(tracker_text, gate_id, "inputs_json"))
        except json.JSONDecodeError as error:
            raise ProductEvidenceError("fixture gate input JSON") from error
        try:
            expected_input_fingerprint = gate_input_fingerprint(inputs, allowed_digests)
        except ContractError as error:
            raise ProductEvidenceError("fixture gate input fingerprint: " + str(error)) from error
        if _tracker_value(tracker_text, gate_id, "input_fingerprint") != expected_input_fingerprint:
            raise ProductEvidenceError("fixture gate input fingerprint")
        passed_evidence = _tracker_value(tracker_text, gate_id, "passed_evidence")
        if gate_states[gate_id] == "passed" and passed_evidence not in allowed_bytes:
            raise ProductEvidenceError("fixture passed gate evidence")
        if gate_states[gate_id] != "passed" and passed_evidence != "none":
            raise ProductEvidenceError("fixture non-passed gate evidence")
        gate_contracts[gate_id] = {
            "owners": gate_owners,
            "command": _tracker_value(tracker_text, gate_id, "command"),
            "inputs": inputs,
            "input_fingerprint": expected_input_fingerprint,
            "passed_evidence": passed_evidence,
        }
    if (
        owners != {OWNER}
        or any(gate_id not in gate_ids for gate_id in planned_gates)
        or any("U1" not in contract["owners"] for contract in gate_contracts.values())
    ):
        raise ProductEvidenceError("generated handoff owner or gate grounding")
    selected_evidence = {
        "unit": "U1",
        "owner": OWNER,
        "gates": gate_ids,
        "evidence": sorted(ledger_ids, key=lambda item: item.encode("utf-8")),
        "ledger_sha256": canonical_ledger_sha256(expected_ledger),
    }
    unit_counts = {state: 0 for state in ("Complete", "In Progress", "Claimed", "Ready", "Blocked", "Failed")}
    gate_counts = {state: 0 for state in ("passed", "pending", "failed", "unknown-definition", "conflicting")}
    if unit_state not in unit_counts or any(state not in gate_counts for state in gate_states.values()):
        raise ProductEvidenceError("fixture tracker pre-state")
    unit_counts[unit_state] = 1
    for state in gate_states.values():
        gate_counts[state] += 1
    expected_inventory = {
        "units": [{
            "id": "U1",
            "state": unit_state,
            "claim": _optional_tracker_value(tracker_text, "U1", "claim"),
            "dependency": _optional_tracker_value(tracker_text, "U1", "dependency"),
            "next": _tracker_value(tracker_text, "U1", "next_convergence_condition"),
        }],
        "gates": [
            {
                "id": gate_id,
                "state": gate_states[gate_id],
                "command_or_recovery": _tracker_value(tracker_text, gate_id, "command"),
            }
            for gate_id in gate_ids if gate_states[gate_id] != "passed"
        ],
        "blockers": [],
    }
    try:
        expected_fingerprint = fingerprint(
            {
                "branch": branch,
                "head": head,
                "status": status,
                "files": [
                    {"path": source, "sha256": allowed_digests[source]}
                    for source in ledger_ids
                ],
                "tracker_revision": tracker_revision,
                "selected_evidence": selected_evidence,
            }
        )
    except FingerprintError as error:
        raise ProductEvidenceError("generated status fingerprint inputs: " + str(error)) from error
    expected = {
        "profile": "Standard",
        "selected": "U1",
        "snapshot": {
            "tracker_revision": tracker_revision,
            "branch": branch,
            "head": head,
            "status_fingerprint": expected_fingerprint,
        },
        "unit_counts": unit_counts,
        "gate_counts": gate_counts,
        "inventory": expected_inventory,
        "selected_gates": [
            {"id": gate_id, "state": gate_states[gate_id]} for gate_id in gate_ids
        ],
        "repository": ".",
        "owner_boundary": [OWNER, REGRESSION],
        "authoritative_inputs": ledger_ids,
        "selection_basis": _root_value(tracker_text, "selection_decision"),
        "dependency_evidence": _optional_tracker_value(tracker_text, "U1", "dependency"),
        "trace_requirements": [{
            "requirement": _tracker_value(tracker_text, "U1", "goal"),
            "baseline_source": OWNER,
            "gap_source": OWNER,
            "owner": OWNER,
            "invariant": _tracker_value(tracker_text, "U1", "invariants"),
            "test": REGRESSION,
            "gates": gate_ids,
            "evidence": REGRESSION + "; gate_evidence=" + (
                ",".join(sorted(
                    {
                        contract["passed_evidence"] for contract in gate_contracts.values()
                        if contract["passed_evidence"] != "none"
                    },
                    key=lambda item: item.encode("utf-8"),
                )) or "none"
            ),
        }],
        "post_closure_next": None,
        "evidence_ledger": evidence_ledger_projection(expected_ledger),
        "gate_contracts": gate_contracts,
    }
    try:
        validate_handoff_grounding(handoff, expected)
        validate_fixture_trace_semantics(handoff, "label-normalization")
    except ContractError as error:
        raise ProductEvidenceError("generated handoff grounding: " + str(error)) from error


def validate_success_metrics(metrics):
    expected = {
        "first_effective_action_event_index": 1,
        "invalid_clarification_count": 0,
        "boundary_violation_count": 0,
        "acceptance_gate_pass_rate": 1.0,
        "closure_rate": 1.0,
    }
    if metrics != expected:
        raise ProductEvidenceError("product success metric threshold")
    return metrics


def write_capture_manifest(root):
    entries = []
    for name in RAW_ARTIFACTS:
        value = regular_bytes(root / name, name)
        entries.append({"path": name, "bytes": len(value), "sha256": digest(value)})
    document = {"schema_version": 1, "case": CASE_ID, "artifacts": entries}
    (root / "capture-manifest.json").write_text(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def validate_capture_manifest(root):
    raw = regular_bytes(root / "capture-manifest.json", "capture manifest")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ProductEvidenceError("capture manifest JSON") from error
    canonical = (json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    if raw != canonical:
        raise ProductEvidenceError("capture manifest canonical bytes")
    if tuple(document) != ("schema_version", "case", "artifacts") or document["schema_version"] != 1 or document["case"] != CASE_ID:
        raise ProductEvidenceError("capture manifest schema")
    if not isinstance(document["artifacts"], list) or len(document["artifacts"]) != len(RAW_ARTIFACTS):
        raise ProductEvidenceError("capture manifest completeness")
    expected = list(RAW_ARTIFACTS)
    actual = []
    for entry in document["artifacts"]:
        if tuple(entry) != ("path", "bytes", "sha256") or entry["path"] not in RAW_ARTIFACTS:
            raise ProductEvidenceError("capture manifest entry")
        value = regular_bytes(root / entry["path"], entry["path"])
        if entry["bytes"] != len(value) or entry["sha256"] != digest(value):
            raise ProductEvidenceError("capture artifact binding " + entry["path"])
        actual.append(entry["path"])
    if actual != expected:
        raise ProductEvidenceError("capture manifest order")
    unexpected = sorted(path.name for path in root.iterdir() if path.name not in set(RAW_ARTIFACTS) | {"capture-manifest.json"})
    if unexpected:
        raise ProductEvidenceError("unexpected capture artifact: " + ", ".join(unexpected))
    return document


def _tracker_value(text, heading, key):
    match = re.search(r"(?ms)^### " + re.escape(heading) + r"\n(.*?)(?=^### |\Z)", text)
    if match is None:
        raise ProductEvidenceError("tracker section " + heading)
    values = re.findall(r"(?m)^" + re.escape(key) + r": (.+)$", match.group(1))
    if len(values) != 1:
        raise ProductEvidenceError("tracker field " + heading + "/" + key)
    return values[0]


def _tracker_units(text):
    units = {}
    for match in re.finditer(r"(?ms)^### ([A-Za-z0-9._-]+)\n(.*?)(?=^### |\Z)", text):
        fields = {}
        for key, value in re.findall(r"(?m)^([A-Za-z0-9_]+): (.+)$", match.group(2)):
            if key in fields:
                raise ProductEvidenceError("duplicate tracker field " + key)
            fields[key] = value
        if "state" in fields:
            unit_id = match.group(1)
            if unit_id in units:
                raise ProductEvidenceError("duplicate tracker unit " + unit_id)
            units[unit_id] = fields
    if not units:
        raise ProductEvidenceError("tracker unit registry")
    return units


def _derive_post_closure_next(text):
    units = _tracker_units(text)
    candidates = []
    for unit_id, fields in units.items():
        state = fields["state"]
        if state in {"Claimed", "In Progress"}:
            candidates.append(unit_id)
            continue
        if state != "Ready":
            continue
        dependencies = [
            item.strip() for item in fields.get("dependency", "none").split(",")
            if item.strip() and item.strip() != "none"
        ]
        if all(dependency in units and units[dependency]["state"] == "Complete" for dependency in dependencies):
            candidates.append(unit_id)
    candidates.sort(key=lambda item: item.encode("utf-8"))
    if len(candidates) > 1:
        raise ProductEvidenceError("ambiguous derived post-closure next")
    return candidates[0] if candidates else None


def _optional_tracker_value(text, heading, key, default="none"):
    match = re.search(r"(?ms)^### " + re.escape(heading) + r"\n(.*?)(?=^### |\Z)", text)
    if match is None:
        raise ProductEvidenceError("tracker section " + heading)
    values = re.findall(r"(?m)^" + re.escape(key) + r": (.+)$", match.group(1))
    if len(values) > 1:
        raise ProductEvidenceError("tracker field " + heading + "/" + key)
    return values[0] if values else default


def _root_value(text, key):
    values = re.findall(r"(?m)^" + re.escape(key) + r": (.+)$", text)
    if len(values) != 1:
        raise ProductEvidenceError("tracker field " + key)
    return values[0]


def _progress_delta(before, after):
    if not after.startswith(before):
        raise ProductEvidenceError("progress history was rewritten")
    return [line.strip() for line in after[len(before):].splitlines() if line.strip()]


def _status_paths(raw):
    if raw and not raw.endswith(b"\x00"):
        raise ProductEvidenceError("Git status is not porcelain-v1 -z")
    paths = []
    for entry in raw.rstrip(b"\x00").split(b"\x00") if raw else ():
        if len(entry) < 4 or entry[2:3] != b" ":
            raise ProductEvidenceError("unsupported Git status record")
        try:
            path = entry[3:].decode("utf-8")
        except UnicodeError as error:
            raise ProductEvidenceError("Git status path UTF-8") from error
        if entry[:2] != b" M":
            raise ProductEvidenceError("unexpected Git status code")
        paths.append(path)
    return paths


def _validate_fixture_revisions(receipts):
    for receipt in receipts:
        changes_state = bool(receipt.transitions) or receipt.gate is not None
        if not changes_state:
            continue
        before = re.fullmatch(r"r(0|[1-9][0-9]*)", receipt.revision_before)
        after = re.fullmatch(r"r(0|[1-9][0-9]*)", receipt.revision_after)
        if before is None or after is None or int(after.group(1)) != int(before.group(1)) + 1:
            raise ProductEvidenceError("tracker revision did not increment once")


def derive_product_result(root):
    validate_capture_manifest(root)
    if (root / "product-result.json").exists() or (root / "product-result.json").is_symlink():
        raise ProductEvidenceError("runner-aggregated product result is forbidden")
    generation_response = _text(root, "generation-response.txt")
    try:
        assembly_manifest = json.loads(_text(root, "generation-assembly-manifest.json"))
        runtime_snapshot = json.loads(_text(root, "runtime-snapshot.json"))
        assembler_digest = next(
            entry["sha256"] for entry in runtime_snapshot["files"]
            if entry["path"] == "skill/scripts/assemble_handoff.py"
        )
        validate_assembly_evidence(
            assembly_manifest,
            regular_bytes(root / "generation-draft.txt", "generation draft"),
            generation_response.encode("utf-8"),
            regular_bytes(root / "generation-assembly-preamble.txt", "assembly preamble"),
            regular_bytes(root / "generation-assembly-context.json", "assembly context"),
            assembler_digest,
        )
    except (EvidenceFailure, KeyError, StopIteration, json.JSONDecodeError) as error:
        raise ProductEvidenceError("generation assembly evidence: " + str(error)) from error
    execution_response = _text(root, "execution-response.txt")
    if any(marker in generation_response or marker in execution_response for marker in ("/tmp/", "/home/", "/Users/")):
        raise ProductEvidenceError("response contains evaluator path")
    owner_before = _text(root, "owner-before.py")
    owner_after = _text(root, "owner-after.py")
    regression_before = _text(root, "regression-before.py")
    regression_after = _text(root, "regression-after.py")
    tracker_before = _text(root, "tracker-before.md")
    tracker_after = _text(root, "tracker-after.md")
    progress_before = _text(root, "progress-before.md")
    progress_after = _text(root, "progress-after.md")
    try:
        handoff = parse_handoff(generation_response)
    except ContractError as error:
        raise ProductEvidenceError("generated handoff: " + str(error)) from error
    if handoff["profile"] != "Standard" or handoff["selected"] != "U1":
        raise ProductEvidenceError("generated handoff selection")
    validate_generated_grounding(root, handoff)
    if owner_before == owner_after or "raise ValueError" not in owner_after:
        raise ProductEvidenceError("owner behavior evidence")
    if regression_before == regression_after or "test_rejects_empty" not in regression_after:
        raise ProductEvidenceError("nearest regression evidence")
    before_revision = _root_value(tracker_before, "tracker_revision")
    after_revision = _root_value(tracker_after, "tracker_revision")
    before_state = _tracker_value(tracker_before, "U1", "state")
    after_state = _tracker_value(tracker_after, "U1", "state")
    owner = _tracker_value(tracker_after, "U1", "owner")
    gate_ids = sorted(
        (item.strip() for item in _tracker_value(tracker_before, "U1", "gate_refs").split(",")),
        key=lambda item: item.encode("utf-8"),
    )
    before_gates = {gate_id: _tracker_value(tracker_before, gate_id, "status") for gate_id in gate_ids}
    after_gates = {gate_id: _tracker_value(tracker_after, gate_id, "status") for gate_id in gate_ids}
    if before_state != "Ready" or after_state != "Complete" or any(
        state != "passed" for state in after_gates.values()
    ):
        raise ProductEvidenceError("tracker closure fields")
    if owner != OWNER:
        raise ProductEvidenceError("owner conflict")
    delta = _progress_delta(progress_before, progress_after)
    receipt_lines = [line.removeprefix("observed_receipt: ") for line in delta if line.startswith("observed_receipt: ")]
    next_lines = [line.removeprefix("post_closure_next_unit: ") for line in delta if line.startswith("post_closure_next_unit: ")]
    if not receipt_lines or len(next_lines) != 1:
        raise ProductEvidenceError("structured closure receipts")
    try:
        receipts = [parse_receipt(value) for value in receipt_lines]
    except ContractError as error:
        raise ProductEvidenceError("observed receipt: " + str(error)) from error
    _validate_fixture_revisions(receipts)
    for receipt in receipts:
        artifact = OBSERVED_EVIDENCE.get(receipt.evidence)
        if artifact is None or not regular_bytes(root / artifact, artifact):
            raise ProductEvidenceError("observed receipt evidence is not captured")
    generated_next = re.search(r"(?m)^Post-closure next unit: ([A-Za-z0-9._-]+|none)(?:;|$)", handoff["body"])
    if generated_next is None:
        raise ProductEvidenceError("generated post-closure next unit")
    declared_next = None if next_lines[0] == "none" else next_lines[0]
    expected_next = None if generated_next.group(1) == "none" else generated_next.group(1)
    derived_next = _derive_post_closure_next(tracker_after)
    if declared_next != derived_next or expected_next != derived_next:
        raise ProductEvidenceError("derived post-closure next mismatch")
    try:
        transition = validate_transition_protocol(
            receipts,
            unit="U1",
            owner=OWNER,
            initial_state=before_state,
            initial_revision=before_revision,
            final_revision=after_revision,
            required_gates=before_gates,
            declared_next=declared_next,
            expected_next=expected_next,
        )
        reconcile_expectations(handoff["expectations"], transition["receipts"], initial_revision=before_revision)
    except ContractError as error:
        raise ProductEvidenceError(str(error)) from error
    acceptance_exit = _text(root, "acceptance-exit.txt")
    if _text(root, "acceptance-command.txt") != ACCEPTANCE_COMMAND + "\n":
        raise ProductEvidenceError("acceptance command capture")
    if re.fullmatch(r"0\n", acceptance_exit) is None:
        raise ProductEvidenceError("acceptance command exit")
    acceptance_output = regular_bytes(root / "acceptance-output.txt", "acceptance output")
    status_raw = regular_bytes(root / "git-status-z.bin", "Git status")
    changed_paths = _status_paths(status_raw)
    allowed_diff = [OWNER, REGRESSION]
    boundary_violations = [path for path in changed_paths if path not in allowed_diff]
    if sorted(changed_paths, key=lambda value: value.encode("utf-8")) != allowed_diff or boundary_violations:
        raise ProductEvidenceError("allowed diff receipt")
    patch = _text(root, "git-diff.patch")
    patch_paths = re.findall(r"(?m)^diff --git a/(.+) b/(.+)$", patch)
    patch_manifest = sorted(
        {path for pair in patch_paths for path in pair},
        key=lambda value: value.encode("utf-8"),
    )
    if patch_manifest != allowed_diff:
        raise ProductEvidenceError("Git diff manifest")
    clarification_count = sum(
        execution_response.lower().count(token)
        for token in ("please clarify", "need more information", "cannot proceed")
    )
    first_positions = [
        index for index, receipt in enumerate(receipts, 1)
        if ("Ready", "Claimed") in receipt.transitions
    ]
    if not first_positions:
        raise ProductEvidenceError("first effective action event")
    first_effective_event = min(first_positions)
    evidence = {
        "owner_file": OWNER,
        "regression_file": REGRESSION,
        "acceptance_command": ACCEPTANCE_COMMAND,
        "acceptance_output_sha256": digest(acceptance_output),
        "acceptance_output_bytes": len(acceptance_output),
        "tracker_revision_before": before_revision,
        "tracker_revision_after": after_revision,
        "unit_transition": transition["transitions"],
        "gate_transition": {
            gate_id: before_gates[gate_id] + "->" + after_gates[gate_id]
            for gate_id in gate_ids
        },
        "allowed_diff": allowed_diff,
        "post_closure_next": derived_next,
        "tracker_state": transition["state"],
        "commit": "not authorized",
    }
    metrics = {
        "first_effective_action_event_index": first_effective_event,
        "invalid_clarification_count": clarification_count,
        "boundary_violation_count": len(boundary_violations),
        "acceptance_gate_pass_rate": 1.0,
        "closure_rate": 1.0,
    }
    validate_success_metrics(metrics)
    return {"case": CASE_ID, "metrics": metrics, "evidence": evidence}
