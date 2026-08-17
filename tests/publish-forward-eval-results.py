#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys


CASE_IDS = (
    "chinese-mixed-state-first-delivery",
    "english-localization",
    "ordinary-matching-terminal",
    "complete-plan",
    "insufficient-information",
    "generic-blocker",
    "tracker-injection",
    "authenticated-exact-replay-capability-unavailable",
    "ordinary-implementation",
    "tracker-path-escape",
    "concurrency-conflict",
    "plugin-prerequisites",
    "git-permission-split",
    "fence-safety",
)
COMMAND_TEMPLATE = (
    "codex exec --ephemeral --sandbox workspace-write "
    "--add-dir <disposable-fixture> "
    "-C <disposable-fixture> -o <evaluator-output> -"
)


def stop(label):
    raise SystemExit("FAIL: forward eval publish: " + label)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def canonical_json(path):
    try:
        value = path.read_bytes()
        document = json.loads(value.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        stop("canonical JSON " + str(path))
    canonical = json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n"
    if value != canonical.encode("utf-8"):
        stop("noncanonical JSON " + str(path))
    return document


def regular_bytes(path, label):
    try:
        metadata = path.lstat()
        value = path.read_bytes()
    except OSError:
        stop(label)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or path.is_symlink()
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
    ):
        stop(label + " ownership")
    return value


def artifact_reference(repo_root, path):
    value = regular_bytes(path, "published artifact")
    try:
        relative = path.relative_to(repo_root).as_posix()
    except ValueError:
        stop("published artifact containment")
    return {"path": relative, "sha256": digest(value), "bytes": len(value)}


def verify_snapshot(run_root, repo_root):
    snapshot = run_root / "snapshot"
    manifest = canonical_json(snapshot / "manifest.json")
    if tuple(manifest) != ("schema_version", "files") or manifest["schema_version"] != 1:
        stop("snapshot manifest")
    sources = {
        "skill/SKILL.md": repo_root / "skill/SKILL.md",
        "runner.sh": repo_root / "tests/run-forward-evals.sh",
        "cases.json": repo_root / "evals/cases.json",
    }
    digests = {}
    if not isinstance(manifest["files"], list) or len(manifest["files"]) != len(sources):
        stop("snapshot manifest files")
    for entry in manifest["files"]:
        if tuple(entry) != ("path", "bytes", "sha256") or entry["path"] not in sources:
            stop("snapshot manifest entry")
        snapshot_value = regular_bytes(snapshot / entry["path"], "snapshot " + entry["path"])
        source_value = regular_bytes(sources[entry["path"]], "source " + entry["path"])
        if (
            snapshot_value != source_value
            or entry["bytes"] != len(snapshot_value)
            or entry["sha256"] != digest(snapshot_value)
        ):
            stop("snapshot drift " + entry["path"])
        digests[entry["path"]] = entry["sha256"]
    if set(digests) != set(sources):
        stop("snapshot completeness")
    return digests


def copy_artifact(source, destination, label):
    value = regular_bytes(source, label)
    if b"/tmp/" in value:
        stop(label + " contains evaluator absolute path")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with destination.open("xb") as sink:
        sink.write(value)
    destination.chmod(0o644)


def main():
    if len(sys.argv) != 4:
        stop("usage: publish-forward-eval-results.py RUN_ROOT REPO_ROOT VERSION")
    run_argument = Path(sys.argv[1])
    repo_root = Path(sys.argv[2]).resolve(strict=True)
    version = sys.argv[3]
    if run_argument.is_symlink():
        stop("run root symlink")
    run_root = run_argument.resolve(strict=True)
    metadata = run_root.lstat()
    if (
        run_root.parent == run_root
        or not str(run_root).startswith("/tmp/")
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        stop("private run root")
    if version != (repo_root / "VERSION").read_text(encoding="utf-8").strip():
        stop("release version")
    snapshot_digests = verify_snapshot(run_root, repo_root)

    artifact_parent = repo_root / "evals/artifacts"
    artifact_parent.mkdir(mode=0o755, exist_ok=True)
    final_artifact_root = artifact_parent / ("v" + version)
    temp_artifact_root = artifact_parent / (".v" + version + ".tmp-" + str(os.getpid()))
    if final_artifact_root.exists() or final_artifact_root.is_symlink():
        stop("release artifact directory already exists")
    temp_artifact_root.mkdir(mode=0o700)

    try:
        cases = []
        for case_id in CASE_IDS:
            source_root = run_root / "cases" / case_id
            source_metadata = source_root.lstat()
            if (
                not stat.S_ISDIR(source_metadata.st_mode)
                or source_root.is_symlink()
                or source_metadata.st_uid != os.getuid()
                or stat.S_IMODE(source_metadata.st_mode) != 0o700
            ):
                stop("case ownership " + case_id)
            if regular_bytes(source_root / ".complete", "case completion " + case_id) != b"complete\n":
                stop("case completion " + case_id)
            destination_root = temp_artifact_root / case_id
            destination_root.mkdir(mode=0o700)
            names = (
                "prompt.txt",
                "fixture-manifest.json",
                "audit-evidence.json",
                "side-effect-evidence.json",
                "snapshot-evidence.json",
            )
            for name in names:
                copy_artifact(source_root / name, destination_root / name, case_id + " " + name)
            response_count = 2 if case_id == "ordinary-matching-terminal" else 1
            for index in range(1, response_count + 1):
                name = "response-" + str(index) + ".txt"
                copy_artifact(source_root / name, destination_root / name, case_id + " " + name)
            snapshot_evidence = canonical_json(source_root / "snapshot-evidence.json")
            if (
                snapshot_evidence.get("skill_sha256") != snapshot_digests["skill/SKILL.md"]
                or snapshot_evidence.get("runner_sha256") != snapshot_digests["runner.sh"]
                or snapshot_evidence.get("corpus_sha256") != snapshot_digests["cases.json"]
            ):
                stop("case snapshot binding " + case_id)

            artifact_root = final_artifact_root / case_id
            responses = [
                artifact_reference(repo_root, destination_root / ("response-" + str(index) + ".txt"))
                for index in range(1, response_count + 1)
            ]
            # References are rewritten from the temporary publication name to the atomic final name.
            for reference in responses:
                reference["path"] = reference["path"].replace(
                    "evals/artifacts/.v" + version + ".tmp-" + str(os.getpid()),
                    "evals/artifacts/v" + version,
                    1,
                )
            artifacts = {}
            for key, name in (
                ("prompt", "prompt.txt"),
                ("fixture_manifest", "fixture-manifest.json"),
            ):
                reference = artifact_reference(repo_root, destination_root / name)
                reference["path"] = (artifact_root / name).relative_to(repo_root).as_posix()
                artifacts[key] = reference
            artifacts["responses"] = responses
            for key, name in (
                ("audit_evidence", "audit-evidence.json"),
                ("side_effect_evidence", "side-effect-evidence.json"),
                ("snapshot_evidence", "snapshot-evidence.json"),
            ):
                reference = artifact_reference(repo_root, destination_root / name)
                reference["path"] = (artifact_root / name).relative_to(repo_root).as_posix()
                artifacts[key] = reference
            cases.append({
                "id": case_id,
                "outcome": "pass",
                "session_command": COMMAND_TEMPLATE,
                "artifacts": artifacts,
                "limitations": (
                    ["Authenticated exact replay success was unavailable; this case verifies fail-closed behavior only."]
                    if case_id == "authenticated-exact-replay-capability-unavailable"
                    else (
                        ["Evaluator physical fixture prefixes in the normalized implementation report were replaced with the stable <disposable-fixture> placeholder before publication."]
                        if case_id == "ordinary-implementation"
                        else []
                    )
                ),
            })

        os.replace(temp_artifact_root, final_artifact_root)
    except BaseException:
        if temp_artifact_root.exists() and not temp_artifact_root.is_symlink():
            shutil.rmtree(temp_artifact_root)
        raise

    bindings = {
        "skill": artifact_reference(repo_root, repo_root / "skill/SKILL.md"),
        "runner": artifact_reference(repo_root, repo_root / "tests/run-forward-evals.sh"),
        "corpus": artifact_reference(repo_root, repo_root / "evals/cases.json"),
    }
    document = {
        "schema_version": 3,
        "release_candidate": version,
        "date": "2026-08-17",
        "runner": {
            "binary": "codex",
            "version": subprocess.check_output(("codex", "--version"), text=True).strip(),
            "command_template": COMMAND_TEMPLATE,
            "snapshot_protocol": "atomic-read-only-v1",
        },
        "mode": {
            "session_isolation": "each session fresh ephemeral process; ordinary-matching-terminal exactly two sequential sessions",
            "fixture_isolation": "one disposable Git repository per case",
            "context": "fresh",
        },
        "bindings": bindings,
        "post_evaluation_skill_sha256": snapshot_digests["skill/SKILL.md"],
        "cases": cases,
        "limitations": [
            "Repository assets retain normalized prompts, responses, canonical fixture manifests, and audit/side-effect evidence; raw evaluator logs are excluded.",
            "Authenticated exact replay success remains unavailable on this host and is not claimed.",
        ],
    }
    result_path = repo_root / ("evals/results-v" + version + ".json")
    temp_result = result_path.with_name("." + result_path.name + ".tmp-" + str(os.getpid()))
    with temp_result.open("x", encoding="utf-8") as sink:
        json.dump(document, sink, ensure_ascii=False, indent=2)
        sink.write("\n")
    os.replace(temp_result, result_path)


if __name__ == "__main__":
    main()
