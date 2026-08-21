#!/usr/bin/env python3
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
    validate_generation_evidence,
    validate_grounding_source_publication,
    validate_side_effect_evidence,
    validate_snapshot_evidence,
)

def fail(label):
    raise SystemExit("FAIL: forward eval evidence self-test: " + label)

def main():
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
        "schema_version": 5,
        "case_id": "plan-convergence-preamble",
        "generation_read_only": True,
        "lock_state": "absent",
        "response_fence_regions": [1],
        "response_sha256": ["0" * 64],
        "response_bytes": [10],
        "summary_sha256": ["1" * 64],
        "body_sha256": ["2" * 64],
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
