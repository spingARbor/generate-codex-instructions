#!/usr/bin/env python3
"""Canonical status-fingerprint-v1 serialization shared by evaluators and tests."""

import hashlib
import json
import re
import struct
from pathlib import PurePosixPath


class FingerprintError(ValueError):
    pass


def _text(value, label, *, normalize_lines=False):
    if not isinstance(value, str):
        raise FingerprintError(label + " must be text")
    if normalize_lines:
        value = value.replace("\r\n", "\n").replace("\r", "\n")
    if "\x00" in value:
        raise FingerprintError(label + " contains NUL")
    return value.encode("utf-8")


def _field(value):
    return struct.pack(">Q", len(value)) + value


def normalize_path(value):
    raw = _text(value, "path").decode("utf-8")
    if not raw or raw.startswith("/") or "\\" in raw:
        raise FingerprintError("path must be repository-relative POSIX text")
    if any(ord(character) < 32 or ord(character) == 127 for character in raw):
        raise FingerprintError("path contains a control character")
    path = PurePosixPath(raw)
    if raw != path.as_posix() or any(part in ("", ".", "..") for part in path.parts):
        raise FingerprintError("path is not normalized")
    if path.parts[0] == ".git":
        raise FingerprintError("Git metadata is not a file input")
    return raw


def _selected_evidence(value):
    if not isinstance(value, dict) or tuple(value) != (
        "unit", "owner", "gates", "evidence", "ledger_sha256"
    ):
        raise FingerprintError("selected evidence schema")
    if not isinstance(value["unit"], str) or not value["unit"]:
        raise FingerprintError("selected evidence unit")
    if not isinstance(value["owner"], str) or not value["owner"]:
        raise FingerprintError("selected evidence owner")
    document = {"unit": value["unit"], "owner": value["owner"]}
    for key in ("gates", "evidence"):
        items = value[key]
        if not isinstance(items, list) or any(not isinstance(item, str) or not item for item in items):
            raise FingerprintError("selected evidence " + key)
        if items != sorted(items, key=lambda item: item.encode("utf-8")) or len(items) != len(set(items)):
            raise FingerprintError("selected evidence " + key + " ordering")
        document[key] = items
    ledger_sha256 = value["ledger_sha256"]
    if not isinstance(ledger_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", ledger_sha256) is None:
        raise FingerprintError("selected evidence ledger digest")
    document["ledger_sha256"] = ledger_sha256
    return (json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def canonical_bytes(state):
    required = {"branch", "head", "status", "files", "tracker_revision", "selected_evidence"}
    if not isinstance(state, dict) or set(state) != required:
        raise FingerprintError("state schema")
    branch = _text(state["branch"], "branch")
    head_text = state["head"]
    if not isinstance(head_text, str) or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head_text) is None:
        raise FingerprintError("HEAD must be a lowercase object ID")
    status = state["status"]
    if not isinstance(status, bytes):
        raise FingerprintError("status must be raw porcelain-v1 -z bytes")
    files = state["files"]
    if not isinstance(files, list):
        raise FingerprintError("files must be a list")
    canonical_files = []
    seen = set()
    for entry in files:
        if not isinstance(entry, dict) or tuple(entry) != ("path", "sha256"):
            raise FingerprintError("file input schema")
        path = normalize_path(entry["path"])
        if path in seen:
            raise FingerprintError("duplicate file input")
        seen.add(path)
        digest = entry["sha256"]
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise FingerprintError("file content digest")
        canonical_files.append((path.encode("utf-8"), bytes.fromhex(digest)))
    canonical_files.sort(key=lambda item: item[0])
    file_payload = bytearray()
    for path, content_digest in canonical_files:
        file_payload.extend(_field(path))
        file_payload.extend(_field(content_digest))
    fields = (
        b"status-fingerprint-v1",
        branch,
        _text(head_text, "head"),
        status,
        bytes(file_payload),
        _text(state["tracker_revision"], "tracker revision"),
        _selected_evidence(state["selected_evidence"]),
    )
    return b"".join(_field(value) for value in fields)


def fingerprint(state):
    return hashlib.sha256(canonical_bytes(state)).hexdigest()


def bounded_snapshot(observations):
    """Return the stable digest, allowing one recomputation and rejecting drift #2."""
    if not isinstance(observations, list) or not observations:
        raise FingerprintError("snapshot observations")
    digests = [fingerprint(item) for item in observations]
    current = digests[0]
    recomputations = 0
    for candidate in digests[1:]:
        if candidate == current:
            continue
        if recomputations == 1:
            raise FingerprintError("second snapshot drift")
        recomputations += 1
        current = candidate
    return {"sha256": current, "recomputations": recomputations}
