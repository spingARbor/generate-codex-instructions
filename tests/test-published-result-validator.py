#!/usr/bin/env python3
"""Guard against status-only or declaration-only release authorization."""

import json
from pathlib import Path
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from published_result_validator import ResultValidationError, validate_repository


def fail(message):
    raise SystemExit("FAIL: published result validator self-test: " + message)


def expect_failure(label, root):
    try:
        validate_repository(root)
    except ResultValidationError:
        return
    fail(label + " accepted")


def clone_required(source, target):
    for relative in (
        "VERSION",
        "skill/SKILL.md",
        "skill/agents/openai.yaml",
        "skill/scripts/status_fingerprint.py",
        "tests/run-forward-evals.sh",
        "tests/run-product-forward-eval.sh",
        "tests/publish-product-forward-results.py",
        "tests/product_forward_evidence.py",
        "tests/execution_contract.py",
        "tests/forward_eval_evidence.py",
        "tests/status_fingerprint.py",
        "evals/cases.json",
        "evals/results-v0.5.0.json",
        "evals/product-forward-results-v0.5.0.json",
        "evals/representative-forward-results-v0.5.0.json",
    ):
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, destination)


def main():
    source = Path(__file__).resolve().parent.parent
    validator_source = (source / "tests/published_result_validator.py").read_text(encoding="utf-8")
    for marker in ("validate_forward_case", "representative_bindings", "aggregate-publisher-semantic-replay-v3-poststate-bound"):
        if marker not in validator_source:
            fail("archived semantic replay marker " + marker)
    current_result = json.loads(
        (source / "evals/results-v0.5.0.json").read_text(encoding="utf-8")
    )
    current_authorized = (
        current_result.get("status") == "fresh-eval-passed"
        and current_result.get("release_authorized") is True
    )
    if current_authorized:
        if validate_repository(source) is not True:
            fail("current fresh evidence did not validate")
        if validate_repository(source, require_release=True) is not True:
            fail("release mode did not validate current fresh evidence")
    else:
        if validate_repository(source) is not False:
            fail("current pending evidence did not return blocked")
        try:
            validate_repository(source, require_release=True)
        except ResultValidationError as error:
            if "pending" not in str(error):
                fail("release mode returned wrong pending failure")
        else:
            fail("release mode accepted pending evidence")
    with tempfile.TemporaryDirectory(prefix="gci-result-validator-", dir="/tmp") as temporary:
        root = Path(temporary) / "repo"
        clone_required(source, root)
        result_path = root / "evals/results-v0.5.0.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result.update({
            "schema_version": 5,
            "status": "fresh-eval-passed",
            "cases": [{"id": "handcrafted", "outcome": "pass", "artifacts": {}, "session_command": "fake"}],
            "metrics": {"closure_rate": 1.0},
            "release_authorized": True,
        })
        result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        expect_failure("status-only fresh result", root)

        clone_required(source, root)
        product_path = root / "evals/product-forward-results-v0.5.0.json"
        product = json.loads(product_path.read_text(encoding="utf-8"))
        product.update({
            "schema_version": 3,
            "status": "fresh-eval-passed",
            "metrics": {"closure_rate": 1.0},
            "evidence": {"tracker_state": "Complete"},
            "evidence_source": "publisher-recomputed-v1",
            "artifacts": {},
        })
        product_path.write_text(json.dumps(product, indent=2) + "\n", encoding="utf-8")
        expect_failure("declaration-only product result", root)
    print("PASS: published result replay rejects status-only and declaration-only evidence")


if __name__ == "__main__":
    main()
