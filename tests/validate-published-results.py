#!/usr/bin/env python3
"""CLI for deterministic development and release result validation."""

from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from published_result_validator import ResultValidationError, validate_repository


def main():
    if len(sys.argv) not in (2, 3) or (len(sys.argv) == 3 and sys.argv[2] != "--release"):
        raise SystemExit("usage: validate-published-results.py REPO_ROOT [--release]")
    try:
        ready = validate_repository(sys.argv[1], require_release=len(sys.argv) == 3)
    except ResultValidationError as error:
        raise SystemExit("FAIL: published results: " + str(error))
    print("ready" if ready else "blocked")


if __name__ == "__main__":
    main()
