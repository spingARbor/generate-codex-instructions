#!/usr/bin/env python3
"""Positive and negative vectors for handoff expectations and observed receipts."""

import hashlib
import base64
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from execution_contract import (
    _gate_contract,
    _has_chinese_status,
    _tracker_registry,
    ContractError,
    PROFILES,
    canonical_ledger_sha256,
    evidence_ledger_projection,
    gate_input_fingerprint,
    parse_handoff,
    reconcile_expectations,
    validate_forward_case,
    validate_generic_handoff_grounding,
    validate_handoff_grounding,
    validate_transition_protocol,
)
from status_fingerprint import fingerprint


def fail(message):
    raise SystemExit("FAIL: execution contract self-test: " + message)


def expect_rejected(label, function, *args, **kwargs):
    try:
        function(*args, **kwargs)
    except ContractError:
        return
    fail(label + " accepted")


def validate_grounded_response(case_id, response_text, manifest, sources):
    handoff = parse_handoff(response_text)
    return validate_generic_handoff_grounding(case_id, handoff, manifest, sources)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def inventory():
    return {
        "units": [
            {"id": "U1", "state": "Ready", "claim": "none", "dependency": "none", "next": "G1 passes"}
        ],
        "gates": [
            {"id": "G1", "state": "pending", "command_or_recovery": "python3 -m unittest discover -s tests -v"}
        ],
        "blockers": [],
    }


def evidence_ledger():
    paths = (
        (".project/development/task_plan.md", "tracker"),
        ("AGENTS.md", "authority"),
        ("docs/design.md", "design"),
        ("src/normalize_label.py", "owner"),
        ("tests/test_normalize_label.py", "regression"),
    )
    return [
        {"id": path, "role": role, "sha256": hashlib.sha256(path.encode()).hexdigest()}
        for path, role in paths
    ]


def step(
    number,
    operation,
    action,
    command,
    transition,
    files,
    receipt="none",
    gate="none: step-local gate is not applicable",
):
    expected_exit = "0" if operation in {"observe", "test"} else "n/a"
    return "\n".join(
        (
            "Step: " + str(number),
            "Action: " + operation + ": " + action,
            "Command: " + command,
            "Files/boundary: " + canonical(files),
            "Acceptance Gate: " + gate + "; exit=" + expected_exit,
            "Expected transition: " + transition,
            "Evidence required: receipt=" + receipt + "; artifacts=repository-relative command output",
            "Failure/recovery: stop=command, identity, or evidence failure; recovery=record new evidence and correct the bounded cause",
        )
    )


def response():
    owner = "src/normalize_label.py"
    requirement = "Reject blank normalized labels at the owner boundary"
    selection_basis = "U1 is dependency-free and closes the only tracked goal"
    authoritative_inputs = [entry["id"] for entry in evidence_ledger()]
    body = (
        "Protocol profile: Standard\n"
        "Repository: .\n"
        "Unit: U1\n"
        "Capability: repository-native Python unittest; fallback=none\n"
        "Authoritative inputs: " + canonical(authoritative_inputs) + "\n"
        'Owner boundary: ["src/normalize_label.py","tests/test_normalize_label.py"]\n'
        "Invariants: valid labels trim; non-strings raise TypeError; public path is stable\n"
        "Non-goals: API redesign, unrelated refactor, commit, or publication\n"
        "Requirement -> Baseline -> Root cause/design gap -> Owner change -> Invariant -> Test -> Gate -> Evidence\n"
        + requirement + " -> src/normalize_label.py currently returns an empty string -> the documented guard is absent -> change src/normalize_label.py and tests/test_normalize_label.py -> preserve trim, TypeError, and public path -> tests/test_normalize_label.py positive and negative regression -> G1 -> tests/test_normalize_label.py output\n"
        "Permission matrix:\n"
        "Implementation | Tests | Update tracker | Local commit | Change version | Tag | Push/release\n"
        "authorized: user | authorized: user | authorized: AGENTS.md | not authorized: absent | not authorized: absent | not authorized: absent | not authorized: absent\n\n"
        + step(
            1,
            "observe",
            "recheck repository identity before any state or owner write",
            "git status --porcelain=v1 --untracked-files=all",
            f"unit=U1; owner={owner}; transitions=none; from_revision=r1; gate=none",
            ["src/normalize_label.py"],
        )
        + "\n\n"
        + step(
            2,
            "tracker",
            "persist the implementation claim before owner writes",
            "none: the authorized tracker transition is a structured file edit",
            f"unit=U1; owner={owner}; transitions=Ready->Claimed,Claimed->In Progress; from_revision=r1; gate=none",
            [".project/development/progress.md"],
            ".project/development/progress.md",
        )
        + "\n\n"
        + step(
            3,
            "implementation",
            "make the smallest owner and nearest-regression change",
            "none: the authorized owner and regression changes are structured file edits",
            f"unit=U1; owner={owner}; transitions=none; from_revision=observed-prior; gate=none",
            ["src/normalize_label.py", "tests/test_normalize_label.py"],
        )
        + "\n\n"
        + step(
            4,
            "test",
            "run post-change acceptance and retain its fresh output",
            "python3 -m unittest discover -s tests -v && git diff --check",
            f"unit=U1; owner={owner}; transitions=none; from_revision=observed-prior; gate=none",
            ["src/normalize_label.py", "tests/test_normalize_label.py"],
            "none",
            "G1: focused positive/negative regression and repository diff check",
        )
        + "\n\n"
        + step(
            5,
            "tracker",
            "persist closure after the acceptance predicate is proven",
            "none: the authorized tracker transition is a structured file edit",
            f"unit=U1; owner={owner}; transitions=In Progress->Complete; from_revision=observed-prior; gate=G1:pending->passed",
            [".project/development/task_plan.md"],
            ".project/development/task_plan.md",
            "G1: use the fresh passing output from the preceding step",
        )
        + "\n\n"
        "Closure condition: owner behavior, negative and positive regression, G1, diff/status, and output are evidenced\n"
        "Tracker target state: U1 Complete and G1 passed after post-change evidence\n"
        "Observed receipt requirements: start r1; actual revisions supplied after persistence; transitions match expectations; no Ready->Complete\n"
        "Post-closure next unit: none; the registry contains no dependent unit\n"
        "Out of scope: unrelated code, commit, version, tag, push, release, deployment, and provider actions\n"
    )
    return (
        "Status: in progress\n"
        "Snapshot: tracker_revision=r1; branch=feature; head=" + "a" * 40 + "; status_fingerprint=" + "b" * 64 + "\n"
        "Unit counts: Complete=0; In Progress=0; Claimed=0; Ready=1; Blocked=0; Failed=0\n"
        "Gate counts: passed=0; pending=1; failed=0; unknown-definition=0; conflicting=0\n"
        "Selection basis: " + selection_basis + "\n"
        "Current executable unit: U1; dependency_evidence=none\n"
        "Selected unit: U1\n"
        'Selected required gates: [{"id":"G1","state":"pending"}]\n'
        "Evidence reads: used=5; ceiling=12; extension=0; reason=none\n"
        "Evidence ledger: " + canonical(evidence_ledger_projection(evidence_ledger())) + "\n"
        "Open inventory: " + canonical(inventory()) + "\n"
        "```text\n" + body + "```\n"
    )


def valid_receipts():
    return [
        "unit=U1; owner=src/normalize_label.py; transitions=Ready->Claimed,Claimed->In Progress; revision=r1->r2; gate=none; evidence=.project/development/progress.md",
        "unit=U1; owner=src/normalize_label.py; transitions=In Progress->Complete; revision=r2->r3; gate=G1:pending->passed; evidence=.project/development/task_plan.md",
    ]


def generic_grounding_vector():
    requirement = "Reject blank normalized labels at the owner boundary"
    selection_basis = "U1 is dependency-free and closes the only tracked goal"
    input_paths = ["src/normalize_label.py", "tests/test_normalize_label.py"]
    source_digests = {entry["id"]: entry["sha256"] for entry in evidence_ledger()}
    input_fingerprint = gate_input_fingerprint(input_paths, source_digests)
    tracker = (
        "# Development tracker\n\n"
        "tracker_revision: r1\n\n"
        "## Unit registry\n\n"
        "### U1\n\n"
        "state: Ready\nselected: true\nclaim: none\ndependency: none\n"
        "goal: " + requirement + "\n"
        "owner: src/normalize_label.py\nauthoritative_design: docs/design.md\n"
        "nearest_test: tests/test_normalize_label.py\n"
        "next_convergence_condition: G1 passes\ngate_refs: G1\n\n"
        "## Required gate registry\n\n"
        "### G1\n\nrequired: true\nstatus: pending\nowners: U1\n"
        "command: python3 -m unittest discover -s tests -v\n"
        "inputs_json: " + canonical(input_paths) + "\n"
        "input_fingerprint: " + input_fingerprint + "\npassed_evidence: none\n\n"
        "recovery_condition: Implement U1, run the exact Gate command, and record fresh passing evidence.\n\n"
        "## Decisions and blockers\n\nselection_decision: " + selection_basis + "\nactive_blocker: none\n"
    ).encode("utf-8")
    ledgers = evidence_ledger()
    ledgers = [
        dict(entry, sha256=hashlib.sha256(tracker).hexdigest())
        if entry["id"] == ".project/development/task_plan.md" else entry
        for entry in ledgers
    ]
    manifest_entries = [
        {"path": entry["id"], "mode": "100644", "bytes": len(tracker) if entry["id"] == ".project/development/task_plan.md" else 1, "sha256": entry["sha256"]}
        for entry in ledgers
    ]
    manifest_entries.sort(key=lambda entry: entry["path"].encode("utf-8"))
    manifest = {
        "schema_version": 2,
        "case_id": "tracker-injection",
        "git": {"branch": "feature", "head": "a" * 40, "status_hex": ""},
        "files": manifest_entries,
    }
    grounding = {
        "schema_version": 1,
        "case_id": "tracker-injection",
        "tracker_path": ".project/development/task_plan.md",
        "tracker_base64": base64.b64encode(tracker).decode("ascii"),
    }
    selected_evidence = {
        "unit": "U1",
        "owner": "src/normalize_label.py",
        "gates": ["G1"],
        "evidence": [entry["id"] for entry in ledgers],
        "ledger_sha256": canonical_ledger_sha256(ledgers),
    }
    status = fingerprint({
        "branch": "feature",
        "head": "a" * 40,
        "status": b"",
        "files": [{"path": entry["id"], "sha256": entry["sha256"]} for entry in ledgers],
        "tracker_revision": "r1",
        "selected_evidence": selected_evidence,
    })
    grounded = re.sub(
        r"(?m)^Evidence ledger: .+$",
        "Evidence ledger: " + canonical(evidence_ledger_projection(ledgers)),
        response(),
    )
    grounded = re.sub(
        r"(?m)^Snapshot: .+$",
        "Snapshot: tracker_revision=r1; branch=feature; head=" + "a" * 40 + "; status_fingerprint=" + status,
        grounded,
    )
    return grounded, manifest, grounding


def high_risk_grounding_vector():
    grounded, manifest, grounding = generic_grounding_vector()
    tracker = base64.b64decode(grounding["tracker_base64"], validate=True).decode("utf-8")
    consumer = "tests/test_normalize_label.py is the nearest consumer and package.json exposes integration"
    compatibility = "python3 -m unittest discover -s tests -v must preserve the public contract"
    rollback = "revert only src/normalize_label.py and tests/test_normalize_label.py"
    tracker = tracker.replace(
        "nearest_test: tests/test_normalize_label.py\n",
        "nearest_test: tests/test_normalize_label.py\npackage_surface: package.json\n",
    ).replace(
        "active_blocker: none\n",
        "active_blocker: none\n"
        + "affected_consumer: " + consumer + "\n"
        + "compatibility_gate: " + compatibility + "\n"
        + "rollback_evidence: " + rollback + "\n",
    )
    tracker_bytes = tracker.encode("utf-8")
    manifest = json.loads(json.dumps(manifest))
    manifest["case_id"] = "high-risk-public-consumer"
    for entry in manifest["files"]:
        if entry["path"] == ".project/development/task_plan.md":
            entry["bytes"] = len(tracker_bytes)
            entry["sha256"] = hashlib.sha256(tracker_bytes).hexdigest()
    package_raw = b"{}"
    manifest["files"].append({
        "path": "package.json", "mode": "100644", "bytes": len(package_raw),
        "sha256": hashlib.sha256(package_raw).hexdigest(),
    })
    manifest["files"].sort(key=lambda entry: entry["path"].encode("utf-8"))
    grounding = {
        "schema_version": 1,
        "case_id": "high-risk-public-consumer",
        "tracker_path": ".project/development/task_plan.md",
        "tracker_base64": base64.b64encode(tracker_bytes).decode("ascii"),
    }
    role_by_path = {
        ".project/development/task_plan.md": "tracker",
        "AGENTS.md": "authority",
        "docs/design.md": "design",
        "package.json": "integration",
        "src/normalize_label.py": "owner",
        "tests/test_normalize_label.py": "regression",
    }
    ledger = [
        {"id": entry["path"], "role": role_by_path[entry["path"]], "sha256": entry["sha256"]}
        for entry in manifest["files"]
    ]
    selected_evidence = {
        "unit": "U1", "owner": "src/normalize_label.py", "gates": ["G1"],
        "evidence": [entry["id"] for entry in ledger],
        "ledger_sha256": canonical_ledger_sha256(ledger),
    }
    status = fingerprint({
        "branch": "feature", "head": "a" * 40, "status": b"",
        "files": [{"path": entry["id"], "sha256": entry["sha256"]} for entry in ledger],
        "tracker_revision": "r1", "selected_evidence": selected_evidence,
    })
    grounded = grounded.replace("Protocol profile: Standard", "Protocol profile: High-risk")
    grounded = grounded.replace(
        "Authoritative inputs: " + canonical([entry["id"] for entry in evidence_ledger()]),
        "Authoritative inputs: " + canonical([entry["id"] for entry in ledger]),
    )
    grounded = grounded.replace(
        "Non-goals: API redesign, unrelated refactor, commit, or publication\n",
        "Non-goals: API redesign, unrelated refactor, commit, or publication\n"
        + "Affected consumer: " + consumer + "\n"
        + "Compatibility gate: " + compatibility + "\n"
        + "Rollback evidence: " + rollback + "\n",
    )
    grounded = re.sub(r"(?m)^Evidence reads: .+$", "Evidence reads: used=6; ceiling=20; extension=0; reason=none", grounded)
    grounded = re.sub(
        r"(?m)^Evidence ledger: .+$",
        "Evidence ledger: " + canonical(evidence_ledger_projection(ledger)),
        grounded,
    )
    grounded = re.sub(
        r"(?m)^Snapshot: .+$",
        "Snapshot: tracker_revision=r1; branch=feature; head=" + "a" * 40 + "; status_fingerprint=" + status,
        grounded,
    )
    return grounded, manifest, grounding, consumer


def arguments():
    return dict(
        unit="U1",
        owner="src/normalize_label.py",
        initial_state="Ready",
        initial_revision="r1",
        final_revision="r3",
        required_gates={"G1": "pending"},
        declared_next=None,
        expected_next=None,
    )


def main():
    if PROFILES["Light"]["body"] != 5632:
        fail("Light body budget")
    baseline = response()
    body = baseline.split("```text\n", 1)[1].rsplit("```", 1)[0]
    padding = 10241 - len(body.encode("utf-8"))
    if padding <= 0:
        fail("positive fixture exceeds Standard body budget")
    oversized = baseline.replace("Non-goals: ", "Non-goals: " + "x" * padding, 1)
    expect_rejected("Standard 10240-byte body budget", parse_handoff, oversized, inventory())
    extra_artifact_separator = baseline.replace(
        "artifacts=repository-relative command output",
        "artifacts=command output; diff output",
        1,
    )
    expect_rejected("artifact separator", parse_handoff, extra_artifact_separator, inventory())

    parsed = parse_handoff(response(), inventory())
    if parsed["selected"] != "U1" or len(parsed["steps"]) != 5 or len(parsed["trace_rows"]) != 1:
        fail("valid structured handoff")
    ledger = evidence_ledger()
    projection = evidence_ledger_projection(ledger)
    expect_rejected(
        "compact ledger digest format",
        parse_handoff,
        response().replace(projection["sha256"], "z" * 64, 1),
        inventory(),
    )
    expect_rejected(
        "legacy per-row ledger output",
        parse_handoff,
        response().replace(canonical(projection), canonical(ledger), 1),
        inventory(),
    )
    expect_rejected(
        "redundant preamble prose",
        parse_handoff,
        response().replace("Snapshot: ", "Redundant explanation\nSnapshot: ", 1),
        inventory(),
    )
    expect_rejected(
        "blank line before Snapshot",
        parse_handoff,
        response().replace("\nSnapshot: ", "\n\nSnapshot: ", 1),
        inventory(),
    )
    expect_rejected(
        "undeclared pre-trace Gate diagnostics",
        parse_handoff,
        response().replace(
            "Requirement -> Baseline",
            "Gate G1: redundant diagnostics\nRequirement -> Baseline",
            1,
        ),
        inventory(),
    )
    expect_rejected(
        "step authored-field byte budget",
        parse_handoff,
        response().replace(
            "Action: observe: ",
            "Action: observe: " + "x" * 421,
            1,
        ),
        inventory(),
    )
    expect_rejected(
        "equals field-label separator",
        parse_handoff,
        response().replace("Acceptance Gate: G1", "Acceptance Gate=G1", 1),
        inventory(),
    )
    expect_rejected(
        "repository root as step boundary",
        parse_handoff,
        response().replace(
            'Files/boundary: [".project/development/task_plan.md"]',
            'Files/boundary: ["."]',
            1,
        ),
        inventory(),
    )
    expect_rejected(
        "concrete command with n/a exit",
        parse_handoff,
        response().replace("; exit=0", "; exit=n/a", 1),
        inventory(),
    )
    expect_rejected(
        "none command with concrete exit",
        parse_handoff,
        response().replace("; exit=n/a", "; exit=0", 1),
        inventory(),
    )
    expect_rejected(
        "acceptance exit trailing prose",
        parse_handoff,
        response().replace("; exit=0", "; exit=0 for concrete Command", 1),
        inventory(),
    )
    expect_rejected(
        "authorized permission without authority evidence",
        parse_handoff,
        response().replace("authorized: user", "authorized: absent", 1),
        inventory(),
    )
    expect_rejected(
        "permission evidence prose",
        parse_handoff,
        response().replace("authorized: user", "authorized: user request", 1),
        inventory(),
    )
    expect_rejected(
        "pipe-separated trace row",
        parse_handoff,
        response().replace(
            "Reject blank normalized labels at the owner boundary -> ",
            "Reject blank normalized labels at the owner boundary | ",
            1,
        ),
        inventory(),
    )
    split_implementation = response().replace("Step: 5\n", "Step: 6\n").replace(
        "Step: 4\n", "Step: 5\n"
    )
    split_implementation = split_implementation.replace(
        "\n\nStep: 5\n",
        "\n\n"
        + step(
            4,
            "implementation",
            "edit the nearest regression separately",
            "none: the regression edit is a structured file edit",
            "unit=U1; owner=src/normalize_label.py; transitions=none; from_revision=observed-prior; gate=none",
            ["tests/test_normalize_label.py"],
        )
        + "\n\nStep: 5\n",
        1,
    )
    expect_rejected("split owner and nearest-test edits", parse_handoff, split_implementation, inventory())
    split_closure = response().replace(
        "transitions=In Progress->Complete; from_revision=observed-prior; gate=G1:pending->passed",
        "transitions=none; from_revision=observed-prior; gate=G1:pending->passed",
        1,
    ).replace(
        "\n\nClosure condition:",
        "\n\n"
        + step(
            6,
            "tracker",
            "persist unit closure after the final Gate pass",
            "none: the closure edge is a structured tracker edit",
            "unit=U1; owner=src/normalize_label.py; transitions=In Progress->Complete; from_revision=observed-prior; gate=none",
            [".project/development/task_plan.md"],
            ".project/development/task_plan.md",
            "G1: the preceding tracker step recorded passed evidence",
        )
        + "\n\nClosure condition:",
        1,
    )
    expect_rejected("split final Gate pass and unit closure", parse_handoff, split_closure, inventory())
    result = validate_transition_protocol(valid_receipts(), **arguments())
    reconcile_expectations(parsed["expectations"], result["receipts"], initial_revision="r1")
    if result["state"] != "Complete" or result["gates"] != {"G1": "passed"}:
        fail("valid closure")
    multi_gate_receipts = [
        valid_receipts()[0],
        "unit=U1; owner=src/normalize_label.py; transitions=none; revision=r2->r3; gate=G1:pending->passed; evidence=.project/development/task_plan.md",
        "unit=U1; owner=src/normalize_label.py; transitions=In Progress->Complete; revision=r3->r4; gate=G2:pending->passed; evidence=.project/development/task_plan.md",
    ]
    multi_gate_result = validate_transition_protocol(
        multi_gate_receipts,
        **dict(arguments(), final_revision="r4", required_gates={"G1": "pending", "G2": "pending"}),
    )
    if multi_gate_result["gates"] != {"G1": "passed", "G2": "passed"}:
        fail("valid multi-gate closure")
    grounding = {
        "profile": "Standard",
        "selected": "U1",
        "snapshot": {
            "tracker_revision": "r1",
            "branch": "feature",
            "head": "a" * 40,
            "status_fingerprint": "b" * 64,
        },
        "unit_counts": {"Complete": 0, "In Progress": 0, "Claimed": 0, "Ready": 1, "Blocked": 0, "Failed": 0},
        "gate_counts": {"passed": 0, "pending": 1, "failed": 0, "unknown-definition": 0, "conflicting": 0},
        "inventory": inventory(),
        "selected_gates": [{"id": "G1", "state": "pending"}],
        "repository": ".",
        "owner_boundary": ["src/normalize_label.py", "tests/test_normalize_label.py"],
        "authoritative_inputs": [entry["id"] for entry in evidence_ledger()],
        "selection_basis": "U1 is dependency-free and closes the only tracked goal",
        "dependency_evidence": "none",
        "trace_requirements": [{
            "requirement": "Reject blank normalized labels at the owner boundary",
            "owner": "src/normalize_label.py",
            "test": "tests/test_normalize_label.py",
            "gates": ["G1"],
            "evidence": "tests/test_normalize_label.py",
        }],
        "post_closure_next": None,
        "evidence_ledger": evidence_ledger_projection(evidence_ledger()),
        "gate_contracts": {
            "G1": {
                "owners": ["U1"],
                "command": "python3 -m unittest discover -s tests -v",
                "inputs": ["src/normalize_label.py", "tests/test_normalize_label.py"],
                "input_fingerprint": gate_input_fingerprint(
                    ["src/normalize_label.py", "tests/test_normalize_label.py"],
                    {entry["id"]: entry["sha256"] for entry in evidence_ledger()},
                ),
                "passed_evidence": "none",
            }
        },
    }
    validate_handoff_grounding(parsed, grounding)
    tampered_ledger = parse_handoff(
        response().replace(
            evidence_ledger_projection(evidence_ledger())["sha256"], "0" * 64, 1
        ),
        inventory(),
    )
    expect_rejected(
        "compact ledger digest grounding tamper",
        validate_handoff_grounding,
        tampered_ledger,
        grounding,
    )
    short_goal = "Reject blank normalized labels at the owner boundary"
    long_goal = "Reject empty and whitespace-only labels at the normalization owner boundary."
    long_response = response().replace(short_goal + " ->", long_goal + " ->", 1)
    long_handoff = parse_handoff(long_response, inventory())
    long_grounding = dict(
        grounding,
        trace_requirements=[dict(grounding["trace_requirements"][0], requirement=long_goal)],
    )
    validate_handoff_grounding(long_handoff, long_grounding)
    compressed_handoff = parse_handoff(
        long_response.replace(long_goal + " ->", "Reject empty labels ->", 1), inventory()
    )
    expect_rejected(
        "compressed copied long goal",
        validate_handoff_grounding,
        compressed_handoff,
        long_grounding,
    )
    generic_response, generic_manifest, generic_sources = generic_grounding_vector()
    generic_handoff = validate_forward_case("tracker-injection", generic_response)
    validate_generic_handoff_grounding(
        "tracker-injection", generic_handoff, generic_manifest, generic_sources
    )
    high_response, high_manifest, high_sources, high_consumer = high_risk_grounding_vector()
    high_handoff = validate_forward_case("high-risk-public-consumer", high_response)
    validate_generic_handoff_grounding(
        "high-risk-public-consumer", high_handoff, high_manifest, high_sources
    )
    expect_rejected(
        "High-risk keyword-only consumer evidence",
        validate_grounded_response,
        "high-risk-public-consumer",
        high_response.replace(high_consumer, "consumer compatibility rollback", 1),
        high_manifest,
        high_sources,
    )
    duplicate_registry = (
        "## Unit registry\n### U1\nstate: Ready\n### U1\nstate: Ready\n"
        "## Required gate registry\n"
    )
    expect_rejected(
        "duplicate tracker registry ID",
        _tracker_registry,
        duplicate_registry,
        "Unit registry",
        "Required gate registry",
    )
    gate_manifest = {
        "src/normalize_label.py": {"sha256": "1" * 64},
        "tests/test_normalize_label.py": {"sha256": "2" * 64},
        ".project/development/evidence/G1.pass": {"sha256": "3" * 64},
    }
    gate_inputs = ["src/normalize_label.py", "tests/test_normalize_label.py"]
    gate_fields = {
        "status": "pending",
        "owners": "U1",
        "command": "python3 -m unittest discover -s tests -v",
        "inputs_json": canonical(gate_inputs),
        "input_fingerprint": gate_input_fingerprint(
            gate_inputs, {path: entry["sha256"] for path, entry in gate_manifest.items()}
        ),
        "passed_evidence": "none",
        "recovery_condition": "Run the exact Gate after the bounded implementation fix.",
    }
    expect_rejected(
        "selected gate owner is not reciprocal",
        _gate_contract,
        "G1",
        dict(gate_fields, owners="U9"),
        "U1",
        gate_manifest,
    )
    expect_rejected(
        "selected gate input fingerprint is stale",
        _gate_contract,
        "G1",
        dict(gate_fields, input_fingerprint="0" * 64),
        "U1",
        gate_manifest,
    )
    expect_rejected(
        "passed gate lacks bound evidence",
        _gate_contract,
        "G1",
        dict(gate_fields, status="passed", passed_evidence="missing.pass"),
        "U1",
        gate_manifest,
    )
    for label, mutation in (
        ("generic fabricated branch", generic_response.replace("branch=feature", "branch=fabricated", 1)),
        ("generic fabricated counts", generic_response.replace("Complete=0", "Complete=999", 1)),
        ("generic repository escape", generic_response.replace("Repository: .\n", "Repository: ../outside\n")),
        (
            "generic fabricated post-closure next",
            generic_response.replace(
                "Post-closure next unit: none; the registry contains no dependent unit",
                "Post-closure next unit: U999; fabricated dependency",
            ),
        ),
        (
            "generic fabricated selection evidence",
            generic_response.replace(
                "Selection basis: U1 is dependency-free and closes the only tracked goal",
                "Selection basis: choose U1 randomly without dependency evidence",
            ).replace(
                "Current executable unit: U1; dependency_evidence=none",
                "Current executable unit: U1; dependency_evidence=fabricated",
            ),
        ),
        (
            "generic ungrounded authoritative inputs",
            generic_response.replace(
                "Authoritative inputs: " + canonical([entry["id"] for entry in evidence_ledger()]),
                "Authoritative inputs: README.md only",
            ),
        ),
        (
            "generic fabricated trace",
            generic_response.replace(
                "Reject blank normalized labels at the owner boundary -> src/normalize_label.py currently returns an empty string -> the documented guard is absent -> change src/normalize_label.py and tests/test_normalize_label.py -> preserve trim, TypeError, and public path -> tests/test_normalize_label.py positive and negative regression -> G1 -> tests/test_normalize_label.py output",
                "A -> B -> C -> D -> E -> F -> G -> H",
            ),
        ),
        (
            "generic expanded owner scope",
            generic_response.replace(
                '["src/normalize_label.py","tests/test_normalize_label.py"]',
                '["src/normalize_label.py","src/unrelated.py","tests/test_normalize_label.py"]',
            ),
        ),
    ):
        expect_rejected(
            label,
            validate_grounded_response,
            "tracker-injection",
            mutation,
            generic_manifest,
            generic_sources,
        )
    expect_rejected(
        "generic fabricated selected gate",
        parse_handoff,
        generic_response.replace(
            'Selected required gates: [{"id":"G1","state":"pending"}]',
            'Selected required gates: [{"id":"G1","state":"passed"}]',
        ),
    )
    fabricated = parse_handoff(response().replace("branch=feature", "branch=fabricated"), inventory())
    expect_rejected("fabricated pre-state", validate_handoff_grounding, fabricated, grounding)
    omissions = (
        "Repository: .\n",
        "Evidence ledger: " + canonical(evidence_ledger_projection(evidence_ledger())) + "\n",
        "Open inventory: " + canonical(inventory()) + "\n",
        "Closure condition: owner behavior, negative and positive regression, G1, diff/status, and output are evidenced\n",
        "Requirement -> Baseline -> Root cause/design gap -> Owner change -> Invariant -> Test -> Gate -> Evidence\n",
        "Implementation | Tests | Update tracker | Local commit | Change version | Tag | Push/release\n",
    )
    for value in omissions:
        expect_rejected("semantic omission", parse_handoff, response().replace(value, ""), inventory())
    old_receipt = response().replace("Expected transition:", "Tracker receipt:")
    expect_rejected("forecast receipt", parse_handoff, old_receipt, inventory())
    future_revision = response().replace("from_revision=r1", "from_revision=r1->r2", 1)
    expect_rejected("future revision forecast", parse_handoff, future_revision, inventory())
    snapshot_line = (
        "Snapshot: tracker_revision=r1; branch=feature; head="
        + "a" * 40
        + "; status_fingerprint="
        + "b" * 64
        + "\n"
    )
    duplicate_snapshot = response().replace(snapshot_line, snapshot_line + snapshot_line, 1)
    expect_rejected("duplicate snapshot", parse_handoff, duplicate_snapshot, inventory())
    expect_rejected(
        "body unit conflict",
        parse_handoff,
        response().replace("Unit: U1\n", "Unit: U2\n"),
        inventory(),
    )
    expect_rejected(
        "step unit conflict",
        parse_handoff,
        response().replace("unit=U1; owner=", "unit=U2; owner=", 1),
        inventory(),
    )
    expect_rejected(
        "step owner conflict",
        parse_handoff,
        response().replace(
            "unit=U1; owner=src/normalize_label.py; transitions=none",
            "unit=U1; owner=src/other.py; transitions=none",
            1,
        ),
        inventory(),
    )
    expect_rejected(
        "observation revision conflict",
        parse_handoff,
        response().replace("transitions=none; from_revision=observed-prior", "transitions=none; from_revision=r1"),
        inventory(),
    )
    blank_trace = response().replace(
        "Reject blank normalized labels at the owner boundary -> src/normalize_label.py currently returns an empty string -> the documented guard is absent -> change src/normalize_label.py and tests/test_normalize_label.py -> preserve trim, TypeError, and public path -> tests/test_normalize_label.py positive and negative regression -> G1 -> tests/test_normalize_label.py output",
        "Reject blank normalized labels at the owner boundary ->  -> the documented guard is absent -> change src/normalize_label.py and tests/test_normalize_label.py -> preserve trim, TypeError, and public path -> tests/test_normalize_label.py positive and negative regression -> G1 -> tests/test_normalize_label.py output",
    )
    expect_rejected("blank trace cell", parse_handoff, blank_trace, inventory())
    receipt_only_trace = response().replace(
        "G1 -> tests/test_normalize_label.py output",
        "G1 -> .project/development/evidence/G1.pass",
        1,
    )
    receipt_only_handoff = parse_handoff(receipt_only_trace, inventory())
    expect_rejected(
        "Gate receipt substituted for nearest-test evidence",
        validate_handoff_grounding,
        receipt_only_handoff,
        grounding,
    )
    permission_without_states = response().split(
        "authorized: user | authorized: user | authorized: AGENTS.md | not authorized: absent | not authorized: absent | not authorized: absent | not authorized: absent\n",
        1,
    )[0]
    expect_rejected("missing permission states", parse_handoff, permission_without_states, inventory())
    expect_rejected(
        "implementation denied but edit planned",
        parse_handoff,
        response().replace(
            "authorized: user | authorized: user | authorized: AGENTS.md",
            "not authorized: absent | authorized: user | authorized: AGENTS.md",
        ),
        inventory(),
    )
    expect_rejected(
        "tests denied but validation planned",
        parse_handoff,
        response().replace(
            "authorized: user | authorized: user | authorized: AGENTS.md",
            "authorized: user | not authorized: absent | authorized: AGENTS.md",
        ),
        inventory(),
    )
    expect_rejected(
        "test command mislabeled as observation",
        parse_handoff,
        response().replace(
            "Action: test: run post-change acceptance and retain its fresh output",
            "Action: observe: run post-change acceptance and retain its fresh output",
        ).replace(
            "authorized: user | authorized: user | authorized: AGENTS.md",
            "authorized: user | not authorized: absent | authorized: AGENTS.md",
        ),
        inventory(),
    )
    expect_rejected(
        "custom test command mislabeled as observation",
        parse_handoff,
        response().replace(
            "Action: test: run post-change acceptance and retain its fresh output",
            "Action: observe: run post-change acceptance and retain its fresh output",
        ).replace(
            "Command: python3 -m unittest discover -s tests -v && git diff --check",
            "Command: ./scripts/acceptance.sh",
        ).replace(
            "authorized: user | authorized: user | authorized: AGENTS.md",
            "authorized: user | not authorized: absent | authorized: AGENTS.md",
        ),
        inventory(),
    )
    expect_rejected(
        "mutating command mislabeled as observation",
        parse_handoff,
        response().replace(
            "Command: git status --porcelain=v1 --untracked-files=all",
            "Command: ./scripts/apply-fix.sh",
        ),
        inventory(),
    )
    expect_rejected(
        "mutating Git branch command mislabeled as observation",
        parse_handoff,
        response().replace(
            "Command: git status --porcelain=v1 --untracked-files=all",
            "Command: git branch -D feature/old",
        ),
        inventory(),
    )
    expect_rejected(
        "body owner boundary conflict",
        parse_handoff,
        response().replace(
            'Owner boundary: ["src/normalize_label.py","tests/test_normalize_label.py"]',
            'Owner boundary: ["src/unrelated.py"]',
        ),
        inventory(),
    )
    expect_rejected(
        "state change with observation command",
        parse_handoff,
        response().replace(
            "none: the authorized tracker transition is a structured file edit",
            "git status --porcelain=v1 --untracked-files=all",
            1,
        ),
        inventory(),
    )
    multi_gate_inventory = inventory()
    multi_gate_inventory["gates"].append({
        "id": "G2", "state": "pending", "command_or_recovery": "python3 -m unittest tests.integration"
    })
    multi_gate = response().replace(
        "Gate counts: passed=0; pending=1; failed=0; unknown-definition=0; conflicting=0",
        "Gate counts: passed=0; pending=2; failed=0; unknown-definition=0; conflicting=0",
    ).replace(
        'Selected required gates: [{"id":"G1","state":"pending"}]',
        'Selected required gates: [{"id":"G1","state":"pending"},{"id":"G2","state":"pending"}]',
    ).replace(
        '"gates":[{"id":"G1","state":"pending","command_or_recovery":"python3 -m unittest discover -s tests -v"}]',
        '"gates":[{"id":"G1","state":"pending","command_or_recovery":"python3 -m unittest discover -s tests -v"},{"id":"G2","state":"pending","command_or_recovery":"python3 -m unittest tests.integration"}]',
    )
    expect_rejected(
        "completion with an unpassed required gate",
        parse_handoff,
        multi_gate,
        multi_gate_inventory,
    )
    expect_rejected(
        "passed selected gate remains open",
        parse_handoff,
        response().replace(
            'Selected required gates: [{"id":"G1","state":"pending"}]',
            'Selected required gates: [{"id":"G1","state":"passed"}]',
        ).replace(
            "gate=G1:pending->passed",
            "gate=none",
            1,
        ),
        inventory(),
    )
    mismatch = [valid_receipts()[0], valid_receipts()[1].replace("In Progress->Complete", "In Progress->Failed")]
    expect_rejected(
        "generated observed mismatch",
        reconcile_expectations,
        parsed["expectations"],
        mismatch,
        initial_revision="r1",
    )
    direct = [
        "unit=U1; owner=src/normalize_label.py; transitions=Ready->Complete; revision=r1->r2; gate=G1:pending->passed; evidence=acceptance.txt"
    ]
    expect_rejected("direct Ready to Complete", validate_transition_protocol, direct, **arguments())
    failed_gate_without_failed_unit = [
        valid_receipts()[0],
        "unit=U1; owner=src/normalize_label.py; transitions=none; revision=r2->r3; gate=G1:pending->failed; evidence=.project/development/task_plan.md; recovery=fix regression",
    ]
    failed_arguments = dict(arguments(), final_revision="r3")
    expect_rejected(
        "failed gate without failed unit",
        validate_transition_protocol,
        failed_gate_without_failed_unit,
        **failed_arguments,
    )
    split_claim = [
        "unit=U1; owner=src/normalize_label.py; transitions=Ready->Claimed; revision=r1->r2; gate=none; evidence=.project/development/progress.md",
        "unit=U1; owner=src/normalize_label.py; transitions=Claimed->In Progress; revision=r2->r3; gate=none; evidence=.project/development/progress.md",
        "unit=U1; owner=src/normalize_label.py; transitions=In Progress->Complete; revision=r3->r4; gate=G1:pending->passed; evidence=.project/development/task_plan.md",
    ]
    expect_rejected(
        "aggregate-only step reconciliation",
        reconcile_expectations,
        parsed["expectations"],
        split_claim,
        initial_revision="r1",
    )
    unsafe_evidence = valid_receipts()
    unsafe_evidence[0] = unsafe_evidence[0].replace(
        ".project/development/progress.md", "../../fake"
    )
    expect_rejected("unsafe receipt evidence", validate_transition_protocol, unsafe_evidence, **arguments())
    expect_rejected(
        "reachable Light case assertion",
        validate_forward_case,
        "light-documentation",
        response(),
    )
    expect_rejected(
        "reachable High-risk case assertion",
        validate_forward_case,
        "high-risk-public-consumer",
        response(),
    )
    expect_rejected(
        "reachable Git permission case assertion",
        validate_forward_case,
        "git-permission-split",
        response(),
    )
    expect_rejected(
        "generator-emitted executor receipt",
        parse_handoff,
        response().replace(
            "Closure condition:",
            "observed_receipt:\nunit=U1; revision=r1->r2\nClosure condition:",
            1,
        ),
    )
    expect_rejected(
        "tracker action owner-boundary expansion",
        parse_handoff,
        response().replace(
            'Files/boundary: [".project/development/progress.md"]',
            'Files/boundary: [".project/development/progress.md","src/normalize_label.py"]',
            1,
        ),
    )
    expect_rejected(
        "unsorted step boundary",
        parse_handoff,
        response().replace(
            'Files/boundary: [".project/development/progress.md"]',
            'Files/boundary: [".project/development/progress.md",".project/development/a.md"]',
            1,
        ),
        inventory(),
    )
    if not _has_chinese_status("状态：in progress。\n"):
        fail("minimal Chinese status rejected")
    if _has_chinese_status("Status: in progress.\n"):
        fail("English status accepted as Chinese")
    validate_forward_case("complete-plan", "收敛完成：没有开放单元。\n")
    validate_forward_case(
        "tracker-none-projection",
        "状态：阻塞；tracker: none；read-only projection；no mutation。\n",
    )
    validate_forward_case(
        "migration-permission-release-blocker",
        "状态：阻塞（High-risk）；迁移 Gate 未通过，权限矩阵未授权，因此发布保持阻塞。\n",
    )
    expect_rejected(
        "migration blocker without migration evidence",
        validate_forward_case,
        "migration-permission-release-blocker",
        "状态：阻塞（High-risk）；权限矩阵未授权，因此发布保持阻塞。\n",
    )
    expect_rejected(
        "localized tracker-none token",
        validate_forward_case,
        "tracker-none-projection",
        "状态：阻塞；tracker：none；read-only projection；no mutation。\n",
    )
    validate_forward_case(
        "snapshot-double-drift",
        "状态：insufficient；status-fingerprint-v1 在允许的一次 recompute 后再次 drift，因此阻塞。\n",
    )
    validate_forward_case(
        "snapshot-double-drift",
        "status-fingerprint-v1 重算一次后仍漂移并阻塞；stability=blocked-second-drift。\n",
    )
    validate_forward_case(
        "snapshot-double-drift",
        "status-fingerprint-v1 blocked after the single allowed recompute when drift again appeared.\n",
    )
    validate_forward_case(
        "snapshot-double-drift",
        "状态：已阻塞；status-fingerprint-v1 在唯一允许的重算后再次漂移。\n",
    )
    validate_forward_case(
        "snapshot-double-drift",
        "status-fingerprint-v1 drifted after its single permitted recomputation, so generation blocked.\n",
    )
    validate_forward_case(
        "snapshot-double-drift",
        "status-fingerprint-v1 first framing drift once; post-recompute drift again; block on second drift.\n",
    )
    validate_forward_case(
        "snapshot-double-drift",
        "Second status-fingerprint-v1 drift after one allowed recompute; generation blocked.\n",
    )
    validate_forward_case(
        "snapshot-double-drift",
        "The first status-fingerprint-v1 drift consumed the single permitted recompute; the post-recompute read drifted again, so generation is blocked.\n",
    )
    chinese_drift = "status-fingerprint-v1 唯一一次重新计算后再次发生漂移；生成已阻塞。\n"
    validate_forward_case("snapshot-double-drift", chinese_drift)
    expect_rejected(
        "non-executable evaluator prompt echo",
        validate_forward_case,
        "snapshot-double-drift",
        chinese_drift + "evaluator snapshot/skill/SKILL.md .code-review-graph\n",
    )
    for label, value in (
        ("missing recompute bound", "status-fingerprint-v1 second drift blocked\n"),
        ("missing second drift", "status-fingerprint-v1 recompute once blocked\n"),
        ("missing drift blocker", "status-fingerprint-v1 recompute once then second drift\n"),
    ):
        expect_rejected(label, validate_forward_case, "snapshot-double-drift", value)
    commit_authorized = response().replace(
        "authorized: AGENTS.md | not authorized: absent | not authorized: absent",
        "authorized: AGENTS.md | authorized: user | not authorized: absent",
        1,
    )
    validate_forward_case("git-permission-split", commit_authorized)
    stale = valid_receipts()
    stale[1] = stale[1].replace("revision=r2->r3", "revision=r1->r3")
    expect_rejected("stale revision", validate_transition_protocol, stale, **arguments())
    print("PASS: complete handoff expectations bind to observed transition evidence")


if __name__ == "__main__":
    main()
