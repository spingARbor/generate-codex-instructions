#!/usr/bin/env python3
"""Compute status-fingerprint-v1 from bounded repository evidence."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import subprocess


class FingerprintError(ValueError):
    pass


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


def _digest(value, label):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise FingerprintError(label + " digest")
    return value


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _ledger(value):
    if not isinstance(value, list) or not value:
        raise FingerprintError("evidence ledger")
    previous = None
    seen = set()
    result = []
    for entry in value:
        if not isinstance(entry, dict) or tuple(entry) != ("id", "role", "sha256"):
            raise FingerprintError("evidence ledger schema")
        identifier = _path(entry["id"])
        if identifier in seen or (previous is not None and identifier.encode("utf-8") <= previous):
            raise FingerprintError("evidence ledger ordering")
        if not isinstance(entry["role"], str) or not entry["role"]:
            raise FingerprintError("evidence ledger role")
        seen.add(identifier)
        previous = identifier.encode("utf-8")
        result.append({"id": identifier, "role": entry["role"], "sha256": _digest(entry["sha256"], "ledger")})
    return result


def _regular_input(root, relative):
    path = root / relative
    try:
        metadata = path.lstat()
        physical = path.resolve(strict=True)
    except OSError as error:
        raise FingerprintError("missing evidence input: " + relative) from error
    try:
        physical.relative_to(root)
    except ValueError as error:
        raise FingerprintError("evidence input escapes repository: " + relative) from error
    if (
        not stat.S_ISREG(metadata.st_mode)
        or path.is_symlink()
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
    ):
        raise FingerprintError("unsafe evidence input: " + relative)
    return path.read_bytes()


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
    if not isinstance(tracker_revision, str) or not tracker_revision or "\x00" in tracker_revision:
        raise FingerprintError("tracker revision")
    if not isinstance(unit, str) or not unit or "\x00" in unit:
        raise FingerprintError("selected unit")
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


def gate_input_fingerprint(paths, file_digests):
    records = [{"path": path, "sha256": file_digests[path]} for path in paths]
    return hashlib.sha256((_canonical_json(records) + "\n").encode("utf-8")).hexdigest()


def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tracker-revision", required=True)
    parser.add_argument("--unit", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--gate", action="append", default=[])
    parser.add_argument("--ledger-json", required=True)
    parser.add_argument("--gate-inputs-json")
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    try:
        ledger = _ledger(json.loads(arguments.ledger_json))
        gates = arguments.gate
        if not gates or gates != sorted(gates, key=lambda value: value.encode("utf-8")) or len(gates) != len(set(gates)):
            raise FingerprintError("Gate ordering")
        state = build_state(
            Path(arguments.repository), arguments.tracker_revision,
            arguments.unit, arguments.owner, gates, ledger,
        )
        result = {
            "status_fingerprint": fingerprint(state),
            "ledger_sha256": state["selected_evidence"]["ledger_sha256"],
            "evidence_ledger": {
                "sha256": state["selected_evidence"]["ledger_sha256"],
                "rows": [{"id": entry["id"], "role": entry["role"]} for entry in ledger],
            },
        }
        if arguments.gate_inputs_json is not None:
            gate_inputs = json.loads(arguments.gate_inputs_json)
            if (
                not isinstance(gate_inputs, list)
                or not gate_inputs
                or gate_inputs != sorted(gate_inputs, key=lambda value: value.encode("utf-8"))
                or len(gate_inputs) != len(set(gate_inputs))
                or any(_path(value) not in state["selected_evidence"]["evidence"] for value in gate_inputs)
            ):
                raise FingerprintError("Gate inputs")
            result["gate_input_fingerprint"] = gate_input_fingerprint(
                gate_inputs, {entry["path"]: entry["sha256"] for entry in state["files"]}
            )
    except (FingerprintError, json.JSONDecodeError, OSError) as error:
        raise SystemExit("error: " + str(error)) from error
    print(_canonical_json(result))


if __name__ == "__main__":
    main()
