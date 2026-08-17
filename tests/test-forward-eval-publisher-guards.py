#!/usr/bin/env python3
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types


def stop(label):
    raise SystemExit("FAIL: forward eval publisher guard self-test: " + label)


def load_module(path):
    try:
        source = path.read_bytes()
        code = compile(source, str(path), "exec")
    except (OSError, SyntaxError):
        stop("publisher import")
    module = types.ModuleType("forward_eval_publisher")
    module.__file__ = str(path)
    exec(code, module.__dict__)
    return module


def expect_failure(label, function, *arguments):
    try:
        function(*arguments)
    except SystemExit as error:
        if str(error).startswith("FAIL: forward eval publish: "):
            return
        stop(label + " wrong failure: " + str(error))
    stop(label + " accepted")


def expect_success(label, function, *arguments):
    try:
        function(*arguments)
    except SystemExit as error:
        stop(label + " rejected: " + str(error))


def new_repo(root, name):
    repo = root / name
    (repo / "evals").mkdir(parents=True)
    return repo


def main():
    repo_root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix="gci-publisher-cli-") as temporary:
        source_root = Path(temporary)
        publisher_path = source_root / "publish-forward-eval-results.py"
        evidence_path = source_root / "forward_eval_evidence.py"
        shutil.copyfile(repo_root / "tests/publish-forward-eval-results.py", publisher_path)
        shutil.copyfile(repo_root / "tests/forward_eval_evidence.py", evidence_path)
        cache_path = source_root / "__pycache__"
        if cache_path.exists():
            stop("direct CLI cache precondition")
        environment = os.environ.copy()
        environment.pop("PYTHONDONTWRITEBYTECODE", None)
        environment.pop("PYTHONPYCACHEPREFIX", None)
        completed = subprocess.run(
            (sys.executable, str(publisher_path)),
            cwd=source_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 1 or "usage: publish-forward-eval-results.py" not in completed.stderr:
            stop("controlled direct CLI invocation")
        if cache_path.exists():
            stop("direct CLI generated source cache")

    module = load_module(repo_root / "tests/publish-forward-eval-results.py")
    evidence_helper = sys.modules.get("forward_eval_evidence")
    if evidence_helper is None:
        stop("publisher evidence helper import")
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

        for value in (
            b"Use a canary deployment before production rollout.\n",
            b"CANARY deployment is a standard release strategy.\n",
            b"untrusted-directive-canary-do-not-obey\n",
            b"ask-exampleSecret12345\n",
            b"sk-short\n",
            b"XAKIA1234567890ABCDEF\n",
            b"-----BEGIN PUBLIC KEY-----\n",
        ):
            expect_success("legal publishable text", module.validate_publishable_bytes, value, "response")

        for marker in (
            *(b"prefix " + marker + b" suffix" for marker in evidence_helper.SENSITIVE_RESPONSE_MARKERS),
            b"sk-exampleSecret12345",
            b"AKIA1234567890ABCDEF",
            b"-----BEGIN PRIVATE KEY-----",
            b"-----begin rsa private key-----",
            b"-----Begin OpenSSH Private Key-----",
        ):
            expect_failure("publishable marker", module.validate_publishable_bytes, marker, "response")

        if getattr(module, "contains_sensitive_evidence", None) is not evidence_helper.contains_sensitive_evidence:
            stop("publisher does not share evidence marker gate")

    print("PASS: forward eval publisher physical destination and marker guards")


if __name__ == "__main__":
    main()
