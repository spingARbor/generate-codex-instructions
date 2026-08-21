#!/usr/bin/env python3
"""Safety and drift vectors for the shared status-fingerprint-v1 implementation."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from status_fingerprint import FingerprintError, bounded_snapshot, fingerprint


def fail(message):
    raise SystemExit("FAIL: status fingerprint self-test: " + message)


def rejected(label, state):
    try:
        fingerprint(state)
    except FingerprintError:
        return
    fail(label + " accepted")


def main():
    baseline = {
        "branch": "feature/标签",
        "head": "a" * 40,
        "status": b" M src/label.py\0?? tests/label.test.py\0",
        "files": [
            {"path": "tests/标签.test.py", "sha256": "1" * 64},
            {"path": "src/label.py", "sha256": "2" * 64},
        ],
        "tracker_revision": "r1",
        "selected_evidence": {
            "unit": "U1",
            "owner": "src/label.py",
            "gates": ["G1"],
            "evidence": ["src/label.py", "tests/标签.test.py"],
            "ledger_sha256": "b" * 64,
        },
    }
    equivalent = dict(
        baseline,
        files=list(reversed(baseline["files"])),
    )
    if fingerprint(baseline) != fingerprint(equivalent):
        fail("canonical UTF-8 path ordering")
    content_drift = dict(
        baseline,
        files=[
            {"path": "tests/标签.test.py", "sha256": "1" * 64},
            {"path": "src/label.py", "sha256": "3" * 64},
        ],
    )
    if fingerprint(baseline) == fingerprint(content_drift):
        fail("file content digest drift")
    status_drift = dict(baseline, status=baseline["status"] + b"?? docs/notes.md\0")
    tracker_drift = dict(status_drift, tracker_revision="r2")
    first = bounded_snapshot([baseline, status_drift])
    if first["recomputations"] != 1 or first["sha256"] != fingerprint(status_drift):
        fail("one-drift recomputation")
    try:
        bounded_snapshot([baseline, status_drift, tracker_drift])
    except FingerprintError as error:
        if str(error) != "second snapshot drift":
            fail("wrong second-drift failure")
    else:
        fail("second drift accepted")
    for label, files in (
        ("absolute path", [{"path": "/etc/passwd", "sha256": "1" * 64}]),
        ("parent path", [{"path": "../outside", "sha256": "1" * 64}]),
        ("Git metadata", [{"path": ".git/config", "sha256": "1" * 64}]),
        ("control path", [{"path": "src/line\nbreak", "sha256": "1" * 64}]),
        ("duplicate path", [{"path": "src/a", "sha256": "1" * 64}, {"path": "src/a", "sha256": "2" * 64}]),
        ("invalid digest", [{"path": "src/a", "sha256": "not-a-digest"}]),
    ):
        rejected(label, dict(baseline, files=files))
    rejected("text status", dict(baseline, status=" M src/a\0"))
    rejected("uppercase HEAD", dict(baseline, head="A" * 40))
    rejected(
        "unsorted selected evidence",
        dict(
            baseline,
            selected_evidence={
                "unit": "U1",
                "owner": "src/label.py",
                "gates": ["G2", "G1"],
                "evidence": ["src/label.py"],
                "ledger_sha256": "b" * 64,
            },
        ),
    )
    rejected(
        "invalid ledger digest",
        dict(
            baseline,
            selected_evidence=dict(baseline["selected_evidence"], ledger_sha256="not-a-digest"),
        ),
    )
    with tempfile.TemporaryDirectory(prefix="gci-runtime-fingerprint-", dir="/tmp") as temporary:
        root = Path(temporary) / "repo"
        root.mkdir()
        (root / "src").mkdir()
        (root / "tests").mkdir()
        (root / "src/main.py").write_text("VALUE = 1\n", encoding="utf-8")
        (root / "tests/test_main.py").write_text("assert True\n", encoding="utf-8")
        subprocess.run(("git", "-C", str(root), "init", "-q", "-b", "main"), check=True)
        subprocess.run(("git", "-C", str(root), "config", "user.name", "Fingerprint Test"), check=True)
        subprocess.run(("git", "-C", str(root), "config", "user.email", "fingerprint@example.invalid"), check=True)
        subprocess.run(("git", "-C", str(root), "add", "--", "src/main.py", "tests/test_main.py"), check=True)
        subprocess.run(
            ("git", "-C", str(root), "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture"),
            check=True,
        )
        paths = ["src/main.py", "tests/test_main.py"]
        ledger = [
            {
                "id": path,
                "role": "owner" if path.startswith("src/") else "regression",
                "sha256": hashlib.sha256((root / path).read_bytes()).hexdigest(),
            }
            for path in paths
        ]
        helper = Path(__file__).resolve().parent.parent / "skill/scripts/status_fingerprint.py"
        completed = subprocess.run(
            (
                sys.executable, str(helper), "--repository", str(root),
                "--tracker-revision", "r1", "--unit", "U1",
                "--owner", "src/main.py", "--gate", "G1",
                "--ledger-json", json.dumps(ledger, ensure_ascii=False, separators=(",", ":")),
                "--gate-inputs-json", json.dumps(paths, separators=(",", ":")),
            ),
            check=True,
            text=True,
            capture_output=True,
        )
        actual = json.loads(completed.stdout)
        ledger_sha256 = hashlib.sha256(
            (json.dumps(ledger, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        ).hexdigest()
        expected = fingerprint({
            "branch": "main",
            "head": subprocess.check_output(("git", "-C", str(root), "rev-parse", "HEAD"), text=True).strip(),
            "status": b"",
            "files": [{"path": entry["id"], "sha256": entry["sha256"]} for entry in ledger],
            "tracker_revision": "r1",
            "selected_evidence": {
                "unit": "U1", "owner": "src/main.py", "gates": ["G1"],
                "evidence": paths, "ledger_sha256": ledger_sha256,
            },
        })
        if (
            actual["status_fingerprint"] != expected
            or actual["ledger_sha256"] != ledger_sha256
            or actual.get("evidence_ledger") != {
                "sha256": ledger_sha256,
                "rows": [{"id": entry["id"], "role": entry["role"]} for entry in ledger],
            }
        ):
            fail("installed helper compatibility")
        gate_records = [{"path": entry["id"], "sha256": entry["sha256"]} for entry in ledger]
        expected_gate = hashlib.sha256(
            (json.dumps(gate_records, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        ).hexdigest()
        if actual.get("gate_input_fingerprint") != expected_gate:
            fail("installed Gate input helper compatibility")
    print("PASS: shared status-fingerprint-v1 safety and bounded drift")


if __name__ == "__main__":
    main()
