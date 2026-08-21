#!/usr/bin/env python3
"""Map changed repository surfaces to the checks they require."""

from pathlib import PurePosixPath
import sys


CHECKS = {
    "text": ("quick_validate", "diff_check"),
    "output_contract": ("quick_validate", "contract_markers", "diff_check"),
    "behavior_protocol": ("forward_eval", "evidence_self_test", "diff_check"),
    "runner_or_publisher": ("runner_guards", "publisher_self_test", "fresh_eval", "diff_check"),
    "runtime_install": ("quick_validate", "install_guard", "shell_guard", "diff_check"),
}


def classify(path):
    normalized = PurePosixPath(path).as_posix()
    if normalized in {"skill/SKILL.md", "README.md", "docs/superpowers/specs/2026-08-16-plan-convergence-output-design.md"}:
        return {"output_contract" if normalized.startswith("skill/") else "text"}
    if normalized in {"skill/agents/openai.yaml", "skill/scripts/status_fingerprint.py", "install.sh"}:
        return {"runtime_install"}
    if normalized.startswith("tests/run-") or normalized.startswith("tests/publish-"):
        return {"runner_or_publisher"}
    if normalized.startswith("tests/") or normalized.startswith("evals/"):
        return {"behavior_protocol"}
    return {"text"}


def required_checks(paths):
    categories = set().union(*(classify(path) for path in paths)) if paths else set()
    return categories, set().union(*(CHECKS[category] for category in categories)) if categories else set()


def fail(message):
    raise SystemExit("FAIL: impact classifier: " + message)


def main():
    if len(sys.argv) > 1:
        categories, checks = required_checks(sys.argv[1:])
        print("categories=" + ",".join(sorted(categories)))
        print("checks=" + ",".join(sorted(checks)))
        return
    vectors = {
        ("skill/SKILL.md",): {"output_contract"},
        ("README.md",): {"text"},
        ("skill/agents/openai.yaml", "skill/scripts/status_fingerprint.py", "install.sh"): {"runtime_install"},
        ("tests/run-forward-evals.sh", "evals/cases.json"): {"behavior_protocol", "runner_or_publisher"},
        ("tests/forward_eval_evidence.py",): {"behavior_protocol"},
    }
    for paths, expected in vectors.items():
        actual, _ = required_checks(paths)
        if actual != expected:
            fail(f"{paths}: {sorted(actual)} != {sorted(expected)}")
    print("PASS: impact classifier contract")


if __name__ == "__main__":
    main()
