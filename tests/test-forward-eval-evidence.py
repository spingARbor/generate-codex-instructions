#!/usr/bin/env python3
import hashlib
import json
import tempfile
import base64
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from forward_eval_evidence import (
    EvidenceFailure,
    contains_sensitive_evidence,
    derive_side_effect_evidence,
    validate_assembly_evidence,
    validate_generation_evidence,
    validate_grounding_source_publication,
    validate_side_effect_evidence,
    validate_snapshot_evidence,
)

def fail(label):
    raise SystemExit("FAIL: forward eval evidence self-test: " + label)

def main():
    labels = (
        b"Snapshot: ", b"Unit counts: ", b"Gate counts: ", b"Selection basis: ",
        b"Current executable unit: ", b"Selected unit: ", b"Selected required gates: ",
        b"Evidence reads: ", b"Evidence ledger: ", b"Open inventory: ",
    )
    draft = b"Status\n" + b"".join(label + b"model\n" for label in labels) + b"```text\nProtocol profile: Standard\n```\n"
    preamble = b"".join(label + b"trusted\n" for label in labels)
    final = draft.splitlines(keepends=True)[0] + preamble + b"".join(draft.splitlines(keepends=True)[11:])
    context = b'{"owner":"src/main.py"}\n'
    assembler = b"assembler\n"
    manifest = {
        "schema_version": 1, "mode": "executable",
        "draft_sha256": hashlib.sha256(draft).hexdigest(),
        "final_sha256": hashlib.sha256(final).hexdigest(),
        "preamble_sha256": hashlib.sha256(preamble).hexdigest(),
        "context_sha256": hashlib.sha256(context).hexdigest(),
        "assembler_sha256": hashlib.sha256(assembler).hexdigest(),
    }
    validate_assembly_evidence(manifest, draft, final, preamble, context, assembler)
    passthrough = dict(
        manifest, mode="passthrough", final_sha256=manifest["draft_sha256"],
        preamble_sha256=hashlib.sha256(b"").hexdigest(),
        context_sha256=hashlib.sha256(b"").hexdigest(),
    )
    validate_assembly_evidence(passthrough, draft, draft, b"", b"", assembler)
    try:
        validate_assembly_evidence(dict(manifest, final_sha256="f" * 64), draft, final, preamble, context, assembler)
    except EvidenceFailure:
        pass
    else:
        fail("tampered assembly manifest accepted")
    encoded_sensitive_tracker = {
        "schema_version": 1,
        "case_id": "plan-convergence-preamble",
        "tracker_path": ".project/development/task_plan.md",
        "tracker_base64": base64.b64encode(b"SECRET-CANARY-NOT-A-CREDENTIAL\n").decode("ascii"),
    }
    if not contains_sensitive_evidence(base64.b64decode(encoded_sensitive_tracker["tracker_base64"], validate=True)):
        fail("sensitive grounding test precondition")
    try:
        validate_grounding_source_publication(encoded_sensitive_tracker, "plan-convergence-preamble")
    except EvidenceFailure:
        pass
    else:
        fail("base64-encoded sensitive grounding accepted")
    valid = {
        "schema_version": 6,
        "case_id": "plan-convergence-preamble",
        "generation_read_only": True,
        "lock_state": "absent",
        "response_fence_regions": [1],
        "response_sha256": ["0" * 64],
        "response_bytes": [10],
        "summary_sha256": ["1" * 64],
        "body_sha256": ["2" * 64],
        "draft_sha256": "6" * 64,
        "assembly_manifest_sha256": "7" * 64,
        "assembly_mode": "executable",
        "snapshot_manifest_sha256": "3" * 64,
        "post_state_manifest_sha256": "9" * 64,
        "grounding_sources_sha256": "8" * 64,
        "tracker_before_sha256": "4" * 64,
        "tracker_after_sha256": "4" * 64,
        "status_fingerprint_sha256": "5" * 64,
        "snapshot_recomputations": 0,
        "second_drift_blocked": False,
        "post_capture_audit": "host/evaluator responsibility",
    }
    try:
        validate_generation_evidence(valid)
    except EvidenceFailure:
        fail("valid evidence rejected")
    invalid = dict(valid)
    invalid["post_capture_audit"] = "pre-emission"
    try:
        validate_generation_evidence(invalid)
    except EvidenceFailure:
        pass
    else:
        fail("pre-emission audit accepted")
    state = {
        "schema_version": 2,
        "case_id": "plan-convergence-preamble",
        "git": {"branch": "feature/test", "head": "a" * 40, "status_hex": ""},
        "files": [{"path": "src/main.py", "mode": "100644", "bytes": 4, "sha256": "b" * 64}],
    }
    side_effect = derive_side_effect_evidence("plan-convergence-preamble", state, state)
    validate_side_effect_evidence(side_effect, "plan-convergence-preamble", True, state, state)
    fabricated = dict(side_effect, application_unchanged=False)
    try:
        validate_side_effect_evidence(fabricated, "plan-convergence-preamble", True, state, state)
    except EvidenceFailure:
        pass
    else:
        fail("fabricated side-effect claim accepted")
    validate_snapshot_evidence({
        "schema_version": 1,
        "case_id": "plan-convergence-preamble",
        "skill_sha256": "5" * 64,
        "runner_sha256": "6" * 64,
        "corpus_sha256": "7" * 64,
        "pre_integrity": True,
        "per_session_integrity": [True],
        "post_integrity": True,
    }, "plan-convergence-preamble", ("5" * 64, "6" * 64, "7" * 64))
    if not contains_sensitive_evidence(b"UNTRUSTED-DIRECTIVE-CANARY-DO-NOT-OBEY"):
        fail("canary accepted")
    with tempfile.TemporaryDirectory(prefix="gci-evidence-") as temporary:
        path = Path(temporary) / "evidence.json"
        path.write_text(json.dumps(valid, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        if json.loads(path.read_text(encoding="utf-8")) != valid:
            fail("JSON round trip")
    print("PASS: forward eval evidence boundary guards")

if __name__ == "__main__":
    main()
