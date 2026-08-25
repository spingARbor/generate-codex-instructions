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
        (root / ".project/development").mkdir(parents=True)
        (root / "AGENTS.md").write_text("# Authority\n", encoding="utf-8")
        (root / "src/main.py").write_text("VALUE = 1\n", encoding="utf-8")
        (root / "tests/test_main.py").write_text("assert True\n", encoding="utf-8")
        gate_paths = ["src/main.py", "tests/test_main.py"]
        gate_records = [
            {"path": path, "sha256": hashlib.sha256((root / path).read_bytes()).hexdigest()}
            for path in gate_paths
        ]
        input_fingerprint = hashlib.sha256(
            (json.dumps(gate_records, separators=(",", ":")) + "\n").encode("utf-8")
        ).hexdigest()
        (root / ".project/development/task_plan.md").write_text(
            "# Tracker\n\n"
            "tracker_revision: r1\n"
            "selection_decision: U1 is the sole dependency-ready unit.\n\n"
            "## Unit registry\n\n"
            "### U1\n\n"
            "state: In Progress\n"
            "selected: true\n"
            "owner: src/main.py\n"
            "authoritative_design: src/main.py\n"
            "nearest_test: tests/test_main.py\n"
            "next_convergence_condition: G1 passes and U1 is Complete.\n"
            "gate_refs: G1\n\n"
            "## Required gate registry\n\n"
            "### G1\n\n"
            "required: true\n"
            "status: pending\n"
            "owners: U1\n"
            "command: python3 -m unittest\n"
            'inputs_json: ["src/main.py","tests/test_main.py"]\n'
            "input_fingerprint: " + input_fingerprint + "\n"
            "passed_evidence: none\n"
            "recovery_condition: Run G1 and record fresh evidence.\n\n"
            "## Decisions and blockers\n\n"
            "active_blocker: none\n",
            encoding="utf-8",
        )
        subprocess.run(("git", "-C", str(root), "init", "-q", "-b", "main"), check=True)
        subprocess.run(("git", "-C", str(root), "config", "user.name", "Fingerprint Test"), check=True)
        subprocess.run(("git", "-C", str(root), "config", "user.email", "fingerprint@example.invalid"), check=True)
        subprocess.run(
            (
                "git", "-C", str(root), "add", "--",
                ".project/development/task_plan.md", "AGENTS.md", "src/main.py", "tests/test_main.py",
            ),
            check=True,
        )
        subprocess.run(
            ("git", "-C", str(root), "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture"),
            check=True,
        )
        paths = [".project/development/task_plan.md", "AGENTS.md", "src/main.py", "tests/test_main.py"]
        ledger = [
            {
                "id": path,
                "role": (
                    "tracker" if path.startswith(".project/")
                    else "authority" if path == "AGENTS.md"
                    else "owner" if path.startswith("src/")
                    else "regression"
                ),
                "sha256": hashlib.sha256((root / path).read_bytes()).hexdigest(),
            }
            for path in paths
        ]
        helper = Path(__file__).resolve().parent.parent / "skill/scripts/status_fingerprint.py"
        helper_args = (
            sys.executable, str(helper), "--repository", str(root),
            "--tracker", ".project/development/task_plan.md",
            "--unit", "U1", "--profile", "Light",
        )
        completed = subprocess.run(
            helper_args + ("--emit", "context"),
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
        light_protocol = {
                    "operations": ["test", "tracker", "observe"],
                    "from_revision": ["r1", "r1", "observed-prior"],
                    "test_command": "python3 -m unittest && git diff --check",
                    "transitions": ["none", "In Progress->Complete", "none"],
                    "gates": ["none", "G1:pending->passed", "none"],
                    "receipts": [
                        "none", ".project/development/evidence/G1.pass", "none",
                    ],
                    "boundaries": [
                        ["src/main.py", "tests/test_main.py"],
                        [
                            ".project/development/evidence/G1.pass",
                            ".project/development/task_plan.md",
                        ],
                        [
                            ".project/development/evidence/G1.pass",
                            ".project/development/task_plan.md",
                            "src/main.py",
                            "tests/test_main.py",
                        ],
                    ],
                    "machine_lines": [
                        [
                            "Command: python3 -m unittest && git diff --check",
                            'Files/boundary: ["src/main.py","tests/test_main.py"]',
                            "Expected transition: unit=U1; owner=src/main.py; transitions=none; from_revision=r1; gate=none",
                            "Evidence required: receipt=none; artifacts=test-output,diff-check-output",
                        ],
                        [
                            "Command: none: persist the verified tracker closure",
                            'Files/boundary: [".project/development/evidence/G1.pass",".project/development/task_plan.md"]',
                            "Expected transition: unit=U1; owner=src/main.py; transitions=In Progress->Complete; from_revision=r1; gate=G1:pending->passed",
                            "Evidence required: receipt=.project/development/evidence/G1.pass; artifacts=.project/development/evidence/G1.pass,.project/development/task_plan.md",
                        ],
                        [
                            "Command: git status --porcelain=v1 --untracked-files=all",
                            'Files/boundary: [".project/development/evidence/G1.pass",".project/development/task_plan.md","src/main.py","tests/test_main.py"]',
                            "Expected transition: unit=U1; owner=src/main.py; transitions=none; from_revision=observed-prior; gate=none",
                            "Evidence required: receipt=none; artifacts=final-status",
                        ],
                    ],
        }
        expected_context = {
            "owner": "src/main.py",
            "nearest_test": "tests/test_main.py",
            "gate_ids": ["G1"],
            "passed_evidence": [],
            "authoritative_inputs": paths,
            "verified_owner_light_protocol": light_protocol,
        }
        if actual != expected_context:
            fail("installed helper compatibility")
        canonical = lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        inventory = {
            "units": [{
                "id": "U1", "state": "In Progress", "claim": "none",
                "dependency": "none", "next": "G1 passes and U1 is Complete.",
            }],
            "gates": [{
                "id": "G1", "state": "pending",
                "command_or_recovery": "python3 -m unittest",
            }],
            "blockers": [],
        }
        evidence_projection = {
            "sha256": ledger_sha256,
            "rows": [{"id": entry["id"], "role": entry["role"]} for entry in ledger],
        }
        expected_preamble = [
            "Snapshot: tracker_revision=r1; branch=main; head="
            + subprocess.check_output(("git", "-C", str(root), "rev-parse", "HEAD"), text=True).strip()
            + "; status_fingerprint=" + expected,
            "Unit counts: Complete=0; In Progress=1; Claimed=0; Ready=0; Blocked=0; Failed=0",
            "Gate counts: passed=0; pending=1; failed=0; unknown-definition=0; conflicting=0",
            "Selection basis: U1 is the sole dependency-ready unit.",
            "Current executable unit: U1; dependency_evidence=none",
            "Selected unit: U1",
            'Selected required gates: [{"id":"G1","state":"pending"}]',
            "Evidence reads: used=4; ceiling=6; extension=0; reason=none",
            "Evidence ledger: " + canonical(evidence_projection),
            "Open inventory: " + canonical(inventory),
        ]
        completed = subprocess.run(
            helper_args + ("--emit", "preamble"),
            check=True,
            text=True,
            capture_output=True,
        )
        if completed.stdout.splitlines() != expected_preamble:
            fail("installed helper preamble projection")
        tracker = root / ".project/development/task_plan.md"
        tracker_text = tracker.read_text(encoding="utf-8")
        tracker.write_text(
            tracker_text.replace("command: python3 -m unittest\n", ""),
            encoding="utf-8",
        )
        completed = subprocess.run(
            (
                sys.executable, str(helper), "--repository", str(root),
                "--tracker", ".project/development/task_plan.md",
                "--unit", "U1", "--profile", "Light", "--emit", "context",
            ),
            text=True,
            capture_output=True,
        )
        if completed.returncode == 0 or "Gate command/recovery" not in completed.stderr:
            fail("runtime helper accepted a selected Gate without a command")
        tracker.write_text(tracker_text, encoding="utf-8")
        (root / "linked-src").symlink_to(root / "src", target_is_directory=True)
        tracker.write_text(
            tracker.read_text(encoding="utf-8").replace(
                "authoritative_design: src/main.py",
                "authoritative_design: linked-src/main.py",
            ),
            encoding="utf-8",
        )
        completed = subprocess.run(
            (
                sys.executable, str(helper), "--repository", str(root),
                "--tracker", ".project/development/task_plan.md",
                "--unit", "U1", "--profile", "Light", "--emit", "context",
            ),
            text=True,
            capture_output=True,
        )
        if completed.returncode == 0 or "unsafe evidence input" not in completed.stderr:
            fail("runtime helper accepted an intermediate symlink component")
    print("PASS: shared status-fingerprint-v1 safety and bounded drift")


if __name__ == "__main__":
    main()
