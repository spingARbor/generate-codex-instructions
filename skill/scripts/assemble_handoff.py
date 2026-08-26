#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


PREAMBLE_LABELS = (
    "Snapshot", "Unit counts", "Gate counts", "Selection basis",
    "Current executable unit", "Selected unit", "Selected required gates",
    "Evidence reads", "Evidence ledger", "Open inventory",
)


class AssemblyError(ValueError):
    pass


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _validated_lines(value, label):
    if not isinstance(value, bytes) or not value or b"\x00" in value or b"\r" in value:
        raise AssemblyError(label + " bytes")
    try:
        text = value.decode("utf-8")
    except UnicodeError as error:
        raise AssemblyError(label + " UTF-8") from error
    return text.splitlines(keepends=True)


def _validate_preamble(lines, label):
    if len(lines) != len(PREAMBLE_LABELS):
        raise AssemblyError(label + " line count")
    for line, expected in zip(lines, PREAMBLE_LABELS):
        if not line.startswith(expected + ": ") or not line.endswith("\n"):
            raise AssemblyError(label + " schema")


def assemble_executable(draft, trusted_preamble):
    draft_lines = _validated_lines(draft, "draft")
    trusted_lines = _validated_lines(trusted_preamble, "preamble")
    _validate_preamble(trusted_lines, "trusted preamble")
    if len(draft_lines) < 13 or not draft_lines[0].strip():
        raise AssemblyError("draft structure")
    opening = draft_lines[11].rstrip("\n")
    if re.fullmatch(r"(`{3,}|~{3,})text", opening) is None:
        raise AssemblyError("draft fence position")
    _validate_preamble(draft_lines[1:11], "draft preamble")
    final = draft_lines[0].encode("utf-8") + trusted_preamble + "".join(draft_lines[11:]).encode("utf-8")
    if not final.endswith(b"\n"):
        final += b"\n"
    _validated_lines(final, "final")
    return final


def assemble_passthrough(draft):
    _validated_lines(draft, "draft")
    return draft if draft.endswith(b"\n") else draft + b"\n"


def assembly_manifest(mode, draft, final, preamble, context, assembler_source):
    if mode not in {"executable", "passthrough"}:
        raise AssemblyError("assembly mode")
    return {
        "schema_version": 1,
        "mode": mode,
        "draft_sha256": _digest(draft),
        "final_sha256": _digest(final),
        "preamble_sha256": _digest(preamble),
        "context_sha256": _digest(context),
        "assembler_sha256": _digest(assembler_source),
    }


def canonical_manifest(document):
    return (json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _regular_bytes(path, label):
    try:
        metadata = path.lstat()
        value = path.read_bytes()
    except OSError as error:
        raise AssemblyError(label) from error
    if (
        not stat.S_ISREG(metadata.st_mode) or path.is_symlink()
        or metadata.st_nlink != 1 or metadata.st_uid != os.getuid()
    ):
        raise AssemblyError(label)
    return value


def _write_new(path, value, label):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(value)
    except OSError as error:
        raise AssemblyError(label) from error


def _helper_pair(helper, repository, tracker, unit, profile, emit):
    command = (
        sys.executable, str(helper), "--repository", str(repository),
        "--tracker", tracker, "--unit", unit, "--profile", profile,
        "--emit", emit,
    )
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    outputs = []
    for _ in range(2):
        completed = subprocess.run(command, capture_output=True, env=environment, check=False)
        if completed.returncode != 0 or completed.stderr:
            raise AssemblyError("helper " + emit)
        outputs.append(completed.stdout)
    if outputs[0] != outputs[1]:
        raise AssemblyError("helper " + emit + " mismatch")
    return outputs[0]


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=("executable", "passthrough"))
    parser.add_argument("--draft", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--preamble-output", required=True)
    parser.add_argument("--context-output", required=True)
    parser.add_argument("--repository")
    parser.add_argument("--tracker")
    parser.add_argument("--unit")
    parser.add_argument("--profile", choices=("Light", "Standard", "High-risk"))
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    try:
        source_path = Path(__file__)
        source = _regular_bytes(source_path, "assembler source")
        draft = _regular_bytes(Path(arguments.draft), "draft input")
        if arguments.mode == "executable":
            if not all((arguments.repository, arguments.tracker, arguments.unit, arguments.profile)):
                raise AssemblyError("executable arguments")
            helper = source_path.with_name("status_fingerprint.py")
            _regular_bytes(helper, "fingerprint helper")
            repository = Path(arguments.repository)
            context = _helper_pair(
                helper, repository, arguments.tracker, arguments.unit,
                arguments.profile, "context",
            )
            preamble = _helper_pair(
                helper, repository, arguments.tracker, arguments.unit,
                arguments.profile, "preamble",
            )
            final = assemble_executable(draft, preamble)
        else:
            if any((arguments.repository, arguments.tracker, arguments.unit, arguments.profile)):
                raise AssemblyError("passthrough arguments")
            context = b""
            preamble = b""
            final = assemble_passthrough(draft)
        manifest = assembly_manifest(arguments.mode, draft, final, preamble, context, source)
        _write_new(Path(arguments.output), final, "final output")
        _write_new(Path(arguments.preamble_output), preamble, "preamble output")
        _write_new(Path(arguments.context_output), context, "context output")
        _write_new(Path(arguments.manifest), canonical_manifest(manifest), "assembly manifest")
    except AssemblyError as error:
        raise SystemExit("error: " + str(error)) from error


if __name__ == "__main__":
    main()
