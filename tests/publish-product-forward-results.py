#!/usr/bin/env python3
"""Publish product evidence only after recomputing claims from raw captures."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys

sys.dont_write_bytecode = True
from product_forward_evidence import (
    ProductEvidenceError,
    RAW_ARTIFACTS,
    derive_product_result,
    regular_bytes,
    validate_runtime_snapshot,
)


class PublishFailure(Exception):
    pass


def stop(message):
    raise PublishFailure(message)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def artifact_reference(repo_root, path):
    value = regular_bytes(path, "published artifact")
    return {
        "path": path.relative_to(repo_root).as_posix(),
        "sha256": digest(value),
        "bytes": len(value),
    }


def private_run_root(argument):
    if argument.is_symlink():
        stop("run root symlink")
    try:
        root = argument.resolve(strict=True)
        metadata = root.lstat()
    except OSError:
        stop("run root")
    if (
        not str(root).startswith("/tmp/")
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) not in (0o500, 0o700)
    ):
        stop("private run root")
    return root


def main():
    if len(sys.argv) != 4:
        stop("usage: publish-product-forward-results.py RUN_ROOT REPO_ROOT VERSION")
    run_root = private_run_root(Path(sys.argv[1]))
    repo_root = Path(sys.argv[2]).resolve(strict=True)
    version = sys.argv[3]
    if version != (repo_root / "VERSION").read_text(encoding="ascii").strip():
        stop("version")
    try:
        validate_runtime_snapshot(run_root, repo_root)
        derived = derive_product_result(run_root)
    except ProductEvidenceError as error:
        stop(str(error))
    version_root = repo_root / ("evals/product-artifacts/v" + version)
    destination = version_root / derived["case"]
    if destination.exists() or destination.is_symlink():
        stop("product artifact target already exists")
    version_root.mkdir(mode=0o755, parents=True, exist_ok=True)
    destination.mkdir(mode=0o700)
    try:
        for name in RAW_ARTIFACTS + ("capture-manifest.json",):
            value = regular_bytes(run_root / name, name)
            if any(marker in value for marker in (b"/tmp/", b"/home/", b"/Users/")) and name in ("generation-response.txt", "execution-response.txt"):
                stop("response contains evaluator path")
            target = destination / name
            with target.open("xb") as sink:
                sink.write(value)
            target.chmod(0o644)
        artifacts = {
            name: artifact_reference(repo_root, destination / name)
            for name in RAW_ARTIFACTS + ("capture-manifest.json",)
        }
        result = {
            "schema_version": 4,
            "version": version,
            "status": "fresh-eval-passed",
            "case": derived["case"],
            "metrics": derived["metrics"],
            "evidence": derived["evidence"],
            "evidence_source": "publisher-recomputed-v3-prestate-and-observed-bound",
            "artifacts": artifacts,
            "bindings": {
                "skill_sha256": digest((repo_root / "skill/SKILL.md").read_bytes()),
                "handoff_contract_sha256": digest((repo_root / "skill/references/handoff-contract.md").read_bytes()),
                "runtime_assembler_sha256": digest((repo_root / "skill/scripts/assemble_handoff.py").read_bytes()),
                "runtime_fingerprint_sha256": digest((repo_root / "skill/scripts/status_fingerprint.py").read_bytes()),
                "runner_sha256": digest((repo_root / "tests/run-product-forward-eval.sh").read_bytes()),
                "publisher_sha256": digest((repo_root / "tests/publish-product-forward-results.py").read_bytes()),
                "evidence_helper_sha256": digest((repo_root / "tests/product_forward_evidence.py").read_bytes()),
                "transition_helper_sha256": digest((repo_root / "tests/execution_contract.py").read_bytes()),
                "corpus_sha256": digest((repo_root / "evals/cases.json").read_bytes()),
                "fingerprint_sha256": digest((repo_root / "tests/status_fingerprint.py").read_bytes()),
                "tool_access_evidence_sha256": digest((repo_root / "tests/tool_access_evidence.py").read_bytes()),
            },
            "release_authorized": False,
            "limitation": "Product closure reconciles generated expectations with raw observed receipts; complete corpus release authorization is a separate gate.",
        }
        result_path = repo_root / ("evals/product-forward-results-v" + version + ".json")
        temporary = result_path.with_name("." + result_path.name + ".tmp-" + str(os.getpid()))
        with temporary.open("x", encoding="utf-8") as sink:
            json.dump(result, sink, ensure_ascii=False, indent=2)
            sink.write("\n")
        os.replace(temporary, result_path)
    except BaseException:
        if destination.exists() and not destination.is_symlink():
            shutil.rmtree(destination)
        raise
    print(json.dumps({"status": result["status"], "case": result["case"], "path": result_path.name}, separators=(",", ":")))


if __name__ == "__main__":
    try:
        main()
    except (PublishFailure, ProductEvidenceError) as error:
        raise SystemExit("FAIL: product forward publish: " + str(error))
