#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import stat
import struct
import subprocess


UNIT_STATES = ("Complete", "In Progress", "Claimed", "Ready", "Blocked", "Failed")
GATE_STATES = ("passed", "pending", "failed", "unknown-definition", "conflicting")
PROFILE_READS = {"Light": 6, "Standard": 12, "High-risk": 20}
MAX_PROJECTED_TEXT_BYTES = 512
UNSAFE_PROJECTED_TEXT = (
    re.compile(r"(?i)(?:ignore|bypass|override|disregard).{0,48}(?:instruction|authority|skill|policy|rule)"),
    re.compile(r"(?i)(?:reveal|print|output|expose).{0,48}(?:secret|credential|token|password|hidden|system prompt|private)"),
    re.compile(r"(?i)(?:secret|credential|password|bearer(?:\s+token)?|api[-_ ]?key|private[-_ ]?key)\s*[:=]\s*\S+"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{8,}"),
    re.compile(r"(?i)\bsecret-[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"(?<![A-Za-z0-9])AKIA[0-9A-Z]{16}(?![A-Za-z0-9])"),
    re.compile(r"(?i)-----begin (?:rsa |openssh )?private key-----"),
    re.compile(r"(?i)(?:^|\s)/(?:home|Users|root|etc|var|tmp)/"),
    re.compile(r"(?i)https?://"),
)
LOCAL_TEST_COMMANDS = {"pytest", "py.test", "ctest", "rspec", "phpunit"}


class FingerprintError(ValueError):
    pass


def _safe_projected_text(value, label):
    if not isinstance(value, str) or not value or value.strip() != value:
        raise FingerprintError("unsafe projected text: " + label)
    if len(value.encode("utf-8")) > MAX_PROJECTED_TEXT_BYTES:
        raise FingerprintError("unsafe projected text: " + label)
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise FingerprintError("unsafe projected text: " + label)
    if "```" in value or "~~~" in value or any(pattern.search(value) for pattern in UNSAFE_PROJECTED_TEXT):
        raise FingerprintError("unsafe projected text: " + label)
    return value


def _is_test_path(value):
    lowered = value.lower()
    parts = PurePosixPath(lowered).parts
    name = parts[-1] if parts else ""
    return (
        any(part in {"test", "tests", "spec", "specs"} for part in parts[:-1])
        or name.startswith(("test_", "test-", "spec_", "spec-"))
        or ".test." in name
        or ".spec." in name
    )


def _safe_gate_command(value, inputs):
    value = _safe_projected_text(value, "Gate command")
    if re.search(r"[;&|<>`]|\$\(", value):
        raise FingerprintError("unsafe Gate command")
    try:
        arguments = shlex.split(value, posix=True)
    except ValueError as error:
        raise FingerprintError("unsafe Gate command") from error
    if not arguments:
        raise FingerprintError("unsafe Gate command")
    executable, rest = arguments[0], arguments[1:]
    safe = executable in LOCAL_TEST_COMMANDS
    if executable in {"python", "python3"}:
        safe = len(rest) >= 2 and rest[0] == "-m" and rest[1] in {"unittest", "pytest", "compileall"}
        safe = safe or (bool(rest) and rest[0] in inputs and _is_test_path(rest[0]))
    elif executable == "node":
        safe = bool(rest) and rest[0] == "--test"
    elif executable in {"npm", "pnpm", "yarn", "bun"}:
        if rest and rest[0] == "test":
            safe = True
        elif len(rest) >= 2 and rest[0] == "run":
            safe = re.search(r"(?i)(?:test|check|lint|verify|type)", rest[1]) is not None
    elif executable == "go":
        safe = bool(rest) and rest[0] in {"test", "vet"}
    elif executable == "cargo":
        safe = bool(rest) and rest[0] in {"test", "check", "clippy"}
    elif executable in {"make", "dotnet", "mvn", "mvnw", "gradle", "gradlew", "rake"}:
        safe = bool(rest) and any(token in {"test", "tests", "check", "verify", "lint"} for token in rest)
    elif executable in {"sh", "bash", "dash"}:
        safe = bool(rest) and rest[0] in inputs and _is_test_path(rest[0])
    elif executable == "busybox":
        safe = len(rest) >= 2 and rest[0] == "sh" and rest[1] in inputs and _is_test_path(rest[1])
    elif executable in inputs and _is_test_path(executable):
        safe = True
    if not safe:
        raise FingerprintError("unsafe Gate command")
    return value


def _field(value):
    return struct.pack(">Q", len(value)) + value


def _path(value):
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        raise FingerprintError("path must be repository-relative POSIX text")
    parsed = PurePosixPath(value)
    if parsed.as_posix() != value or any(part in ("", ".", "..") for part in parsed.parts):
        raise FingerprintError("path is not normalized")
    if parsed.parts[0] == ".git" or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise FingerprintError("path is unsafe")
    return value


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _tracker_registry(text, heading, next_heading):
    match = re.search(
        r"(?ms)^## " + re.escape(heading) + r"\n(.*?)(?=^## "
        + re.escape(next_heading) + r"\n|\Z)",
        text,
    )
    if match is None:
        raise FingerprintError("tracker registry " + heading)
    entries = {}
    for section in re.finditer(
        r"(?ms)^### ([A-Za-z0-9._-]+)\n(.*?)(?=^### |\Z)", match.group(1)
    ):
        fields = {}
        for key, value in re.findall(r"(?m)^([A-Za-z0-9_]+): (.+)$", section.group(2)):
            if key in fields:
                raise FingerprintError("duplicate tracker field")
            fields[key] = value
        identifier = section.group(1)
        if identifier in entries:
            raise FingerprintError("duplicate tracker id")
        entries[identifier] = fields
    if not entries:
        raise FingerprintError("empty tracker registry")
    return entries


def _tracker_ids(value, label):
    identifiers = [item.strip() for item in (value or "").split(",") if item.strip()]
    if not identifiers or len(identifiers) != len(set(identifiers)):
        raise FingerprintError(label)
    return sorted(identifiers, key=lambda item: item.encode("utf-8"))


def _root_value(text, key):
    values = re.findall(r"(?m)^" + re.escape(key) + r": (.+)$", text)
    if len(values) != 1:
        raise FingerprintError("tracker field " + key)
    return values[0]


def _tracker_json_paths(fields, key, label):
    try:
        values = json.loads(fields.get(key, ""))
    except json.JSONDecodeError as error:
        raise FingerprintError(label) from error
    if (
        not isinstance(values, list) or not values
        or any(not isinstance(value, str) for value in values)
    ):
        raise FingerprintError(label)
    paths = [_path(value) for value in values]
    if paths != sorted(paths, key=lambda value: value.encode("utf-8")) or len(paths) != len(set(paths)):
        raise FingerprintError(label)
    return paths


def _applicable_authorities(root, paths):
    candidates = {"AGENTS.md"}
    for path in paths:
        parts = path.split("/")
        candidates.update("/".join(parts[:depth] + ["AGENTS.md"]) for depth in range(1, len(parts)))
    authorities = []
    for candidate in sorted(candidates, key=lambda value: value.encode("utf-8")):
        absolute = root / candidate
        if os.path.lexists(absolute):
            _regular_input(root, candidate)
            authorities.append(candidate)
    return authorities


def tracker_projection(raw, tracker_path, selected_id, profile, root):
    try:
        text = raw.decode("utf-8")
    except UnicodeError as error:
        raise FingerprintError("tracker UTF-8") from error
    tracker_revision = _root_value(text, "tracker_revision")
    if re.fullmatch(r"[A-Za-z0-9._-]{1,128}", tracker_revision) is None:
        raise FingerprintError("tracker revision")
    units = _tracker_registry(text, "Unit registry", "Required gate registry")
    gates = _tracker_registry(text, "Required gate registry", "Decisions and blockers")
    if selected_id not in units:
        raise FingerprintError("selected unit absent from tracker")
    for unit_id, fields in units.items():
        if not fields.get("gate_refs"):
            continue
        for gate_id in _tracker_ids(fields["gate_refs"], "unit Gate refs"):
            if gate_id not in gates or unit_id not in _tracker_ids(gates[gate_id].get("owners"), "Gate owners"):
                raise FingerprintError("reciprocal Gate topology")
    for gate_id, fields in gates.items():
        for unit_id in _tracker_ids(fields.get("owners"), "Gate owners"):
            if unit_id not in units or gate_id not in _tracker_ids(units[unit_id].get("gate_refs"), "unit Gate refs"):
                raise FingerprintError("reciprocal Gate topology")
    selected = units[selected_id]
    gate_ids = _tracker_ids(selected.get("gate_refs"), "selected Gate refs")
    if any(gate_id not in gates for gate_id in gate_ids):
        raise FingerprintError("selected Gate mismatch")
    owner = _path(selected.get("owner"))
    nearest_test = _path(selected.get("nearest_test"))
    design = _path(selected.get("authoritative_design"))
    gate_inputs = sorted({owner, nearest_test}, key=lambda value: value.encode("utf-8"))
    required_paths = {tracker_path, owner, nearest_test, design}
    authorities = _applicable_authorities(root, (owner, nearest_test))
    required_paths.update(authorities)
    integration = selected.get("package_surface")
    if profile == "High-risk":
        required_paths.add(_path(integration))
    passed_evidence = []
    for gate_id in gate_ids:
        fields = gates[gate_id]
        if fields.get("required") != "true":
            raise FingerprintError("selected Gate is not required")
        if not fields.get("command") or (
            fields.get("status") != "passed" and not fields.get("recovery_condition")
        ):
            raise FingerprintError("Gate command/recovery")
        if _tracker_json_paths(fields, "inputs_json", "Gate inputs") != gate_inputs:
            raise FingerprintError("Gate input coverage")
        _safe_gate_command(fields["command"], gate_inputs)
        if fields.get("recovery_condition"):
            _safe_projected_text(fields["recovery_condition"], "Gate recovery")
        digests = {
            path: hashlib.sha256(_regular_input(root, path)).hexdigest()
            for path in gate_inputs
        }
        records = [{"path": path, "sha256": digests[path]} for path in gate_inputs]
        expected_input = hashlib.sha256((_canonical_json(records) + "\n").encode("utf-8")).hexdigest()
        if fields.get("input_fingerprint") != expected_input:
            raise FingerprintError("Gate input fingerprint")
        evidence = fields.get("passed_evidence", "none")
        if fields.get("status") == "passed":
            passed_evidence.append(_path(evidence))
            required_paths.add(evidence)
        elif evidence != "none":
            raise FingerprintError("non-passed Gate evidence")
    role_by_path = {tracker_path: "tracker"}
    role_by_path.update({path: "authority" for path in authorities})
    role_by_path[design] = "design"
    if profile == "High-risk":
        role_by_path[integration] = "integration"
    role_by_path.update({path: "gate-evidence" for path in passed_evidence})
    role_by_path[owner] = "owner"
    role_by_path[nearest_test] = "regression"
    evidence_specs = [
        {"id": path, "role": role_by_path[path]}
        for path in sorted(required_paths, key=lambda value: value.encode("utf-8"))
    ]
    unit_counts = {state: 0 for state in UNIT_STATES}
    for fields in units.values():
        state = fields.get("state")
        if state not in unit_counts:
            raise FingerprintError("Unit state")
        unit_counts[state] += 1
    gate_counts = {state: 0 for state in GATE_STATES}
    for fields in gates.values():
        state = fields.get("status")
        if fields.get("required") not in ("true", "false") or state not in gate_counts:
            raise FingerprintError("Gate state")
        if fields["required"] == "true":
            gate_counts[state] += 1
    open_units = []
    blockers = []
    for unit_id, fields in units.items():
        if fields["state"] == "Complete":
            continue
        claim = fields.get("claim", "none")
        if re.fullmatch(r"[A-Za-z0-9._@/-]{1,128}", claim) is None:
            raise FingerprintError("unsafe projected text: Unit claim")
        dependency = fields.get("dependency", "none")
        if dependency != "none":
            dependency = ",".join(_tracker_ids(dependency, "Unit dependency"))
        open_units.append({
            "id": unit_id,
            "state": fields["state"],
            "claim": claim,
            "dependency": dependency,
            "next": _safe_projected_text(
                fields.get("next_convergence_condition", ""), "Unit next condition"
            ),
        })
        if "blocker" in fields:
            blockers.append({
                "id": fields.get("blocker_id", unit_id + "-blocker"),
                "owner": _safe_projected_text(
                    fields.get("blocker_owner", fields.get("owner", "unassigned")),
                    "blocker owner",
                ),
                "detail": _safe_projected_text(fields["blocker"], "blocker detail"),
                "recovery": _safe_projected_text(
                    fields.get("recovery_condition", ""), "blocker recovery"
                ),
            })
    open_gates = []
    for gate_id, fields in gates.items():
        if fields["required"] != "true" or fields["status"] == "passed":
            continue
        command = fields.get("command") or fields.get("recovery_condition")
        if not command:
            raise FingerprintError("Gate command or recovery")
        if fields.get("command"):
            command = _safe_gate_command(
                command, _tracker_json_paths(fields, "inputs_json", "Gate inputs")
            )
        else:
            command = _safe_projected_text(command, "Gate recovery")
        open_gates.append({
            "id": gate_id,
            "state": fields["status"],
            "command_or_recovery": command,
        })
    for group in (open_units, open_gates, blockers):
        group.sort(key=lambda entry: entry["id"].encode("utf-8"))
    selected_required_gates = [
        {"id": gate_id, "state": gates[gate_id]["status"]} for gate_id in gate_ids
    ]
    commands = [gates[gate_id].get("command") for gate_id in gate_ids]
    shared_command = commands[0] if commands and len(set(commands)) == 1 and commands[0] else None
    pending = [gate_id for gate_id in gate_ids if gates[gate_id]["status"] == "pending"]
    light_protocol = None
    if (
        selected["state"] == "In Progress"
        and len(pending) == 1
        and all(gates[gate_id]["status"] in ("passed", "pending") for gate_id in gate_ids)
        and shared_command is not None
    ):
        receipt = (
            PurePosixPath(tracker_path).parent / "evidence" / (pending[0] + ".pass")
        ).as_posix()
        owner_boundary = sorted(
            [_path(selected.get("owner")), _path(selected.get("nearest_test"))],
            key=lambda item: item.encode("utf-8"),
        )
        tracker_boundary = sorted(
            [tracker_path, receipt], key=lambda item: item.encode("utf-8")
        )
        light_protocol = {
            "operations": ["test", "tracker", "observe"],
            "from_revision": [tracker_revision, tracker_revision, "observed-prior"],
            "test_command": shared_command + " && git diff --check",
            "transitions": ["none", "In Progress->Complete", "none"],
            "gates": ["none", pending[0] + ":pending->passed", "none"],
            "receipts": ["none", receipt, "none"],
            "boundaries": [
                owner_boundary,
                tracker_boundary,
                sorted(set(owner_boundary + tracker_boundary), key=lambda item: item.encode("utf-8")),
            ],
        }
        light_protocol["machine_lines"] = []
        artifacts = (
            "test-output,diff-check-output",
            ",".join(tracker_boundary),
            "final-status",
        )
        for index, operation in enumerate(light_protocol["operations"]):
            light_protocol["machine_lines"].append([
                "Command: " + (
                    light_protocol["test_command"] if operation == "test"
                    else "git status --porcelain=v1 --untracked-files=all" if operation == "observe"
                    else "none: persist the verified tracker closure"
                ),
                "Files/boundary: " + _canonical_json(light_protocol["boundaries"][index]),
                "Expected transition: unit=" + selected_id
                + "; owner=" + owner
                + "; transitions=" + light_protocol["transitions"][index]
                + "; from_revision=" + light_protocol["from_revision"][index]
                + "; gate=" + light_protocol["gates"][index],
                "Evidence required: receipt=" + light_protocol["receipts"][index]
                + "; artifacts=" + artifacts[index],
            ])
    return {
        "tracker_revision": tracker_revision,
        "unit_counts": unit_counts,
        "gate_counts": gate_counts,
        "selection_basis": _safe_projected_text(
            _root_value(text, "selection_decision"), "selection decision"
        ),
        "dependency_evidence": (
            "none" if selected.get("dependency", "none") == "none"
            else ",".join(_tracker_ids(selected.get("dependency"), "selected dependency"))
        ),
        "selected_required_gates": selected_required_gates,
        "open_inventory": {"units": open_units, "gates": open_gates, "blockers": blockers},
        "verified_owner_light_protocol": light_protocol,
        "safe_goal": _safe_projected_text(selected.get("goal", ""), "Unit goal"),
        "safe_invariants": _safe_projected_text(
            selected.get("invariants", ""), "Unit invariants"
        ),
        "safe_high_risk": (
            {
                key: _safe_projected_text(_root_value(text, key), key)
                for key in ("affected_consumer", "compatibility_gate", "rollback_evidence")
            }
            if profile == "High-risk" else None
        ),
        "_owner": owner,
        "_gate_ids": gate_ids,
        "_evidence_specs": evidence_specs,
    }


def _regular_input(root, relative):
    parts = PurePosixPath(relative).parts
    required_flags = ("O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW")
    if any(not hasattr(os, flag) for flag in required_flags):
        raise FingerprintError("safe evidence traversal is unavailable")
    directory_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    descriptors = []
    try:
        current = os.open(root, directory_flags)
        descriptors.append(current)
        for component in parts[:-1]:
            current = os.open(component, directory_flags, dir_fd=current)
            descriptors.append(current)
            metadata = os.fstat(current)
            if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid():
                raise FingerprintError("unsafe evidence input: " + relative)
        descriptor = os.open(parts[-1], file_flags, dir_fd=current)
        descriptors.append(descriptor)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != os.getuid()
        ):
            raise FingerprintError("unsafe evidence input: " + relative)
        chunks = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    except OSError as error:
        raise FingerprintError("unsafe evidence input: " + relative) from error
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _git(root, *arguments, text=False):
    try:
        return subprocess.check_output(("git", "-C", str(root), *arguments), text=text)
    except (OSError, subprocess.CalledProcessError) as error:
        raise FingerprintError("Git observation failed") from error


def build_state(root, tracker_revision, unit, owner, gates, ledger):
    try:
        metadata = root.lstat()
    except OSError as error:
        raise FingerprintError("repository root") from error
    if not stat.S_ISDIR(metadata.st_mode) or root.is_symlink() or metadata.st_uid != os.getuid():
        raise FingerprintError("repository root")
    root = root.resolve(strict=True)
    branch = _git(root, "branch", "--show-current", text=True).strip()
    head = _git(root, "rev-parse", "--verify", "HEAD", text=True).strip()
    if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head) is None:
        raise FingerprintError("HEAD")
    if not branch:
        branch = "DETACHED:" + head
    status_bytes = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    files = []
    for entry in ledger:
        raw = _regular_input(root, entry["id"])
        actual = hashlib.sha256(raw).hexdigest()
        if actual != entry["sha256"]:
            raise FingerprintError("ledger content drift: " + entry["id"])
        files.append({"path": entry["id"], "sha256": actual})
    selected = {
        "unit": unit,
        "owner": _path(owner),
        "gates": gates,
        "evidence": [entry["id"] for entry in ledger],
        "ledger_sha256": hashlib.sha256((_canonical_json(ledger) + "\n").encode("utf-8")).hexdigest(),
    }
    return {
        "branch": branch,
        "head": head,
        "status": status_bytes,
        "files": files,
        "tracker_revision": tracker_revision,
        "selected_evidence": selected,
    }


def fingerprint(state):
    file_payload = bytearray()
    for entry in state["files"]:
        file_payload.extend(_field(entry["path"].encode("utf-8")))
        file_payload.extend(_field(bytes.fromhex(entry["sha256"])))
    selected = (_canonical_json(state["selected_evidence"]) + "\n").encode("utf-8")
    fields = (
        b"status-fingerprint-v1",
        state["branch"].encode("utf-8"),
        state["head"].encode("ascii"),
        state["status"],
        bytes(file_payload),
        state["tracker_revision"].encode("utf-8"),
        selected,
    )
    return hashlib.sha256(b"".join(_field(value) for value in fields)).hexdigest()


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tracker", required=True)
    parser.add_argument("--unit", required=True)
    parser.add_argument("--profile", required=True, choices=tuple(PROFILE_READS))
    parser.add_argument("--emit", required=True, choices=("context", "preamble"))
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    try:
        root = Path(arguments.repository)
        tracker_path = _path(arguments.tracker)
        tracker_raw = _regular_input(root, tracker_path)
        projection = tracker_projection(
            tracker_raw, tracker_path, arguments.unit, arguments.profile, root,
        )
        owner = projection.pop("_owner")
        gates = projection.pop("_gate_ids")
        ledger = [{
            "id": entry["id"], "role": entry["role"],
            "sha256": hashlib.sha256(_regular_input(root, entry["id"])).hexdigest(),
        } for entry in projection.pop("_evidence_specs")]
        tracker_revision = projection["tracker_revision"]
        state = build_state(
            root, tracker_revision, arguments.unit, owner, gates, ledger,
        )
        status_digest = fingerprint(state)
        evidence_projection = {
            "sha256": state["selected_evidence"]["ledger_sha256"],
            "rows": [{"id": entry["id"], "role": entry["role"]} for entry in ledger],
        }
        tracker_entry = next(entry for entry in ledger if entry["id"] == tracker_path)
        if hashlib.sha256(tracker_raw).hexdigest() != tracker_entry["sha256"]:
            raise FingerprintError("tracker content drift")
        ceiling = PROFILE_READS[arguments.profile]
        used = len(ledger)
        if used > ceiling + ceiling // 2:
            raise FingerprintError("evidence-read ceiling")
        extension = max(0, used - ceiling)
        reason = "required-ledger-members" if extension else "none"
        preamble = [
            "Snapshot: tracker_revision=" + projection["tracker_revision"]
            + "; branch=" + state["branch"] + "; head=" + state["head"]
            + "; status_fingerprint=" + status_digest,
            "Unit counts: " + "; ".join(
                state_name + "=" + str(projection["unit_counts"][state_name])
                for state_name in UNIT_STATES
            ),
            "Gate counts: " + "; ".join(
                state_name + "=" + str(projection["gate_counts"][state_name])
                for state_name in GATE_STATES
            ),
            "Selection basis: " + projection["selection_basis"],
            "Current executable unit: " + arguments.unit
            + "; dependency_evidence=" + projection["dependency_evidence"],
            "Selected unit: " + arguments.unit,
            "Selected required gates: " + _canonical_json(projection["selected_required_gates"]),
            "Evidence reads: used=" + str(used) + "; ceiling=" + str(ceiling)
            + "; extension=" + str(extension) + "; reason=" + reason,
            "Evidence ledger: " + _canonical_json(evidence_projection),
            "Open inventory: " + _canonical_json(projection["open_inventory"]),
        ]
        context = {
            "owner": owner,
            "nearest_test": next(entry["id"] for entry in ledger if entry["role"] == "regression"),
            "gate_ids": gates,
            "passed_evidence": [entry["id"] for entry in ledger if entry["role"] == "gate-evidence"],
            "authoritative_inputs": [entry["id"] for entry in ledger],
            "verified_owner_light_protocol": projection["verified_owner_light_protocol"],
            "safe_goal": projection["safe_goal"],
            "safe_invariants": projection["safe_invariants"],
            "safe_high_risk": projection["safe_high_risk"],
        }
    except (FingerprintError, OSError, StopIteration) as error:
        raise SystemExit("error: " + str(error)) from error
    print("\n".join(preamble) if arguments.emit == "preamble" else _canonical_json(context))


if __name__ == "__main__":
    main()
