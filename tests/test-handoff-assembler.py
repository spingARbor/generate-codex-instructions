#!/usr/bin/env python3

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True


def fail(message):
    raise SystemExit("FAIL: handoff assembler self-test: " + message)


def load_assembler():
    path = Path(__file__).resolve().parent.parent / "skill/scripts/assemble_handoff.py"
    spec = importlib.util.spec_from_file_location("assemble_handoff", path)
    if spec is None or spec.loader is None:
        fail("assembler import spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(value):
    return hashlib.sha256(value).hexdigest()


def main():
    module = load_assembler()
    labels = (
        "Snapshot", "Unit counts", "Gate counts", "Selection basis",
        "Current executable unit", "Selected unit", "Selected required gates",
        "Evidence reads", "Evidence ledger", "Open inventory",
    )
    candidate = "".join(label + ": model value\n" for label in labels)
    trusted = "".join(label + ": trusted value\n" for label in labels).encode("utf-8")
    body = "```text\nProtocol profile: Standard\nRepository: .\n```\n"
    draft = ("Status: in progress\n" + candidate + body).encode("utf-8")
    expected = b"Status: in progress\n" + trusted + body.encode("utf-8")
    try:
        final = module.assemble_executable(draft, trusted)
    except module.AssemblyError as error:
        fail("valid executable draft rejected: " + str(error))
    if final != expected or b"model value" in final:
        fail("authoritative preamble replacement")
    if module.assemble_passthrough(draft) != draft:
        fail("passthrough changed bytes")
    if module.assemble_passthrough(b"plain draft") != b"plain draft\n":
        fail("passthrough final newline")
    if module.assemble_executable(draft.rstrip(b"\n"), trusted) != expected:
        fail("executable final newline")
    for label, invalid_draft, invalid_preamble in (
        ("missing draft row", b"Status\n" + body.encode("utf-8"), trusted),
        ("extra draft row", b"Status\n" + candidate.encode("utf-8") + b"Extra: x\n" + body.encode("utf-8"), trusted),
        ("bad trusted row", draft, trusted.replace(b"Open inventory:", b"Inventory:")),
    ):
        try:
            module.assemble_executable(invalid_draft, invalid_preamble)
        except module.AssemblyError:
            pass
        else:
            fail(label + " accepted")
    manifest = module.assembly_manifest(
        "executable", draft, final, trusted,
        b'{"owner":"src/main.py"}\n', b"assembler source\n",
    )
    if tuple(manifest) != (
        "schema_version", "mode", "draft_sha256", "final_sha256",
        "preamble_sha256", "context_sha256", "assembler_sha256",
    ):
        fail("manifest schema")
    if manifest != {
        "schema_version": 1,
        "mode": "executable",
        "draft_sha256": digest(draft),
        "final_sha256": digest(final),
        "preamble_sha256": digest(trusted),
        "context_sha256": digest(b'{"owner":"src/main.py"}\n'),
        "assembler_sha256": digest(b"assembler source\n"),
    }:
        fail("manifest binding")
    encoded = module.canonical_manifest(manifest)
    if encoded != (json.dumps(manifest, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"):
        fail("manifest canonical bytes")
    print("PASS: deterministic final handoff assembly")


if __name__ == "__main__":
    main()
