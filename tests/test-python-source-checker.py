#!/usr/bin/env python3
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def stop(label):
    raise SystemExit("FAIL: Python source checker self-test: " + label)


def run(command):
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(command, capture_output=True, text=True, timeout=10, env=environment)


def main():
    repo_root = Path(__file__).resolve().parent.parent
    checker = repo_root / "tests/check-python-sources.py"
    if not checker.is_file() or checker.is_symlink():
        stop("checker missing")

    validator_source = (repo_root / "tests/validate.sh").read_text(encoding="utf-8")
    if "python3 -m py_compile" in validator_source or "check-python-sources.py" not in validator_source:
        stop("validator still invokes bytecode compilation")

    with tempfile.TemporaryDirectory(prefix="gci-python-source-") as temporary:
        root = Path(temporary)
        good = root / "good.py"
        good.write_text("value = 1\n", encoding="utf-8")
        if run((sys.executable, str(checker), str(good))).returncode != 0:
            stop("valid source rejected")

        bad = root / "bad.py"
        bad.write_text("value =\n", encoding="utf-8")
        if run((sys.executable, str(checker), str(bad))).returncode == 0:
            stop("syntax error accepted")

        source_link = root / "source-link.py"
        source_link.symlink_to(good)
        if run((sys.executable, str(checker), str(source_link))).returncode == 0:
            stop("source symlink accepted")

        checker_link = root / "checker-link.py"
        checker_link.symlink_to(checker)
        if run((sys.executable, str(checker_link), str(good))).returncode == 0:
            stop("checker symlink accepted")

        fifo = root / "source.fifo"
        os.mkfifo(fifo)
        if run((sys.executable, str(checker), str(fifo))).returncode == 0:
            stop("special source accepted")

        hardlink = root / "source-hardlink.py"
        os.link(good, hardlink)
        if run((sys.executable, str(checker), str(hardlink))).returncode == 0:
            stop("hardlinked source accepted")

        if any(path.name == "__pycache__" for path in root.rglob("*")):
            stop("bytecode side effect")

    print("PASS: Python source AST and filesystem guards")


if __name__ == "__main__":
    main()
