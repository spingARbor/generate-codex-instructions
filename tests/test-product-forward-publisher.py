#!/usr/bin/env python3
"""Publisher tests prove metrics are recomputed from raw product captures."""

import json
import os
from pathlib import Path
import runpy
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from execution_contract import (
    canonical_ledger_sha256,
    evidence_ledger_projection,
    gate_input_fingerprint,
    parse_handoff,
)
from product_forward_evidence import RUNTIME_SNAPSHOT_FILES, PRESTATE_SOURCES, digest, write_capture_manifest
from status_fingerprint import fingerprint
from tool_access_evidence import project_tool_access


def fail(message):
    raise SystemExit("FAIL: product forward publisher self-test: " + message)


def valid_generation_response():
    vectors = runpy.run_path(str(Path(__file__).with_name("test-execution-contract.py")))
    return vectors["response"]()


def grounded_generation_response(values):
    response = valid_generation_response()
    parsed = parse_handoff(response)
    ledger = []
    for entry in parsed["evidence_ledger"]["rows"]:
        source = entry["id"]
        artifact = PRESTATE_SOURCES[source]
        value = values[artifact]
        raw = value if isinstance(value, bytes) else value.encode("utf-8")
        ledger.append({"id": source, "role": entry["role"], "sha256": digest(raw)})
    ledger_raw = json.dumps(
        evidence_ledger_projection(ledger), ensure_ascii=False, separators=(",", ":")
    )
    response = re.sub(r"(?m)^Evidence ledger: .+$", "Evidence ledger: " + ledger_raw, response)
    branch = values["git-branch-before.txt"].strip()
    head = values["git-head-before.txt"].strip()
    selected_evidence = {
        "unit": "U1",
        "owner": "src/normalize_label.py",
        "gates": ["G1"],
        "evidence": [entry["id"] for entry in ledger],
        "ledger_sha256": canonical_ledger_sha256(ledger),
    }
    status = fingerprint(
        {
            "branch": branch,
            "head": head,
            "status": values["git-status-before-z.bin"],
            "files": [
                {
                    "path": entry["id"],
                    "sha256": entry["sha256"],
                }
                for entry in ledger
            ],
            "tracker_revision": "r1",
            "selected_evidence": selected_evidence,
        }
    )
    return re.sub(
        r"(?m)^Snapshot: .+$",
        f"Snapshot: tracker_revision=r1; branch={branch}; head={head}; status_fingerprint={status}",
        response,
    )


def make_repo(source_root, root, name):
    repo = root / name
    for relative in (
        "skill/SKILL.md",
        "skill/agents/openai.yaml",
        "skill/references/handoff-contract.md",
        "skill/scripts/assemble_handoff.py",
        "skill/scripts/status_fingerprint.py",
        "tests/run-product-forward-eval.sh",
        "tests/publish-product-forward-results.py",
        "tests/product_forward_evidence.py",
        "tests/execution_contract.py",
        "tests/forward_eval_evidence.py",
        "tests/status_fingerprint.py",
        "tests/tool_access_evidence.py",
        "evals/cases.json",
    ):
        destination = repo / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_root / relative, destination)
    (repo / "VERSION").write_text("0.0.0\n", encoding="ascii")
    return repo


def make_capture(root, name, repo=None):
    capture = root / name
    capture.mkdir(mode=0o700)
    repo = repo or root / "repo"
    runtime_files = []
    for relative in RUNTIME_SNAPSHOT_FILES:
        value = (repo / relative).read_bytes()
        runtime_files.append({"path": relative, "bytes": len(value), "sha256": digest(value)})
    values = {
        "runtime-snapshot.json": json.dumps(
            {"schema_version": 1, "files": runtime_files},
            ensure_ascii=False,
            separators=(",", ":"),
        ) + "\n",
        "generation-prompt.txt": "Generate a handoff.\n",
        "generation-tool-access-evidence.json": json.dumps(
            project_tool_access(
                "product-forward-label-validation",
                "\n".join((
                    "/usr/bin/zsh -lc 'sed -n 1,80p /repo/skill/SKILL.md' in /tmp/fixture",
                    "/usr/bin/zsh -lc 'sed -n 1,220p /repo/skill/references/handoff-contract.md' in /tmp/fixture",
                    "/usr/bin/zsh -lc 'python3 /repo/skill/scripts/status_fingerprint.py --repository . --tracker .project/development/task_plan.md --unit U1 --profile Standard --emit context' in /tmp/fixture",
                    "/usr/bin/zsh -lc 'python3 /repo/skill/scripts/status_fingerprint.py --repository . --tracker .project/development/task_plan.md --unit U1 --profile Standard --emit context' in /tmp/fixture",
                    "/usr/bin/zsh -lc 'python3 /repo/skill/scripts/status_fingerprint.py --repository . --tracker .project/development/task_plan.md --unit U1 --profile Standard --emit preamble' in /tmp/fixture",
                    "/usr/bin/zsh -lc 'python3 /repo/skill/scripts/status_fingerprint.py --repository . --tracker .project/development/task_plan.md --unit U1 --profile Standard --emit preamble' in /tmp/fixture",
                )).encode("utf-8"),
            ),
            ensure_ascii=False,
            separators=(",", ":"),
        ) + "\n",
        "execution-prompt.txt": "Execute the handoff.\n",
        "execution-response.txt": "Implemented owner, regression, gate, and tracker closure.\n",
        "agents-before.md": "# Product fixture\n",
        "design-before.md": "Empty labels raise ValueError.\n",
        "lessons-before.md": "Keep the public path stable.\n",
        "owner-before.py": "def normalize_label(value):\n    return value.strip()\n",
        "owner-after.py": "def normalize_label(value):\n    value = value.strip()\n    if not value:\n        raise ValueError(\"empty label\")\n    return value\n",
        "regression-before.py": "def test_trim():\n    pass\n",
        "regression-after.py": "def test_trim():\n    pass\n\ndef test_rejects_empty():\n    pass\n",
        "tracker-before.md": (
            "tracker_revision: r1\nselection_decision: U1 is dependency-free and closes the only tracked goal\n\n"
            "### U1\n\nstate: Ready\nclaim: none\ndependency: none\n"
            "goal: Reject blank normalized labels at the owner boundary\n"
            "invariants: Preserve trim, TypeError, and public path.\n"
            "next_convergence_condition: G1 passes\nowner: src/normalize_label.py\ngate_refs: G1\n\n"
            "### G1\n\nstatus: pending\nowners: U1\n"
            "command: python3 -m unittest discover -s tests -v\n"
            "inputs_json: [\"src/normalize_label.py\",\"tests/test_normalize_label.py\"]\n"
            "input_fingerprint: __GATE_INPUT_FINGERPRINT__\npassed_evidence: none\n"
            "recovery_condition: Implement U1, run the exact Gate command, and record fresh passing evidence.\n"
        ),
        "tracker-after.md": "tracker_revision: r3\n\n### U1\n\nstate: Complete\nowner: src/normalize_label.py\ngate_refs: G1\n\n### G1\n\nstatus: passed\n",
        "progress-before.md": "# Progress\n",
        "progress-after.md": (
            "# Progress\n"
            "observed_receipt: unit=U1; owner=src/normalize_label.py; transitions=Ready->Claimed,Claimed->In Progress; revision=r1->r2; gate=none; evidence=.project/development/progress.md\n"
            "observed_receipt: unit=U1; owner=src/normalize_label.py; transitions=In Progress->Complete; revision=r2->r3; gate=G1:pending->passed; evidence=.project/development/task_plan.md\n"
            "post_closure_next_unit: none\n"
        ),
        "git-branch-before.txt": "product-forward\n",
        "git-head-before.txt": "c" * 40 + "\n",
        "git-status-before-z.bin": b"",
        "acceptance-command.txt": "python3 -m unittest discover -s tests -v\n",
        "acceptance-output.txt": "Ran 4 tests in 0.001s\n\nOK\n",
        "acceptance-exit.txt": "0\n",
        "git-status-z.bin": b" M src/normalize_label.py\0 M tests/test_normalize_label.py\0",
        "git-diff.patch": (
            "diff --git a/src/normalize_label.py b/src/normalize_label.py\n"
            "--- a/src/normalize_label.py\n+++ b/src/normalize_label.py\n"
            "diff --git a/tests/test_normalize_label.py b/tests/test_normalize_label.py\n"
            "--- a/tests/test_normalize_label.py\n+++ b/tests/test_normalize_label.py\n"
        ),
    }
    input_digests = {
        "src/normalize_label.py": digest(values["owner-before.py"].encode("utf-8")),
        "tests/test_normalize_label.py": digest(values["regression-before.py"].encode("utf-8")),
    }
    values["tracker-before.md"] = values["tracker-before.md"].replace(
        "__GATE_INPUT_FINGERPRINT__",
        gate_input_fingerprint(
            ["src/normalize_label.py", "tests/test_normalize_label.py"], input_digests
        ),
    )
    values["generation-response.txt"] = grounded_generation_response(values)
    values["generation-draft.txt"] = values["generation-response.txt"]
    response_lines = values["generation-response.txt"].splitlines(keepends=True)
    values["generation-assembly-preamble.txt"] = "".join(response_lines[1:11])
    values["generation-assembly-context.json"] = "{}\n"
    assembler_bytes = (repo / "skill/scripts/assemble_handoff.py").read_bytes()
    values["generation-assembly-manifest.json"] = json.dumps({
        "schema_version": 1,
        "mode": "executable",
        "draft_sha256": digest(values["generation-draft.txt"].encode("utf-8")),
        "final_sha256": digest(values["generation-response.txt"].encode("utf-8")),
        "preamble_sha256": digest(values["generation-assembly-preamble.txt"].encode("utf-8")),
        "context_sha256": digest(values["generation-assembly-context.json"].encode("utf-8")),
        "assembler_sha256": digest(assembler_bytes),
    }, ensure_ascii=False, separators=(",", ":")) + "\n"
    for relative, value in values.items():
        path = capture / relative
        if isinstance(value, bytes):
            path.write_bytes(value)
        else:
            path.write_text(value, encoding="utf-8")
    write_capture_manifest(capture)
    return capture


def publish(repo, capture):
    return subprocess.run(
        (sys.executable, str(repo / "tests/publish-product-forward-results.py"), str(capture), str(repo), "0.0.0"),
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
    )


def refresh_generation_assembly(capture, repo):
    final = (capture / "generation-response.txt").read_bytes()
    (capture / "generation-draft.txt").write_bytes(final)
    preamble = b"".join(final.splitlines(keepends=True)[1:11])
    (capture / "generation-assembly-preamble.txt").write_bytes(preamble)
    context = (capture / "generation-assembly-context.json").read_bytes()
    assembler = (repo / "skill/scripts/assemble_handoff.py").read_bytes()
    (capture / "generation-assembly-manifest.json").write_text(json.dumps({
        "schema_version": 1, "mode": "executable",
        "draft_sha256": digest(final), "final_sha256": digest(final),
        "preamble_sha256": digest(preamble), "context_sha256": digest(context),
        "assembler_sha256": digest(assembler),
    }, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def main():
    source_root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix="gci-product-publisher-", dir="/tmp") as temporary:
        root = Path(temporary)
        repo = make_repo(source_root, root, "repo")
        capture = make_capture(root, "capture")
        completed = publish(repo, capture)
        if completed.returncode != 0:
            fail("valid raw capture rejected: " + completed.stderr)
        result = json.loads((repo / "evals/product-forward-results-v0.0.0.json").read_text(encoding="utf-8"))
        if result.get("schema_version") != 4 or result.get("evidence_source") != "publisher-recomputed-v3-prestate-and-observed-bound":
            fail("publisher recomputation provenance")
        if result["metrics"].get("first_effective_action_event_index") != 1:
            fail("first action metric was not derived")
        raw_acceptance = (capture / "acceptance-output.txt").read_bytes()
        if result["evidence"].get("acceptance_output_sha256") != digest(raw_acceptance):
            fail("acceptance digest was not derived")
        if set(result["artifacts"]) != {
            path.name for path in capture.iterdir()
        }:
            fail("raw artifact inventory")

        runtime_tamper = make_capture(root, "runtime-tamper")
        runtime_document = json.loads((runtime_tamper / "runtime-snapshot.json").read_text(encoding="utf-8"))
        runtime_document["files"][0]["sha256"] = "0" * 64
        (runtime_tamper / "runtime-snapshot.json").write_text(
            json.dumps(runtime_document, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        runtime_result = publish(repo, runtime_tamper)
        if runtime_result.returncode == 0 or "runtime snapshot source binding" not in runtime_result.stderr:
            fail("tampered generation runtime snapshot accepted")

        semantic_mutations = {
            "repository-escape": lambda value: value.replace(
                "Repository: .\n", "Repository: ../outside\n"
            ),
            "expanded-scope": lambda value: value.replace(
                '["src/normalize_label.py","tests/test_normalize_label.py"]',
                '["src/normalize_label.py","src/unrelated.py","tests/test_normalize_label.py"]',
            ),
            "fabricated-selection": lambda value: value.replace(
                "Selection basis: U1 is dependency-free and closes the only tracked goal",
                "Selection basis: choose U1 randomly without dependency evidence",
            ).replace(
                "Current executable unit: U1; dependency_evidence=none",
                "Current executable unit: U1; dependency_evidence=fabricated",
            ),
            "ungrounded-inputs": lambda value: value.replace(
                'Authoritative inputs: [".project/development/task_plan.md","AGENTS.md","docs/design.md","src/normalize_label.py","tests/test_normalize_label.py"]',
                'Authoritative inputs: ["README.md"]',
            ),
            "fabricated-trace": lambda value: value.replace(
                "Reject blank normalized labels at the owner boundary -> src/normalize_label.py: currently returns an empty string -> src/normalize_label.py: the documented empty-result guard is absent -> src/normalize_label.py: trim once, add the empty-result guard, and update tests/test_normalize_label.py -> Preserve trim, TypeError, and public path. -> tests/test_normalize_label.py: empty and whitespace-only positive/negative regression -> G1 -> tests/test_normalize_label.py; gate_evidence=none",
                "A -> B -> C -> D -> E -> F -> G -> H",
            ),
            "source-prefixed-fabricated-trace": lambda value: value.replace(
                "Reject blank normalized labels at the owner boundary -> src/normalize_label.py: currently returns an empty string -> src/normalize_label.py: the documented empty-result guard is absent -> src/normalize_label.py: trim once, add the empty-result guard, and update tests/test_normalize_label.py -> Preserve trim, TypeError, and public path. -> tests/test_normalize_label.py: empty and whitespace-only positive/negative regression -> G1 -> tests/test_normalize_label.py; gate_evidence=none",
                "Reject blank normalized labels at the owner boundary -> src/normalize_label.py: FABRICATED baseline -> src/normalize_label.py: FABRICATED gap -> src/normalize_label.py: FABRICATED change -> Preserve trim, TypeError, and public path. -> tests/test_normalize_label.py: FABRICATED test -> G1 -> tests/test_normalize_label.py; gate_evidence=none",
            ),
            "custom-test-bypass": lambda value: value.replace(
                "Action: test: run post-change acceptance and retain its fresh output",
                "Action: observe: run post-change acceptance and retain its fresh output",
            ).replace(
                "Command: python3 -m unittest discover -s tests -v && git diff --check",
                "Command: ./scripts/acceptance.sh",
            ).replace(
                "authorized: user | authorized: user | authorized: AGENTS.md",
                "authorized: user | not authorized: absent | authorized: AGENTS.md",
            ),
        }
        for name, mutate in semantic_mutations.items():
            semantic_repo = make_repo(source_root, root, name + "-repo")
            semantic_capture = make_capture(root, name)
            generated_path = semantic_capture / "generation-response.txt"
            generated_path.write_text(
                mutate(generated_path.read_text(encoding="utf-8")), encoding="utf-8"
            )
            write_capture_manifest(semantic_capture)
            rejected = publish(semantic_repo, semantic_capture)
            if rejected.returncode == 0:
                fail(name + " semantic mutation accepted")

        tamper_repo = make_repo(source_root, root, "tamper-repo")
        tamper = make_capture(root, "tamper")
        (tamper / "acceptance-output.txt").write_text("forged pass\n", encoding="utf-8")
        rejected = publish(tamper_repo, tamper)
        if rejected.returncode == 0 or "capture artifact binding" not in rejected.stderr:
            fail("post-manifest raw artifact tamper accepted")

        declaration_repo = make_repo(source_root, root, "declaration-repo")
        declaration = make_capture(root, "declaration")
        (declaration / "product-result.json").write_text('{"metrics":{"closure_rate":1.0}}\n', encoding="utf-8")
        rejected = publish(declaration_repo, declaration)
        if rejected.returncode == 0 or "unexpected capture artifact" not in rejected.stderr:
            fail("runner-aggregated metrics accepted")

        owner_repo = make_repo(source_root, root, "owner-repo")
        owner = make_capture(root, "owner")
        tracker = (owner / "tracker-after.md").read_text(encoding="utf-8").replace(
            "owner: src/normalize_label.py", "owner: src/other.py"
        )
        (owner / "tracker-after.md").write_text(tracker, encoding="utf-8")
        write_capture_manifest(owner)
        rejected = publish(owner_repo, owner)
        if rejected.returncode == 0 or "owner conflict" not in rejected.stderr:
            fail("conflicting owner evidence accepted")

        next_repo = make_repo(source_root, root, "next-repo")
        next_capture = make_capture(root, "next")
        progress = (next_capture / "progress-after.md").read_text(encoding="utf-8").replace(
            "post_closure_next_unit: none", "post_closure_next_unit: U2"
        )
        (next_capture / "progress-after.md").write_text(progress, encoding="utf-8")
        write_capture_manifest(next_capture)
        rejected = publish(next_repo, next_capture)
        if rejected.returncode == 0 or "post-closure next mismatch" not in rejected.stderr:
            fail("post-closure next mismatch accepted")

        false_next_repo = make_repo(source_root, root, "false-next-repo")
        false_next = make_capture(root, "false-next")
        progress = (false_next / "progress-after.md").read_text(encoding="utf-8").replace(
            "post_closure_next_unit: none", "post_closure_next_unit: U2"
        )
        generated = (false_next / "generation-response.txt").read_text(encoding="utf-8").replace(
            "Post-closure next unit: none;", "Post-closure next unit: U2;"
        )
        (false_next / "progress-after.md").write_text(progress, encoding="utf-8")
        (false_next / "generation-response.txt").write_text(generated, encoding="utf-8")
        refresh_generation_assembly(false_next, false_next_repo)
        write_capture_manifest(false_next)
        rejected = publish(false_next_repo, false_next)
        if rejected.returncode == 0 or not any(
            marker in rejected.stderr
            for marker in ("derived post-closure next", "ungrounded post closure next")
        ):
            fail("mutually consistent but nonexistent next unit accepted")

        omitted_next_repo = make_repo(source_root, root, "omitted-next-repo")
        omitted_next = make_capture(root, "omitted-next")
        tracker = (omitted_next / "tracker-after.md").read_text(encoding="utf-8") + (
            "\n### U2\n\nstate: Ready\ndependency: U1\nowner: docs/follow-up.md\n"
        )
        (omitted_next / "tracker-after.md").write_text(tracker, encoding="utf-8")
        write_capture_manifest(omitted_next)
        rejected = publish(omitted_next_repo, omitted_next)
        if rejected.returncode == 0 or "derived post-closure next" not in rejected.stderr:
            fail("ready derived next unit omitted")

        revision_repo = make_repo(source_root, root, "revision-repo")
        revision = make_capture(root, "revision")
        progress = (revision / "progress-after.md").read_text(encoding="utf-8").replace(
            "revision=r1->r2", "revision=r1->r9"
        ).replace("revision=r2->r3", "revision=r9->r3")
        (revision / "progress-after.md").write_text(progress, encoding="utf-8")
        write_capture_manifest(revision)
        rejected = publish(revision_repo, revision)
        if rejected.returncode == 0 or "revision did not increment once" not in rejected.stderr:
            fail("non-unit tracker revision increment accepted")

        stub_repo = make_repo(source_root, root, "stub-repo")
        stub = make_capture(root, "stub")
        (stub / "generation-response.txt").write_text(
            "Selected unit: U1\n```text\nstructured handoff\n```\n", encoding="utf-8"
        )
        write_capture_manifest(stub)
        rejected = publish(stub_repo, stub)
        if rejected.returncode == 0 or not any(
            marker in rejected.stderr for marker in ("generated handoff", "generation assembly evidence")
        ):
            fail("stub generated handoff accepted")

        mismatch_repo = make_repo(source_root, root, "mismatch-repo")
        mismatch = make_capture(root, "mismatch")
        generated = (mismatch / "generation-response.txt").read_text(encoding="utf-8").replace(
            "transitions=In Progress->Complete; from_revision=observed-prior; gate=G1:pending->passed",
            "transitions=In Progress->Failed; from_revision=observed-prior; gate=G1:pending->failed",
        )
        (mismatch / "generation-response.txt").write_text(generated, encoding="utf-8")
        refresh_generation_assembly(mismatch, mismatch_repo)
        write_capture_manifest(mismatch)
        rejected = publish(mismatch_repo, mismatch)
        if rejected.returncode == 0 or not any(
            marker in rejected.stderr for marker in ("generated and observed", "closure protocol")
        ):
            fail("generated/observed mismatch accepted")

        snapshot_repo = make_repo(source_root, root, "snapshot-repo")
        snapshot = make_capture(root, "snapshot")
        generated = (snapshot / "generation-response.txt").read_text(encoding="utf-8").replace(
            "branch=product-forward", "branch=fabricated-branch", 1
        )
        (snapshot / "generation-response.txt").write_text(generated, encoding="utf-8")
        refresh_generation_assembly(snapshot, snapshot_repo)
        write_capture_manifest(snapshot)
        rejected = publish(snapshot_repo, snapshot)
        if rejected.returncode == 0 or "ungrounded snapshot" not in rejected.stderr:
            fail("fabricated generated snapshot accepted")

        inventory_repo = make_repo(source_root, root, "inventory-repo")
        inventory_capture = make_capture(root, "inventory")
        generated = (inventory_capture / "generation-response.txt").read_text(encoding="utf-8")
        generated = generated.replace(
            "Unit counts: Complete=0; In Progress=0; Claimed=0; Ready=1; Blocked=0; Failed=0",
            "Unit counts: Complete=0; In Progress=1; Claimed=0; Ready=0; Blocked=0; Failed=0",
        ).replace('"id":"U1","state":"Ready"', '"id":"U1","state":"In Progress"')
        (inventory_capture / "generation-response.txt").write_text(generated, encoding="utf-8")
        refresh_generation_assembly(inventory_capture, inventory_repo)
        write_capture_manifest(inventory_capture)
        rejected = publish(inventory_repo, inventory_capture)
        if rejected.returncode == 0 or "ungrounded open inventory" not in rejected.stderr:
            fail("fabricated generated inventory accepted")

        ledger_repo = make_repo(source_root, root, "ledger-repo")
        ledger_capture = make_capture(root, "ledger")
        generated = (ledger_capture / "generation-response.txt").read_text(encoding="utf-8")
        generated = re.sub(r'"sha256":"[0-9a-f]{64}"', '"sha256":"' + "0" * 64 + '"', generated, count=1)
        (ledger_capture / "generation-response.txt").write_text(generated, encoding="utf-8")
        refresh_generation_assembly(ledger_capture, ledger_repo)
        write_capture_manifest(ledger_capture)
        rejected = publish(ledger_repo, ledger_capture)
        if rejected.returncode == 0 or "ungrounded evidence ledger" not in rejected.stderr:
            fail("fabricated evidence digest accepted")

        diff_repo = make_repo(source_root, root, "diff-repo")
        diff_capture = make_capture(root, "diff")
        with (diff_capture / "git-diff.patch").open("a", encoding="utf-8") as sink:
            sink.write("diff --git a/src/extra.py b/src/renamed.py\n")
        write_capture_manifest(diff_capture)
        rejected = publish(diff_repo, diff_capture)
        if rejected.returncode == 0 or "Git diff manifest" not in rejected.stderr:
            fail("unequal diff header paths accepted")

        clarification_repo = make_repo(source_root, root, "clarification-repo")
        clarification = make_capture(root, "clarification")
        (clarification / "execution-response.txt").write_text(
            "Please clarify. Implemented owner, regression, gate, and tracker closure.\n",
            encoding="utf-8",
        )
        write_capture_manifest(clarification)
        rejected = publish(clarification_repo, clarification)
        if rejected.returncode == 0 or "metric threshold" not in rejected.stderr:
            fail("successful closure with invalid clarification accepted")
    print("PASS: product publisher recomputes raw evidence and rejects false closure")


if __name__ == "__main__":
    main()
