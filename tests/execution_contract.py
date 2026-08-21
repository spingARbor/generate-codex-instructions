#!/usr/bin/env python3
"""Machine-verifiable handoff expectations and observed transition receipts."""

from dataclasses import dataclass, replace
import base64
import binascii
import hashlib
import json
from pathlib import PurePosixPath
import re

from status_fingerprint import FingerprintError, fingerprint
from forward_eval_evidence import contains_sensitive_evidence


class ContractError(ValueError):
    pass


def _has_chinese_status(response):
    first_line = response.splitlines()[0] if response.splitlines() else ""
    return len(re.findall(r"[\u3400-\u9fff]", first_line)) >= 2


PROFILES = {
    "Light": {"preamble": 4096, "body": 5632, "reads": 6, "steps": (1, 4), "authored": 420},
    "Standard": {"preamble": 6144, "body": 10240, "reads": 12, "steps": (2, 8), "authored": 420},
    "High-risk": {"preamble": 8192, "body": 14336, "reads": 20, "steps": (3, 12), "authored": 640},
}
STEP_FIELDS = (
    "Step",
    "Action",
    "Command",
    "Files/boundary",
    "Acceptance Gate",
    "Expected transition",
    "Evidence required",
    "Failure/recovery",
)
UNIT_STATES = {"Ready", "Claimed", "In Progress", "Blocked", "Failed", "Complete"}
OPEN_GATE_STATES = {"pending", "failed", "unknown-definition", "conflicting"}
GATE_STATES = OPEN_GATE_STATES | {"passed"}
ACTION_KINDS = {"observe", "implementation", "test", "tracker"}
LEGAL_UNIT_TRANSITIONS = {
    ("Ready", "Claimed"),
    ("Claimed", "In Progress"),
    ("In Progress", "Blocked"),
    ("In Progress", "Failed"),
    ("In Progress", "Complete"),
    ("Blocked", "In Progress"),
    ("Failed", "In Progress"),
}
LEGAL_GATE_TRANSITIONS = {
    ("passed", "pending"),
    ("pending", "passed"),
    ("pending", "failed"),
    ("failed", "pending"),
}
TRACE_HEADER = (
    "Requirement -> Baseline -> Root cause/design gap -> Owner change -> "
    "Invariant -> Test -> Gate -> Evidence"
)
PERMISSION_HEADER = (
    "Implementation | Tests | Update tracker | Local commit | Change version | Tag | Push/release"
)
PERMISSION_COLUMNS = (
    "Implementation", "Tests", "Update tracker", "Local commit",
    "Change version", "Tag", "Push/release",
)
EXECUTABLE_FORWARD_CASES = {
    "chinese-mixed-state-first-delivery",
    "english-localization",
    "light-documentation",
    "high-risk-public-consumer",
    "tracker-injection",
    "git-permission-split",
    "fence-safety",
}
NON_EXECUTABLE_FORWARD_CASES = {
    "complete-plan",
    "insufficient-information",
    "generic-blocker",
    "correct-prerequisite-blocker",
    "migration-permission-release-blocker",
    "tracker-none-projection",
    "ordinary-implementation",
    "tracker-path-escape",
    "concurrency-conflict",
    "snapshot-double-drift",
    "plugin-prerequisites",
}
GENERIC_PROFILES = {
    "chinese-mixed-state-first-delivery": "Standard",
    "english-localization": "Standard",
    "light-documentation": "Light",
    "high-risk-public-consumer": "High-risk",
    "tracker-injection": "Standard",
    "git-permission-split": "Standard",
    "fence-safety": "Standard",
}


@dataclass(frozen=True)
class ExpectedTransition:
    unit: str
    owner: str
    transitions: tuple
    from_revision: str
    gate: tuple | None
    evidence_path: str | None = None


@dataclass(frozen=True)
class Receipt:
    unit: str
    owner: str
    transitions: tuple
    revision_before: str
    revision_after: str
    gate: tuple | None
    evidence: str
    recovery: str | None


def _response_parts(value):
    if not isinstance(value, str):
        raise ContractError("response must be text")
    lines = value.splitlines(keepends=True)
    active = None
    regions = []
    for index, raw_line in enumerate(lines):
        line = raw_line.rstrip("\r\n")
        if active is not None:
            if re.fullmatch(re.escape(active[0]) + "{" + str(active[1]) + ",}[ \t]*", line):
                regions.append((active[2], index, active[3]))
                active = None
            continue
        opening = re.fullmatch(r"(`{3,})(.*)", line)
        if opening:
            marker = opening.group(1)
            active = (marker[0], len(marker), index, opening.group(2).strip())
    if active is not None or len(regions) != 1 or regions[0][2] != "text":
        raise ContractError("response must contain exactly one text fence")
    opening, closing, _ = regions[0]
    if "".join(lines[closing + 1:]).strip():
        raise ContractError("content after instruction fence")
    return "".join(lines[:opening]), "".join(lines[opening + 1:closing])


def _pairs(value, label):
    parsed = {}
    for part in value.split("; "):
        if "=" not in part:
            raise ContractError(label + " field")
        key, item = part.split("=", 1)
        if key in parsed:
            raise ContractError("duplicate " + label + " field")
        parsed[key] = item
    return parsed


def _transitions(value):
    if value == "none":
        return ()
    parsed = []
    for transition in value.split(","):
        states = transition.split("->")
        if len(states) != 2 or any(state not in UNIT_STATES for state in states):
            raise ContractError("unit transition syntax")
        if tuple(states) not in LEGAL_UNIT_TRANSITIONS:
            raise ContractError("illegal unit transition")
        parsed.append(tuple(states))
    for left, right in zip(parsed, parsed[1:]):
        if left[1] != right[0]:
            raise ContractError("non-contiguous unit transition")
    return tuple(parsed)


def _gate(value):
    if value == "none":
        return None
    match = re.fullmatch(
        r"([A-Za-z0-9._-]+):(passed|pending|failed)->(pending|passed|failed)", value
    )
    if match is None:
        raise ContractError("gate transition syntax")
    result = (match.group(1), match.group(2), match.group(3))
    if result[1:] not in LEGAL_GATE_TRANSITIONS:
        raise ContractError("illegal gate transition")
    return result


def parse_expected_transition(value):
    parsed = _pairs(value, "expected transition")
    required = ("unit", "owner", "transitions", "from_revision", "gate")
    if tuple(parsed) != required:
        raise ContractError("expected transition schema")
    if not parsed["unit"] or not parsed["owner"] or not parsed["from_revision"]:
        raise ContractError("empty expected transition field")
    if "->" in parsed["from_revision"]:
        raise ContractError("expected transition forecasts future revision")
    _safe_path(parsed["owner"], "expected transition owner")
    return ExpectedTransition(
        unit=parsed["unit"],
        owner=parsed["owner"],
        transitions=_transitions(parsed["transitions"]),
        from_revision=parsed["from_revision"],
        gate=_gate(parsed["gate"]),
    )


def parse_receipt(value):
    parsed = _pairs(value, "observed receipt")
    required = ("unit", "owner", "transitions", "revision", "gate", "evidence")
    if tuple(parsed) not in (required, required + ("recovery",)):
        raise ContractError("observed receipt schema")
    revisions = parsed["revision"].split("->")
    if len(revisions) != 2 or not all(revisions):
        raise ContractError("tracker revision syntax")
    transitions = _transitions(parsed["transitions"])
    gate = _gate(parsed["gate"])
    if not parsed["unit"] or not parsed["owner"] or not parsed["evidence"]:
        raise ContractError("empty observed receipt field")
    _safe_path(parsed["owner"], "observed receipt owner")
    _safe_path(parsed["evidence"], "observed receipt evidence")
    changes_state = bool(transitions) or gate is not None
    if changes_state and revisions[0] == revisions[1]:
        raise ContractError("state transition requires a new revision")
    if not changes_state and revisions[0] != revisions[1]:
        raise ContractError("observation cannot advance revision")
    return Receipt(
        unit=parsed["unit"],
        owner=parsed["owner"],
        transitions=transitions,
        revision_before=revisions[0],
        revision_after=revisions[1],
        gate=gate,
        evidence=parsed["evidence"],
        recovery=parsed.get("recovery"),
    )


def _canonical_json_line(preamble, prefix, label):
    matches = re.findall(r"(?m)^" + re.escape(prefix) + r"(.+)$", preamble)
    if len(matches) != 1:
        raise ContractError(label)
    raw = matches[0]
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ContractError(label + " JSON") from error
    if json.dumps(value, ensure_ascii=False, separators=(",", ":")) != raw:
        raise ContractError(label + " canonical JSON")
    return value


def _safe_path(value, label):
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/"):
        raise ContractError(label)
    path = PurePosixPath(value)
    if path.as_posix() != value or any(part in ("", ".", "..") for part in path.parts):
        raise ContractError(label)


def _validate_evidence_ledger(preamble, used):
    ledger = _canonical_json_line(preamble, "Evidence ledger: ", "evidence ledger")
    if not isinstance(ledger, dict) or tuple(ledger) != ("sha256", "rows"):
        raise ContractError("evidence ledger schema")
    if re.fullmatch(r"[0-9a-f]{64}", ledger["sha256"] or "") is None:
        raise ContractError("evidence ledger digest")
    rows = ledger["rows"]
    if not isinstance(rows, list) or len(rows) != used:
        raise ContractError("evidence ledger count")
    ids = []
    for entry in rows:
        if not isinstance(entry, dict) or tuple(entry) != ("id", "role"):
            raise ContractError("evidence ledger schema")
        _safe_path(entry["id"], "evidence ledger id")
        if not isinstance(entry["role"], str) or not entry["role"]:
            raise ContractError("evidence ledger role")
        ids.append(entry["id"])
    if ids != sorted(ids, key=lambda item: item.encode("utf-8")) or len(ids) != len(set(ids)):
        raise ContractError("evidence ledger ordering")
    return ledger


def canonical_ledger_sha256(ledger):
    raw = json.dumps(ledger, ensure_ascii=False, separators=(",", ":")) + "\n"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def evidence_ledger_projection(ledger):
    return {
        "sha256": canonical_ledger_sha256(ledger),
        "rows": [{"id": entry["id"], "role": entry["role"]} for entry in ledger],
    }


def gate_input_fingerprint(paths, file_digests):
    if not isinstance(paths, list) or not paths:
        raise ContractError("gate input paths")
    records = []
    for path in paths:
        _safe_path(path, "gate input path")
        digest = file_digests.get(path)
        if re.fullmatch(r"[0-9a-f]{64}", digest or "") is None:
            raise ContractError("gate input digest")
        records.append({"path": path, "sha256": digest})
    if paths != sorted(paths, key=lambda item: item.encode("utf-8")) or len(paths) != len(set(paths)):
        raise ContractError("gate input ordering")
    raw = json.dumps(records, ensure_ascii=False, separators=(",", ":")) + "\n"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _validate_inventory(preamble, expected_inventory):
    inventory = _canonical_json_line(preamble, "Open inventory: ", "open inventory")
    if not isinstance(inventory, dict) or tuple(inventory) != ("units", "gates", "blockers"):
        raise ContractError("open inventory schema")
    schemas = {
        "units": ("id", "state", "claim", "dependency", "next"),
        "gates": ("id", "state", "command_or_recovery"),
        "blockers": ("id", "owner", "detail", "recovery"),
    }
    for group, keys in schemas.items():
        entries = inventory[group]
        if not isinstance(entries, list):
            raise ContractError(group + " inventory")
        ids = []
        for entry in entries:
            if not isinstance(entry, dict) or tuple(entry) != keys:
                raise ContractError(group + " inventory schema")
            if not all(isinstance(entry[key], str) and entry[key] for key in keys):
                raise ContractError(group + " inventory field")
            ids.append(entry["id"])
        if ids != sorted(ids, key=lambda item: item.encode("utf-8")) or len(ids) != len(set(ids)):
            raise ContractError(group + " inventory ordering")
    if any(entry["state"] not in UNIT_STATES - {"Complete"} for entry in inventory["units"]):
        raise ContractError("open unit state")
    if any(entry["state"] not in OPEN_GATE_STATES for entry in inventory["gates"]):
        raise ContractError("open gate state")
    if expected_inventory is not None and inventory != expected_inventory:
        raise ContractError("open inventory")
    return inventory


def _canonical_path_array(value, label):
    try:
        paths = json.loads(value)
    except json.JSONDecodeError as error:
        raise ContractError(label + " JSON") from error
    if json.dumps(paths, ensure_ascii=False, separators=(",", ":")) != value:
        raise ContractError(label + " canonical JSON")
    if not isinstance(paths, list) or not paths:
        raise ContractError(label)
    for path in paths:
        _safe_path(path, label)
    if paths != sorted(paths, key=lambda item: item.encode("utf-8")) or len(paths) != len(set(paths)):
        raise ContractError(label + " ordering")
    return paths


def _validate_selected_gates(preamble, inventory):
    gates = _canonical_json_line(
        preamble, "Selected required gates: ", "selected required gates"
    )
    if not isinstance(gates, list):
        raise ContractError("selected required gates")
    open_gates = {entry["id"]: entry["state"] for entry in inventory["gates"]}
    ids = []
    for entry in gates:
        if not isinstance(entry, dict) or tuple(entry) != ("id", "state"):
            raise ContractError("selected required gate schema")
        if not isinstance(entry["id"], str) or not entry["id"] or entry["state"] not in GATE_STATES:
            raise ContractError("selected required gate field")
        if entry["state"] == "passed" and entry["id"] in open_gates:
            raise ContractError("passed selected gate is still open")
        if entry["state"] != "passed" and open_gates.get(entry["id"]) != entry["state"]:
            raise ContractError("selected required gate inventory")
        ids.append(entry["id"])
    if ids != sorted(ids, key=lambda item: item.encode("utf-8")) or len(ids) != len(set(ids)):
        raise ContractError("selected required gate ordering")
    return gates


def _require_single_prefix(body, prefix):
    matches = re.findall(r"(?m)^" + re.escape(prefix) + r"(.+)$", body)
    if len(matches) != 1:
        raise ContractError("missing or duplicate " + prefix.rstrip(": "))
    return matches[0]


def _permission_state(value, label):
    match = re.fullmatch(
        r"(authorized|not authorized|blocked): ([A-Za-z0-9._/-]+|absent)", value
    )
    if match is None:
        raise ContractError(label + " permission")
    if match.group(1) in {"authorized", "blocked"} and match.group(2) == "absent":
        raise ContractError(label + " permission evidence")
    return match.group(1)


def _evidence_requirement(value, changes_state):
    parsed = _pairs(value, "evidence required")
    if tuple(parsed) != ("receipt", "artifacts") or not parsed["artifacts"].strip():
        raise ContractError("evidence required schema")
    receipt_path = parsed["receipt"]
    if receipt_path == "none":
        if changes_state:
            raise ContractError("state-changing step lacks receipt path")
        return None
    _safe_path(receipt_path, "expected receipt evidence")
    if not changes_state:
        raise ContractError("observation step forecasts a receipt")
    return receipt_path


def _observation_only_command(command):
    return command.strip() in {
        "git status --porcelain=v1 --untracked-files=all",
        "git status --porcelain=v1 -z --untracked-files=all",
        "git diff --check",
        "git rev-parse --verify HEAD",
        "git branch --show-current",
    }


def _validate_gate_closure(expectations, selected_gates):
    states = {entry["id"]: entry["state"] for entry in selected_gates}
    merge_required = any(state != "passed" for state in states.values())
    completed = 0
    for expectation in expectations:
        if expectation.gate is not None:
            gate_id, before, after = expectation.gate
            if gate_id not in states or states[gate_id] != before:
                raise ContractError("selected required gate transition")
            states[gate_id] = after
            if after != "passed":
                merge_required = True
        if any(after == "Complete" for _, after in expectation.transitions):
            completed += 1
            if any(state != "passed" for state in states.values()):
                raise ContractError("completion has unpassed required gate")
            if merge_required and (
                expectation.gate is None or expectation.gate[2] != "passed"
            ):
                raise ContractError("final gate pass and unit closure are split")
    if completed != 1 or any(state != "passed" for state in states.values()):
        raise ContractError("selected unit closure protocol")


def parse_handoff(response, expected_inventory=None):
    preamble, body = _response_parts(response)
    preamble_lines = preamble.splitlines()
    preamble_prefixes = (
        "Snapshot: ", "Unit counts: ", "Gate counts: ", "Selection basis: ",
        "Current executable unit: ", "Selected unit: ", "Selected required gates: ",
        "Evidence reads: ", "Evidence ledger: ", "Open inventory: ",
    )
    if (
        len(preamble_lines) != len(preamble_prefixes) + 1
        or not preamble_lines[0].strip()
        or any(
            not line.startswith(prefix)
            for line, prefix in zip(preamble_lines[1:], preamble_prefixes)
        )
    ):
        raise ContractError("preamble schema")
    first_line = body.splitlines()[0] if body.splitlines() else ""
    profile_match = re.fullmatch(r"Protocol profile: (Light|Standard|High-risk)", first_line)
    if profile_match is None:
        raise ContractError("protocol profile")
    profile = profile_match.group(1)
    limits = PROFILES[profile]
    before_trace = body.split(TRACE_HEADER + "\n", 1)[0].splitlines()
    if profile in {"Light", "Standard"} and len(before_trace) != 8:
        raise ContractError("pre-trace schema")
    if len(preamble.encode("utf-8")) > limits["preamble"]:
        raise ContractError("preamble UTF-8 budget")
    if len(body.encode("utf-8")) > limits["body"]:
        raise ContractError("body UTF-8 budget")
    ledger_matches = re.findall(
        r"(?m)^Evidence reads: used=(\d+); ceiling=(\d+); extension=(\d+); reason=(.+)$",
        preamble,
    )
    if len(ledger_matches) != 1:
        raise ContractError("evidence-read ledger")
    used, ceiling, extension = map(int, ledger_matches[0][:3])
    if ceiling != limits["reads"] or extension > ceiling // 2 or used > ceiling + extension:
        raise ContractError("evidence-read budget")
    if extension and ledger_matches[0][3].strip().lower() in ("", "none"):
        raise ContractError("evidence-read extension reason")
    evidence_ledger = _validate_evidence_ledger(preamble, used)
    inventory = _validate_inventory(preamble, expected_inventory)
    selected_matches = re.findall(r"(?m)^Selected unit: ([A-Za-z0-9._-]+)$", preamble)
    if len(selected_matches) != 1:
        raise ContractError("selected unit")
    selected = selected_matches[0]
    selected_entries = [entry for entry in inventory["units"] if entry["id"] == selected]
    if len(selected_entries) != 1:
        raise ContractError("selected unit absent from inventory")
    if selected_entries[0]["state"] not in {"Ready", "Claimed", "In Progress"}:
        raise ContractError("selected unit is not executable")
    selected_gates = _validate_selected_gates(preamble, inventory)
    snapshots = re.findall(
        r"(?m)^Snapshot: tracker_revision=([^;\r\n]+); branch=([^;\r\n]+); head=([0-9a-f]{40}|[0-9a-f]{64}); status_fingerprint=([0-9a-f]{64})$",
        preamble,
    )
    if len(snapshots) != 1:
        raise ContractError("preamble Snapshot")
    tracker_revision, branch, head, status_fingerprint = snapshots[0]
    unit_counts_matches = re.findall(
        r"(?m)^Unit counts: Complete=(\d+); In Progress=(\d+); Claimed=(\d+); Ready=(\d+); Blocked=(\d+); Failed=(\d+)$",
        preamble,
    )
    gate_counts_matches = re.findall(
        r"(?m)^Gate counts: passed=(\d+); pending=(\d+); failed=(\d+); unknown-definition=(\d+); conflicting=(\d+)$",
        preamble,
    )
    if len(unit_counts_matches) != 1 or len(gate_counts_matches) != 1:
        raise ContractError("preamble counts")
    unit_counts = dict(zip(("Complete", "In Progress", "Claimed", "Ready", "Blocked", "Failed"), map(int, unit_counts_matches[0])))
    gate_counts = dict(zip(("passed", "pending", "failed", "unknown-definition", "conflicting"), map(int, gate_counts_matches[0])))
    for state in UNIT_STATES - {"Complete"}:
        if unit_counts[state] != sum(entry["state"] == state for entry in inventory["units"]):
            raise ContractError("unit count mismatch")
    for state in OPEN_GATE_STATES:
        if gate_counts[state] != sum(entry["state"] == state for entry in inventory["gates"]):
            raise ContractError("gate count mismatch")
    selection = re.findall(r"(?m)^Selection basis: (.+)$", preamble)
    current = re.findall(r"(?m)^Current executable unit: ([A-Za-z0-9._-]+); dependency_evidence=(.+)$", preamble)
    if len(selection) != 1 or len(current) != 1 or current[0][0] != selected:
        raise ContractError("selection protocol")
    selection_basis = selection[0]
    dependency_evidence = current[0][1]

    body_unit = _require_single_prefix(body, "Unit: ")
    if body_unit != selected:
        raise ContractError("body unit differs from selected unit")
    body_fields = {}
    for prefix in (
        "Repository: ", "Capability: ", "Authoritative inputs: ",
        "Owner boundary: ", "Invariants: ", "Non-goals: ",
        "Closure condition: ", "Tracker target state: ",
        "Observed receipt requirements: ", "Post-closure next unit: ",
        "Out of scope: ",
    ):
        body_fields[prefix[:-2]] = _require_single_prefix(body, prefix)
    if body_fields["Repository"] != ".":
        raise ContractError("repository root")
    authoritative_inputs = _canonical_path_array(
        body_fields["Authoritative inputs"], "authoritative inputs"
    )
    owner_boundary = _canonical_path_array(body_fields["Owner boundary"], "owner boundary")
    if body.count(TRACE_HEADER) != 1:
        raise ContractError("trace header")
    if body.count(PERMISSION_HEADER) != 1:
        raise ContractError("permission matrix")
    permission_lines = body.split(PERMISSION_HEADER + "\n", 1)[1].splitlines()
    if not permission_lines:
        raise ContractError("permission states")
    permission_line = permission_lines[0]
    cells = [item.strip() for item in permission_line.split("|")]
    if len(cells) != 7:
        raise ContractError("permission states")
    permission_states = {
        column: _permission_state(cell, column)
        for column, cell in zip(PERMISSION_COLUMNS, cells)
    }
    trace_tail = body.split(TRACE_HEADER + "\n", 1)[1]
    trace_lines = []
    for line in trace_tail.splitlines():
        if line.startswith("Permission matrix:") or line.startswith("Step: 1"):
            break
        if line.strip():
            trace_lines.append(line)
    if not trace_lines or any(
        len(cells := line.split(" -> ")) != 8 or any(not cell.strip() for cell in cells)
        for line in trace_lines
    ):
        raise ContractError("requirement trace rows")
    trace_rows = [tuple(line.split(" -> ")) for line in trace_lines]

    field_pattern = "|".join(re.escape(field) for field in STEP_FIELDS)
    records = []
    current = None
    for line in body.splitlines():
        match = re.fullmatch(r"(" + field_pattern + r"): (.+)", line)
        if match is None:
            continue
        field, value = match.groups()
        if field == "Step":
            if current is not None:
                records.append(current)
            current = {}
        if current is None or field in current:
            raise ContractError("step field ordering")
        current[field] = value
    if current is not None:
        records.append(current)
    low, high = limits["steps"]
    if not low <= len(records) <= high:
        raise ContractError("step count")
    expectations = []
    operations = []
    step_boundaries = []
    tracker_ids = [
        entry["id"] for entry in evidence_ledger["rows"] if entry["role"] == "tracker"
    ]
    if len(tracker_ids) != 1:
        raise ContractError("governing tracker cardinality")
    tracker_root = PurePosixPath(tracker_ids[0]).parent
    for index, record in enumerate(records, 1):
        if tuple(record) != STEP_FIELDS or record["Step"] != str(index):
            raise ContractError("step schema or numbering")
        if sum(
            len(record[field].encode("utf-8"))
            for field in ("Action", "Acceptance Gate", "Failure/recovery")
        ) > limits["authored"]:
            raise ContractError("step authored-field budget")
        action = re.fullmatch(r"(observe|implementation|test|tracker): (.+)", record["Action"])
        if action is None:
            raise ContractError("typed action")
        operation = action.group(1)
        boundaries = _canonical_path_array(record["Files/boundary"], "step files boundary")
        if record["Command"].startswith("none: "):
            if len(record["Command"]) <= 6:
                raise ContractError("command reason")
        elif not record["Command"].strip():
            raise ContractError("concrete command")
        acceptance = re.fullmatch(r".+; exit=(0|n/a)", record["Acceptance Gate"])
        if acceptance is None:
            raise ContractError("acceptance exit")
        command_is_none = record["Command"].startswith("none: ")
        if (acceptance.group(1) == "n/a") != command_is_none:
            raise ContractError("acceptance exit and command effect")
        expectation = parse_expected_transition(record["Expected transition"])
        changes_state = bool(expectation.transitions) or expectation.gate is not None
        expectation = replace(
            expectation,
            evidence_path=_evidence_requirement(record["Evidence required"], changes_state),
        )
        expectations.append(expectation)
        operations.append(operation)
        step_boundaries.append(boundaries)
        if re.fullmatch(r"stop=.+; recovery=.+", record["Failure/recovery"]) is None:
            raise ContractError("failure/recovery schema")
    if any(label in body for label in ("Tracker receipt:", "Tracker transition receipt:", "Post-state:")):
        raise ContractError("forecast receipt field")
    if re.search(r"(?m)^(?:observed_receipt|post_closure_next_unit):", body):
        raise ContractError("generator emitted executor receipt")
    if any(expectation.unit != selected for expectation in expectations):
        raise ContractError("step unit differs from selected unit")
    if len({expectation.owner for expectation in expectations}) != 1:
        raise ContractError("step owner conflict")
    if any(expectation.owner not in owner_boundary for expectation in expectations):
        raise ContractError("step owner outside owner boundary")
    for record, expectation, operation, boundaries in zip(
        records, expectations, operations, step_boundaries
    ):
        changes_state = bool(expectation.transitions) or expectation.gate is not None
        if operation == "tracker":
            if not changes_state:
                raise ContractError("tracker action lacks state transition")
            if _observation_only_command(record["Command"]):
                raise ContractError("tracker action uses observation-only command")
            if not record["Command"].startswith("none: "):
                raise ContractError("tracker action command effect is not proven")
            if any(
                path != tracker_ids[0] and tracker_root not in PurePosixPath(path).parents
                for path in boundaries
            ):
                raise ContractError("tracker action boundary outside tracker root")
        elif changes_state:
            raise ContractError("non-tracker action changes state")
        if operation == "implementation":
            if permission_states["Implementation"] != "authorized":
                raise ContractError("implementation action lacks permission")
            if not set(boundaries).issubset(owner_boundary):
                raise ContractError("implementation boundary outside owner boundary")
            if not record["Command"].startswith("none: "):
                raise ContractError("implementation command effect is not proven")
        if operation == "test":
            if permission_states["Tests"] != "authorized":
                raise ContractError("test action lacks permission")
            if record["Command"].startswith("none: "):
                raise ContractError("test action lacks command")
            if not set(boundaries).issubset(owner_boundary):
                raise ContractError("test boundary outside owner boundary")
        if operation == "observe" and (
            record["Command"].startswith("none: ")
            or not _observation_only_command(record["Command"])
        ):
            raise ContractError("observation command effect is not proven")
    if any(
        expectation.transitions or expectation.gate is not None
        for expectation in expectations
    ) and permission_states["Update tracker"] != "authorized":
        raise ContractError("state transitions require tracker-update permission")
    if operations.count("implementation") > 1:
        raise ContractError("owner and nearest-test edits are split")
    prior_state_change = False
    for expectation in expectations:
        source = "observed-prior" if prior_state_change else tracker_revision
        if expectation.from_revision != source:
            raise ContractError("expected transition revision chain")
        prior_state_change = prior_state_change or bool(expectation.transitions) or expectation.gate is not None
    _validate_gate_closure(expectations, selected_gates)
    next_match = re.fullmatch(
        r"([A-Za-z0-9._-]+|none)(?:; .+)?", body_fields["Post-closure next unit"]
    )
    if next_match is None:
        raise ContractError("post-closure next unit")
    post_closure_next = None if next_match.group(1) == "none" else next_match.group(1)
    return {
        "preamble": preamble,
        "body": body,
        "profile": profile,
        "steps": records,
        "expectations": expectations,
        "selected": selected,
        "selected_gates": selected_gates,
        "inventory": inventory,
        "evidence_ledger": evidence_ledger,
        "evidence_ledger_sha256": evidence_ledger["sha256"],
        "trace_rows": trace_rows,
        "tracker_revision": tracker_revision,
        "snapshot": {
            "tracker_revision": tracker_revision,
            "branch": branch,
            "head": head,
            "status_fingerprint": status_fingerprint,
        },
        "unit_counts": unit_counts,
        "gate_counts": gate_counts,
        "body_fields": body_fields,
        "repository": body_fields["Repository"],
        "authoritative_inputs": authoritative_inputs,
        "owner_boundary": owner_boundary,
        "selection_basis": selection_basis,
        "dependency_evidence": dependency_evidence,
        "post_closure_next": post_closure_next,
        "operations": operations,
        "step_boundaries": step_boundaries,
        "permission_states": permission_states,
    }


def validate_handoff_grounding(handoff, expected):
    required = (
        "profile", "selected", "snapshot", "unit_counts", "gate_counts",
        "inventory", "selected_gates",
        "repository", "owner_boundary", "authoritative_inputs",
        "selection_basis", "dependency_evidence", "trace_requirements",
        "post_closure_next", "evidence_ledger", "gate_contracts",
    )
    if tuple(expected) != required:
        raise ContractError("grounding expectation schema")
    for field in ("profile", "selected"):
        if handoff[field] != expected[field]:
            raise ContractError("ungrounded " + field.replace("_", " "))
    if handoff["inventory"] != expected["inventory"]:
        raise ContractError("ungrounded open inventory")
    if handoff["selected_gates"] != expected["selected_gates"]:
        raise ContractError("ungrounded selected required gates")
    if handoff["evidence_ledger"] != expected["evidence_ledger"]:
        raise ContractError("ungrounded evidence ledger")
    for field in ("snapshot", "unit_counts", "gate_counts"):
        if handoff[field] != expected[field]:
            raise ContractError("ungrounded " + field.replace("_", " "))
    for field in (
        "repository", "owner_boundary", "authoritative_inputs", "selection_basis",
        "dependency_evidence", "post_closure_next",
    ):
        if handoff[field] != expected[field]:
            raise ContractError("ungrounded " + field.replace("_", " "))
    trace_requirements = expected["trace_requirements"]
    if not isinstance(trace_requirements, list) or len(handoff["trace_rows"]) != len(trace_requirements):
        raise ContractError("ungrounded requirement trace count")
    for row, requirement in zip(handoff["trace_rows"], trace_requirements):
        if not isinstance(requirement, dict) or tuple(requirement) != (
            "requirement", "owner", "test", "gates", "evidence"
        ):
            raise ContractError("grounded trace expectation schema")
        if row[0] != requirement["requirement"]:
            raise ContractError("ungrounded trace requirement")
        if requirement["owner"] not in row[3] or requirement["test"] not in row[5]:
            raise ContractError("ungrounded trace owner or test")
        if any(gate_id not in row[6].split(",") for gate_id in requirement["gates"]):
            raise ContractError("ungrounded trace gate")
        if requirement["evidence"] not in row[7]:
            raise ContractError("ungrounded trace evidence")
    contracts = expected["gate_contracts"]
    selected_ids = [entry["id"] for entry in handoff["selected_gates"]]
    if not isinstance(contracts, dict) or set(contracts) != set(selected_ids):
        raise ContractError("grounded gate contract topology")
    gate_states = {entry["id"]: entry["state"] for entry in handoff["selected_gates"]}
    for gate_id, contract in contracts.items():
        if not isinstance(contract, dict) or tuple(contract) != (
            "owners", "command", "inputs", "input_fingerprint", "passed_evidence"
        ):
            raise ContractError("grounded gate contract schema")
        if handoff["selected"] not in contract["owners"]:
            raise ContractError("grounded gate owner reciprocity")
        if re.fullmatch(r"[0-9a-f]{64}", contract["input_fingerprint"] or "") is None:
            raise ContractError("grounded gate input fingerprint")
    for record, expectation, operation, boundaries in zip(
        handoff["steps"], handoff["expectations"], handoff["operations"], handoff["step_boundaries"]
    ):
        if expectation.gate is not None:
            gate_id, before, after = expectation.gate
            if gate_states.get(gate_id) != before:
                raise ContractError("grounded gate transition order")
            gate_states[gate_id] = after
        if operation == "implementation":
            for gate_id, contract in contracts.items():
                if set(boundaries).intersection(contract["inputs"]) and gate_states[gate_id] == "passed":
                    raise ContractError("passed gate was not invalidated before input change")
        if operation == "test":
            allowed = {
                contract["command"] for contract in contracts.values()
            } | {
                contract["command"] + " && git diff --check" for contract in contracts.values()
            }
            if record["Command"] not in allowed:
                raise ContractError("test command is not grounded by a selected gate")
    return handoff


def _tracker_registry(text, heading, next_heading):
    match = re.search(
        r"(?ms)^## " + re.escape(heading) + r"\n(.*?)(?=^## " + re.escape(next_heading) + r"\n|\Z)",
        text,
    )
    if match is None:
        raise ContractError("grounding tracker registry " + heading)
    entries = {}
    for section in re.finditer(r"(?ms)^### ([A-Za-z0-9._-]+)\n(.*?)(?=^### |\Z)", match.group(1)):
        fields = {}
        for key, value in re.findall(r"(?m)^([A-Za-z0-9_]+): (.+)$", section.group(2)):
            if key in fields:
                raise ContractError("grounding duplicate tracker field")
            fields[key] = value
        entry_id = section.group(1)
        if entry_id in entries:
            raise ContractError("grounding duplicate tracker id")
        entries[entry_id] = fields
    if not entries:
        raise ContractError("grounding empty tracker registry")
    return entries


def _manifest_files(document, case_id):
    if not isinstance(document, dict) or tuple(document) != ("schema_version", "case_id", "git", "files"):
        raise ContractError("grounding fixture manifest schema")
    if document["schema_version"] != 2 or document["case_id"] != case_id:
        raise ContractError("grounding fixture manifest identity")
    git = document["git"]
    if not isinstance(git, dict) or tuple(git) != ("branch", "head", "status_hex"):
        raise ContractError("grounding fixture Git schema")
    if not git["branch"] or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", git["head"] or "") is None:
        raise ContractError("grounding fixture Git identity")
    try:
        bytes.fromhex(git["status_hex"])
    except (TypeError, ValueError) as error:
        raise ContractError("grounding fixture status") from error
    files = {}
    last = None
    for entry in document["files"]:
        if not isinstance(entry, dict) or tuple(entry) != ("path", "mode", "bytes", "sha256"):
            raise ContractError("grounding fixture file schema")
        _safe_path(entry["path"], "grounding fixture path")
        encoded = entry["path"].encode("utf-8")
        if last is not None and encoded <= last:
            raise ContractError("grounding fixture ordering")
        last = encoded
        if type(entry["bytes"]) is not int or entry["bytes"] < 0 or re.fullmatch(r"[0-9a-f]{64}", entry["sha256"] or "") is None:
            raise ContractError("grounding fixture file value")
        files[entry["path"]] = entry
    return git, files


def _grounding_tracker(document, case_id, manifest_files):
    if not isinstance(document, dict) or tuple(document) != (
        "schema_version", "case_id", "tracker_path", "tracker_base64"
    ):
        raise ContractError("generic grounding source schema")
    if document["schema_version"] != 1 or document["case_id"] != case_id:
        raise ContractError("generic grounding source identity")
    path = document["tracker_path"]
    _safe_path(path, "generic grounding tracker path")
    if path != ".project/development/task_plan.md" or path not in manifest_files:
        raise ContractError("generic grounding tracker selection")
    try:
        raw = base64.b64decode(document["tracker_base64"], validate=True)
    except (TypeError, ValueError, binascii.Error) as error:
        raise ContractError("generic grounding tracker base64") from error
    entry = manifest_files[path]
    if len(raw) != entry["bytes"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
        raise ContractError("generic grounding tracker binding")
    if contains_sensitive_evidence(raw):
        raise ContractError("generic grounding tracker sensitive content")
    try:
        return raw.decode("utf-8")
    except UnicodeError as error:
        raise ContractError("generic grounding tracker UTF-8") from error


def _tracker_json(fields, key, label):
    raw = fields.get(key)
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as error:
        raise ContractError(label + " JSON") from error
    if json.dumps(value, ensure_ascii=False, separators=(",", ":")) != raw:
        raise ContractError(label + " canonical JSON")
    return value


def _tracker_ids(value, label):
    ids = [item.strip() for item in (value or "").split(",") if item.strip()]
    if not ids or len(ids) != len(set(ids)):
        raise ContractError(label)
    return sorted(ids, key=lambda item: item.encode("utf-8"))


def _derive_post_closure_next(units, selected_id):
    states = {unit_id: fields.get("state") for unit_id, fields in units.items()}
    states[selected_id] = "Complete"
    candidates = []
    for unit_id, fields in units.items():
        if unit_id == selected_id:
            continue
        state = states[unit_id]
        if state in {"Claimed", "In Progress"}:
            candidates.append(unit_id)
            continue
        if state != "Ready":
            continue
        dependencies = [
            item.strip() for item in fields.get("dependency", "none").split(",")
            if item.strip() and item.strip() != "none"
        ]
        if all(dependency in states and states[dependency] == "Complete" for dependency in dependencies):
            candidates.append(unit_id)
    candidates.sort(key=lambda item: item.encode("utf-8"))
    if len(candidates) > 1:
        raise ContractError("grounding ambiguous post-closure next")
    return candidates[0] if candidates else None


def _gate_contract(gate_id, fields, selected_id, manifest_files):
    owners = _tracker_ids(fields.get("owners"), "grounding gate owners")
    if selected_id not in owners:
        raise ContractError("grounding selected gate owner reciprocity")
    command = fields.get("command")
    if not command:
        raise ContractError("grounding selected gate command")
    if fields.get("status") != "passed" and not fields.get("recovery_condition"):
        raise ContractError("grounding selected gate recovery")
    inputs = _tracker_json(fields, "inputs_json", "grounding gate inputs")
    if not isinstance(inputs, list):
        raise ContractError("grounding gate inputs")
    digests = {path: entry["sha256"] for path, entry in manifest_files.items()}
    expected_fingerprint = gate_input_fingerprint(inputs, digests)
    if fields.get("input_fingerprint") != expected_fingerprint:
        raise ContractError("grounding gate input fingerprint")
    passed_evidence = fields.get("passed_evidence", "none")
    if fields.get("status") == "passed":
        _safe_path(passed_evidence, "grounding passed gate evidence")
        if passed_evidence not in manifest_files:
            raise ContractError("grounding passed gate evidence binding")
    elif passed_evidence != "none":
        raise ContractError("grounding non-passed gate evidence")
    return {
        "owners": owners,
        "command": command,
        "inputs": inputs,
        "input_fingerprint": expected_fingerprint,
        "passed_evidence": passed_evidence,
    }


def validate_generic_handoff_grounding(case_id, handoff, fixture_manifest, grounding_sources):
    if case_id not in GENERIC_PROFILES:
        raise ContractError("generic grounding case")
    git, manifest_files = _manifest_files(fixture_manifest, case_id)
    tracker = _grounding_tracker(grounding_sources, case_id, manifest_files)
    units = _tracker_registry(tracker, "Unit registry", "Required gate registry")
    gates = _tracker_registry(tracker, "Required gate registry", "Decisions and blockers")
    for unit_id, fields in units.items():
        if not fields.get("gate_refs"):
            continue
        for gate_id in _tracker_ids(fields["gate_refs"], "grounding unit gate refs"):
            if gate_id not in gates or unit_id not in _tracker_ids(
                gates[gate_id].get("owners"), "grounding gate owners"
            ):
                raise ContractError("grounding reciprocal Gate topology")
    for gate_id, fields in gates.items():
        for unit_id in _tracker_ids(fields.get("owners"), "grounding gate owners"):
            if unit_id not in units or gate_id not in _tracker_ids(
                units[unit_id].get("gate_refs"), "grounding unit gate refs"
            ):
                raise ContractError("grounding reciprocal Gate topology")
    selected = [unit_id for unit_id, fields in units.items() if fields.get("selected") == "true"]
    if len(selected) != 1:
        raise ContractError("grounding selected unit")
    selected_id = selected[0]
    selected_fields = units[selected_id]
    owner = selected_fields.get("owner")
    gate_ids = _tracker_ids(selected_fields.get("gate_refs"), "grounding selected gate refs")
    if not owner or not gate_ids or any(gate_id not in gates for gate_id in gate_ids):
        raise ContractError("grounding selected topology")
    unit_counts = {state: 0 for state in UNIT_STATES}
    for fields in units.values():
        state = fields.get("state")
        if state not in unit_counts:
            raise ContractError("grounding unit state")
        unit_counts[state] += 1
    gate_counts = {state: 0 for state in GATE_STATES}
    for fields in gates.values():
        state = fields.get("status")
        if fields.get("required") not in {"true", "false"} or state not in gate_counts:
            raise ContractError("grounding gate state")
        if fields["required"] == "true":
            gate_counts[state] += 1
    open_units = []
    blockers = []
    for unit_id, fields in units.items():
        if fields["state"] == "Complete":
            continue
        open_units.append({
            "id": unit_id,
            "state": fields["state"],
            "claim": fields.get("claim", "none"),
            "dependency": fields.get("dependency", "none"),
            "next": fields.get("next_convergence_condition", ""),
        })
        if "blocker" in fields:
            blockers.append({
                "id": fields.get("blocker_id", unit_id + "-blocker"),
                "owner": fields.get("blocker_owner", fields.get("owner", "unassigned")),
                "detail": fields["blocker"],
                "recovery": fields.get("recovery_condition", ""),
            })
    open_gates = []
    for gate_id, fields in gates.items():
        if fields["required"] != "true" or fields["status"] == "passed":
            continue
        command = fields.get("command") or fields.get("recovery_condition")
        if not command:
            raise ContractError("grounding gate recovery")
        open_gates.append({
            "id": gate_id,
            "state": fields["status"],
            "command_or_recovery": command,
        })
    for group in (open_units, open_gates, blockers):
        group.sort(key=lambda entry: entry["id"].encode("utf-8"))
    inventory = {"units": open_units, "gates": open_gates, "blockers": blockers}
    required_paths = {
        ".project/development/task_plan.md", "AGENTS.md",
        selected_fields.get("authoritative_design", ""), owner,
        selected_fields.get("nearest_test", ""),
    }
    if GENERIC_PROFILES[case_id] == "High-risk":
        required_paths.add(selected_fields.get("package_surface", ""))
    if "" in required_paths:
        raise ContractError("grounding required evidence definition")
    gate_contracts = {
        gate_id: _gate_contract(gate_id, gates[gate_id], selected_id, manifest_files)
        for gate_id in gate_ids
    }
    required_gate_inputs = {owner, selected_fields["nearest_test"]}
    if any(not required_gate_inputs.issubset(contract["inputs"]) for contract in gate_contracts.values()):
        raise ContractError("grounding selected Gate input coverage")
    if any(gates[gate_id].get("required") != "true" for gate_id in gate_ids):
        raise ContractError("grounding selected optional gate")
    for contract in gate_contracts.values():
        if contract["passed_evidence"] != "none":
            required_paths.add(contract["passed_evidence"])
    role_by_path = {
        ".project/development/task_plan.md": "tracker",
        "AGENTS.md": "authority",
        selected_fields.get("authoritative_design", ""): "design",
        owner: "owner",
        selected_fields.get("nearest_test", ""): "regression",
        selected_fields.get("package_surface", ""): "integration",
    }
    for contract in gate_contracts.values():
        if contract["passed_evidence"] != "none":
            role_by_path[contract["passed_evidence"]] = "gate-evidence"
    role_by_path[owner] = "owner"
    role_by_path[selected_fields.get("nearest_test", "")] = "regression"
    expected_ledger = [
        {"id": path, "role": role_by_path[path], "sha256": manifest_files[path]["sha256"]}
        for path in sorted(required_paths, key=lambda item: item.encode("utf-8"))
        if path in manifest_files
    ]
    if len(expected_ledger) != len(required_paths):
        raise ContractError("grounding required evidence binding")
    selected_gates = [{"id": gate_id, "state": gates[gate_id]["status"]} for gate_id in gate_ids]
    selected_evidence = {
        "unit": selected_id,
        "owner": owner,
        "gates": gate_ids,
        "evidence": [entry["id"] for entry in expected_ledger],
        "ledger_sha256": canonical_ledger_sha256(expected_ledger),
    }
    try:
        expected_fingerprint = fingerprint({
            "branch": git["branch"],
            "head": git["head"],
            "status": bytes.fromhex(git["status_hex"]),
            "files": [
                {"path": entry["id"], "sha256": entry["sha256"]}
                for entry in expected_ledger
            ],
            "tracker_revision": _require_single_prefix(tracker, "tracker_revision: "),
            "selected_evidence": selected_evidence,
        })
    except FingerprintError as error:
        raise ContractError("generic grounding fingerprint: " + str(error)) from error
    expected = {
        "profile": GENERIC_PROFILES[case_id],
        "selected": selected_id,
        "snapshot": {
            "tracker_revision": _require_single_prefix(tracker, "tracker_revision: "),
            "branch": git["branch"],
            "head": git["head"],
            "status_fingerprint": expected_fingerprint,
        },
        "unit_counts": unit_counts,
        "gate_counts": gate_counts,
        "inventory": inventory,
        "selected_gates": selected_gates,
        "repository": ".",
        "owner_boundary": sorted(
            {owner, selected_fields["nearest_test"]}, key=lambda item: item.encode("utf-8")
        ),
        "authoritative_inputs": [entry["id"] for entry in expected_ledger],
        "selection_basis": _require_single_prefix(tracker, "selection_decision: "),
        "dependency_evidence": selected_fields.get("dependency", "none"),
        "trace_requirements": [{
            "requirement": selected_fields.get("goal", ""),
            "owner": owner,
            "test": selected_fields["nearest_test"],
            "gates": gate_ids,
            "evidence": selected_fields["nearest_test"],
        }],
        "post_closure_next": _derive_post_closure_next(units, selected_id),
        "evidence_ledger": evidence_ledger_projection(expected_ledger),
        "gate_contracts": gate_contracts,
    }
    validated = validate_handoff_grounding(handoff, expected)
    if GENERIC_PROFILES[case_id] == "High-risk":
        for field in ("affected_consumer", "compatibility_gate", "rollback_evidence"):
            value = _require_single_prefix(tracker, field + ": ")
            if value not in handoff["body"]:
                raise ContractError("ungrounded High-risk " + field.replace("_", " "))
    return validated


def validate_forward_case(case_id, response):
    if case_id not in EXECUTABLE_FORWARD_CASES | NON_EXECUTABLE_FORWARD_CASES:
        raise ContractError("unknown forward-eval case")
    if not isinstance(response, str):
        raise ContractError("forward-eval response must be text")
    lower = response.lower()
    handoff = None
    if case_id in EXECUTABLE_FORWARD_CASES:
        handoff = parse_handoff(response)
        for marker in ("Selection basis", "Current executable unit", "Post-closure next unit"):
            if marker not in response:
                raise ContractError("execution contract marker " + marker)
    elif re.search(r"(?m)^(?:`{3,}|~{3,})", response):
        raise ContractError("non-executable case returned an instruction fence")
    if handoff is None and any(
        marker in lower for marker in ("evaluator", "snapshot/skill/", ".code-review-graph")
    ):
        raise ContractError("non-executable response echoed evaluator instructions")

    if case_id == "chinese-mixed-state-first-delivery":
        if not _has_chinese_status(response):
            raise ContractError("Chinese mixed-state convergence")
    elif case_id == "english-localization":
        if re.search(r"[\u3400-\u9fff]", response):
            raise ContractError("English mixed-state convergence")
    elif case_id == "complete-plan" and not ("收敛" in response or "converged" in lower):
        raise ContractError("complete classification")
    elif case_id == "insufficient-information" and not ("信息不足" in response or "insufficient" in lower):
        raise ContractError("insufficient classification")
    elif case_id == "generic-blocker" and not (
        "Blocked" in response and ("阻塞" in response or "block" in lower)
    ):
        raise ContractError("generic blocker classification")
    elif case_id == "light-documentation" and (
        handoff["profile"] != "Light"
        or "docs/design.md" not in response
        or "npm test" not in response
        or "implementation" in handoff["operations"]
        or handoff["operations"] != ["test", "tracker", "observe"]
        or handoff["steps"][0]["Command"] != "npm test && git diff --check"
    ):
        raise ContractError("Light documentation contract")
    elif case_id == "high-risk-public-consumer" and (
        handoff["profile"] != "High-risk"
        or not any(marker in lower for marker in ("consumer", "compatibility", "rollback"))
    ):
        raise ContractError("High-risk consumer contract")
    elif case_id == "correct-prerequisite-blocker" and (
        "B1" not in response or not any(marker in lower for marker in ("recovery", "approval", "block"))
    ):
        raise ContractError("correct prerequisite blocker")
    elif case_id == "migration-permission-release-blocker":
        localized_markers = (
            "migration" in lower or "迁移" in response,
            "permission" in lower or "权限" in response,
            "release" in lower or "发布" in response,
        )
        if "High-risk" not in response or not all(localized_markers):
            raise ContractError("migration permission release blocker")
    elif case_id == "tracker-none-projection" and not all(
        marker in lower for marker in ("tracker: none", "read-only", "mutation")
    ):
        raise ContractError("tracker none projection")
    elif case_id == "tracker-path-escape" and (
        not any(marker in lower for marker in ("symlink", "symbolic link", "escape", "containment"))
        and not any(marker in response for marker in ("符号链接", "逃逸"))
    ):
        raise ContractError("tracker escape classification")
    elif case_id == "concurrency-conflict" and (
        not any(marker in lower for marker in ("lock", "conflict", "ownership"))
        and not any(marker in response for marker in ("锁", "冲突"))
    ):
        raise ContractError("concurrency classification")
    elif case_id == "snapshot-double-drift":
        normalized = re.sub(r"[-_]+", " ", lower)
        has_recompute = re.search(r"\brecomput(?:e|ed|ation|ing)?\b|重算|重新计算", normalized)
        has_single_bound = re.search(
            r"\b(?:one|single|once|only|one\s+time)\b|一次(?:性)?|唯一", normalized
        )
        recompute_once = has_recompute is not None and has_single_bound is not None
        has_drift = re.search(r"\bdrift(?:ed|ing)?\b|漂移", normalized)
        has_second_relation = re.search(r"\b(?:second|again)\b|第二次|再次", normalized)
        post_recompute_drift = re.search(
            r"(?:drift(?:ed|ing)?\b.{0,64}\bafter\b.{0,64}\brecomput|post\s+recomput.{0,64}\bdrift)",
            normalized,
        )
        second_drift = has_drift is not None and (
            has_second_relation is not None or post_recompute_drift is not None
        )
        blocked = "block" in lower or "阻塞" in response
        if "status-fingerprint-v1" not in lower or not recompute_once or not second_drift or not blocked:
            raise ContractError("snapshot double drift classification")
    elif case_id == "plugin-prerequisites" and (
        "plugin" not in lower
        or not any(marker in lower for marker in ("prerequisite", "authenticated", "headless"))
    ):
        raise ContractError("plugin prerequisite classification")
    elif case_id == "git-permission-split":
        expected = {
            "Local commit": "authorized",
            "Change version": "not authorized",
            "Tag": "not authorized",
            "Push/release": "not authorized",
        }
        if any(handoff["permission_states"][key] != value for key, value in expected.items()):
            raise ContractError("Git permission split")
    if case_id in {"chinese-mixed-state-first-delivery", "english-localization"}:
        expected_units = {"U2": "In Progress", "U3": "Ready", "U4": "Blocked"}
        expected_gates = {"G2": "pending", "G3": "unknown-definition"}
        expected_unit_counts = {
            "Complete": 1, "In Progress": 1, "Claimed": 0,
            "Ready": 1, "Blocked": 1, "Failed": 0,
        }
        expected_gate_counts = {
            "passed": 1, "pending": 1, "failed": 0,
            "unknown-definition": 1, "conflicting": 0,
        }
        actual_units = {entry["id"]: entry["state"] for entry in handoff["inventory"]["units"]}
        actual_gates = {entry["id"]: entry["state"] for entry in handoff["inventory"]["gates"]}
        if (
            handoff["selected"] != "U2"
            or handoff["unit_counts"] != expected_unit_counts
            or handoff["gate_counts"] != expected_gate_counts
            or actual_units != expected_units
            or actual_gates != expected_gates
        ):
            raise ContractError("mixed-state facts")
    return handoff


def validate_transition_protocol(
    receipts,
    *,
    unit,
    owner,
    initial_state,
    initial_revision,
    final_revision,
    required_gates,
    declared_next,
    expected_next,
):
    state = initial_state
    revision = initial_revision
    if not isinstance(required_gates, dict) or any(
        not gate_id or state not in GATE_STATES for gate_id, state in required_gates.items()
    ):
        raise ContractError("required gate topology")
    gate_states = dict(required_gates)
    observed = []
    parsed_receipts = []
    for value in receipts:
        receipt = parse_receipt(value) if isinstance(value, str) else value
        parsed_receipts.append(receipt)
        if receipt.unit != unit or receipt.owner != owner:
            raise ContractError("receipt unit or owner conflict")
        if receipt.revision_before != revision:
            raise ContractError("stale tracker revision")
        for before, after in receipt.transitions:
            if before != state:
                raise ContractError("illegal unit transition")
            state = after
            observed.append(before + "->" + after)
        if receipt.gate is not None:
            gate_id, before, after = receipt.gate
            if gate_id not in gate_states or before != gate_states[gate_id]:
                raise ContractError("illegal gate transition")
            if (before == "failed" or after == "failed") and not (receipt.recovery or "").strip():
                raise ContractError("failed gate transition lacks recovery")
            gate_states[gate_id] = after
            if after == "failed" and state not in {"Failed", "Blocked"}:
                raise ContractError("failed gate and unit state differ")
            if before == "failed" and after == "pending" and state != "In Progress":
                raise ContractError("gate recovery and unit state differ")
        revision = receipt.revision_after
    if revision != final_revision or revision == initial_revision:
        raise ContractError("stale final tracker revision")
    if state != "Complete" or any(value != "passed" for value in gate_states.values()):
        raise ContractError("closure state")
    if declared_next != expected_next:
        raise ContractError("post-closure next mismatch")
    return {
        "state": state,
        "revision": revision,
        "gates": gate_states,
        "transitions": observed,
        "receipts": parsed_receipts,
    }


def reconcile_expectations(expectations, receipts, *, initial_revision):
    expected_changes = []
    expected_gates = []
    prior_state_change = False
    for expectation in expectations:
        changes_state = bool(expectation.transitions) or expectation.gate is not None
        expected_source = "observed-prior" if prior_state_change else initial_revision
        if expectation.from_revision != expected_source:
            raise ContractError("expected transition revision chain")
        prior_state_change = prior_state_change or changes_state
        expected_changes.extend(expectation.transitions)
        if expectation.gate is not None:
            expected_gates.append(expectation.gate)
    parsed = [parse_receipt(value) if isinstance(value, str) else value for value in receipts]
    expected_units = {expectation.unit for expectation in expectations}
    expected_owners = {expectation.owner for expectation in expectations}
    if len(expected_units) != 1 or len(expected_owners) != 1:
        raise ContractError("generated unit or owner conflict")
    if any(receipt.unit not in expected_units or receipt.owner not in expected_owners for receipt in parsed):
        raise ContractError("generated and observed unit or owner differ")
    observed_changes = [transition for receipt in parsed for transition in receipt.transitions]
    observed_gates = [receipt.gate for receipt in parsed if receipt.gate is not None]
    if expected_changes != observed_changes:
        raise ContractError("generated and observed unit transitions differ")
    if expected_gates != observed_gates:
        raise ContractError("generated and observed gate transitions differ")
    expected_boundaries = [
        expectation for expectation in expectations
        if expectation.transitions or expectation.gate is not None
    ]
    observed_boundaries = [
        receipt for receipt in parsed
        if receipt.transitions or receipt.gate is not None
    ]
    if len(expected_boundaries) != len(observed_boundaries):
        raise ContractError("generated and observed step boundaries differ")
    for expectation, receipt in zip(expected_boundaries, observed_boundaries):
        if expectation.transitions != receipt.transitions or expectation.gate != receipt.gate:
            raise ContractError("generated and observed step boundary differs")
        if expectation.evidence_path is None or expectation.evidence_path != receipt.evidence:
            raise ContractError("generated and observed receipt evidence differs")
    if parsed and parsed[0].revision_before != initial_revision:
        raise ContractError("generated and observed initial revisions differ")
    return {"transitions": observed_changes, "gates": observed_gates}
