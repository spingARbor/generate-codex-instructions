#!/usr/bin/env python3
import importlib.util
import os
from pathlib import Path
import sys
import tempfile


def stop(label):
    raise SystemExit("FAIL: forward eval publisher guard self-test: " + label)


def load_module(path):
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("forward_eval_publisher", path)
    if spec is None or spec.loader is None:
        stop("publisher import")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expect_failure(label, function, *arguments):
    try:
        function(*arguments)
    except SystemExit as error:
        if str(error).startswith("FAIL: forward eval publish: "):
            return
        stop(label + " wrong failure: " + str(error))
    stop(label + " accepted")


def new_repo(root, name):
    repo = root / name
    (repo / "evals").mkdir(parents=True)
    return repo


def main():
    repo_root = Path(__file__).resolve().parent.parent
    module = load_module(repo_root / "tests/publish-forward-eval-results.py")
    if not hasattr(module, "prepare_artifact_destination") or not hasattr(module, "validate_publishable_bytes"):
        stop("publisher destination guards missing")

    with tempfile.TemporaryDirectory(prefix="gci-publisher-guard-") as temporary:
        root = Path(temporary)
        safe = new_repo(root, "safe")
        parent, final, temporary_target = module.prepare_artifact_destination(safe, "0.4.0")
        if parent != safe / "evals/artifacts" or final != parent / "v0.4.0" or temporary_target.parent != parent:
            stop("safe destination paths")
        if not parent.is_dir() or parent.is_symlink() or final.exists() or final.is_symlink():
            stop("safe destination state")

        outside = root / "outside"
        outside.mkdir()

        evals_link_repo = root / "evals-link"
        evals_link_repo.mkdir()
        (evals_link_repo / "evals").symlink_to(outside)
        expect_failure("evals symlink", module.prepare_artifact_destination, evals_link_repo, "0.4.0")

        parent_link_repo = new_repo(root, "parent-link")
        (parent_link_repo / "evals/artifacts").symlink_to(outside)
        expect_failure("artifact parent symlink", module.prepare_artifact_destination, parent_link_repo, "0.4.0")

        parent_fifo_repo = new_repo(root, "parent-fifo")
        os.mkfifo(parent_fifo_repo / "evals/artifacts")
        expect_failure("artifact parent special", module.prepare_artifact_destination, parent_fifo_repo, "0.4.0")

        target_link_repo = new_repo(root, "target-link")
        (target_link_repo / "evals/artifacts").mkdir()
        (target_link_repo / "evals/artifacts/v0.4.0").symlink_to(outside)
        expect_failure("artifact target symlink", module.prepare_artifact_destination, target_link_repo, "0.4.0")

        target_fifo_repo = new_repo(root, "target-fifo")
        (target_fifo_repo / "evals/artifacts").mkdir()
        os.mkfifo(target_fifo_repo / "evals/artifacts/v0.4.0")
        expect_failure("artifact target special", module.prepare_artifact_destination, target_fifo_repo, "0.4.0")

        target_file_repo = new_repo(root, "target-file")
        (target_file_repo / "evals/artifacts").mkdir()
        (target_file_repo / "evals/artifacts/v0.4.0").write_text("occupied\n", encoding="utf-8")
        expect_failure("artifact target occupied", module.prepare_artifact_destination, target_file_repo, "0.4.0")

        for marker in (
            b"UNTRUSTED-DIRECTIVE-CANARY-DO-NOT-OBEY",
            b"sk-exampleSecret12345",
            b"-----BEGIN PRIVATE KEY-----",
        ):
            expect_failure("publishable marker", module.validate_publishable_bytes, marker, "response")

    print("PASS: forward eval publisher physical destination and marker guards")


if __name__ == "__main__":
    main()
