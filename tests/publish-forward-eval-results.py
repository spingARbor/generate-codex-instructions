#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys

sys.dont_write_bytecode = True
from forward_eval_evidence import (
    canonical_json,
    contains_sensitive_evidence,
    manifest_file_sha256,
    regular_bytes,
    validate_generation_evidence,
    validate_grounding_source_publication,
    validate_side_effect_evidence,
    validate_snapshot_evidence,
    validate_state_manifest,
)
from published_result_validator import (
    ResultValidationError,
    representative_bindings,
    validate_product_result,
    validate_repository,
)
from execution_contract import (
    ContractError,
    validate_forward_case,
    validate_generic_handoff_grounding,
)

VERSION_RE = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")
COMMAND_TEMPLATE = "codex exec --ephemeral --sandbox workspace-write --add-dir <disposable-fixture> -C <disposable-fixture> -o <evaluator-output> -"

def stop(label):
    raise SystemExit("FAIL: forward eval publish: " + label)

def digest(value):
    return hashlib.sha256(value).hexdigest()

def repository_json(path, label):
    value = regular_bytes(path, label)

    def reject_duplicate_keys(pairs):
        document = {}
        for key, item in pairs:
            if key in document:
                stop(label + " duplicate key")
            document[key] = item
        return document

    try:
        return json.loads(value.decode("utf-8"), object_pairs_hook=reject_duplicate_keys)
    except (UnicodeError, json.JSONDecodeError):
        stop(label + " parse")

def physical_directory(path, label, expected_parent=None):
    try:
        metadata = path.lstat()
    except OSError:
        stop(label)
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid():
        stop(label)
    try:
        physical = path.resolve(strict=True)
        if expected_parent is not None and (path.parent != expected_parent or physical.parent != expected_parent.resolve(strict=True)):
            stop(label + " containment")
    except (OSError, ValueError):
        stop(label + " containment")
    return physical

def require_absent(path, label):
    try:
        path.lstat()
    except FileNotFoundError:
        return
    except OSError:
        stop(label)
    stop(label)

def prepare_artifact_destination(repo_root, version):
    if VERSION_RE.fullmatch(version) is None:
        stop("artifact version")
    physical_directory(repo_root, "repository root")
    eval_root = repo_root / "evals"
    physical_directory(eval_root, "eval directory", repo_root)
    parent = eval_root / "artifacts"
    try:
        parent.lstat()
    except FileNotFoundError:
        parent.mkdir(mode=0o755)
    except OSError:
        stop("artifact parent")
    physical_directory(parent, "artifact parent", eval_root)
    final = parent / ("v" + version)
    temporary = parent / (".v" + version + ".tmp-" + str(os.getpid()))
    require_absent(final, "release artifact target already exists")
    require_absent(temporary, "temporary artifact target already exists")
    return parent, final, temporary

def validate_publishable_bytes(value, label):
    if any(marker in value for marker in (b"/tmp/", b"/home/", b"/Users/")) or contains_sensitive_evidence(value):
        stop(label + " contains forbidden evidence")

def copy_artifact(source, destination, label):
    value = regular_bytes(source, label)
    validate_publishable_bytes(value, label)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with destination.open("xb") as sink:
        sink.write(value)
    destination.chmod(0o644)

def artifact_reference(repo_root, path):
    value = regular_bytes(path, "published artifact")
    relative = path.relative_to(repo_root).as_posix()
    return {"path": relative, "sha256": digest(value), "bytes": len(value)}

def published_reference(repo_root, temporary_path, published_path):
    reference = artifact_reference(repo_root, temporary_path)
    reference["path"] = published_path.relative_to(repo_root).as_posix()
    return reference

def restore_bytes(path, value):
    temporary = path.with_name("." + path.name + ".restore-" + str(os.getpid()))
    with temporary.open("xb") as sink:
        sink.write(value)
    os.replace(temporary, path)

def response_parts(value):
    lines = value.decode("utf-8").splitlines(keepends=True)
    active = None
    regions = []
    for index, raw_line in enumerate(lines):
        line = raw_line.rstrip("\r\n")
        if active is not None:
            if re.fullmatch(re.escape(active[0]) + "{" + str(active[1]) + ",}[ \t]*", line):
                regions.append((active[2], index, active[3]))
                active = None
            continue
        opening = re.fullmatch(r"(`{3,})(.*)", line)
        if opening:
            marker = opening.group(1)
            active = (marker[0], len(marker), index, opening.group(2).strip())
    if active is not None or len(regions) > 1:
        stop("published response fence")
    if not regions:
        return value, b""
    opening, closing, info = regions[0]
    if info != "text": stop("published response fence language")
    return "".join(lines[:opening]).encode("utf-8"), "".join(lines[opening + 1:closing]).encode("utf-8")

def verify_snapshot(run_root, repo_root):
    snapshot = run_root / "snapshot"
    manifest = canonical_json(snapshot / "manifest.json")
    if tuple(manifest) != ("schema_version", "files") or manifest["schema_version"] != 1:
        stop("snapshot manifest")
    expected = {
        "skill/SKILL.md": repo_root / "skill/SKILL.md",
        "skill/scripts/status_fingerprint.py": repo_root / "skill/scripts/status_fingerprint.py",
        "runner.sh": repo_root / "tests/run-forward-evals.sh",
        "cases.json": repo_root / "evals/cases.json",
        "status_fingerprint.py": repo_root / "tests/status_fingerprint.py",
        "execution_contract.py": repo_root / "tests/execution_contract.py",
        "forward_eval_evidence.py": repo_root / "tests/forward_eval_evidence.py",
    }
    seen = set()
    for entry in manifest.get("files", []):
        if tuple(entry) != ("path", "bytes", "sha256") or entry["path"] not in expected or entry["path"] in seen:
            stop("snapshot entry")
        value = regular_bytes(snapshot / entry["path"], "snapshot " + entry["path"])
        source = regular_bytes(expected[entry["path"]], "source " + entry["path"])
        if value != source or entry["bytes"] != len(value) or entry["sha256"] != digest(value):
            stop("snapshot binding " + entry["path"])
        seen.add(entry["path"])
    if seen != set(expected): stop("snapshot completeness")
    return {path: digest(regular_bytes(source, path)) for path, source in expected.items()}

def main():
    if len(sys.argv) != 4:
        stop("usage: publish-forward-eval-results.py RUN_ROOT REPO_ROOT VERSION")
    run_argument = Path(sys.argv[1])
    repo_root = Path(sys.argv[2]).resolve(strict=True)
    version = sys.argv[3]
    if run_argument.is_symlink(): stop("run root symlink")
    run_root = run_argument.resolve(strict=True)
    metadata = run_root.lstat()
    if not str(run_root).startswith("/tmp/") or not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
        stop("private run root")
    if version != (repo_root / "VERSION").read_text(encoding="ascii").strip(): stop("release version")
    result_path = repo_root / ("evals/results-v" + version + ".json")
    representative_path = repo_root / ("evals/representative-forward-results-v" + version + ".json")
    previous_result = regular_bytes(result_path, "previous release result")
    previous_representative = regular_bytes(representative_path, "previous representative result")
    snapshot_digests = verify_snapshot(run_root, repo_root)
    corpus = repository_json(repo_root / "evals/cases.json", "corpus")
    expected_cases = {item["id"] for item in corpus.get("cases", [])} - {"product-forward-closure"}
    actual_cases = {path.name for path in (run_root / "cases").iterdir() if not path.name.startswith(".")}
    if actual_cases != expected_cases:
        stop("fresh case set")
    try:
        product = json.loads(regular_bytes(repo_root / ("evals/product-forward-results-v" + version + ".json"), "product evidence").decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        stop("product evidence")
    try:
        if not validate_product_result(repo_root, version, product):
            stop("product evidence status")
    except ResultValidationError as error:
        stop("product evidence: " + str(error))
    artifact_parent, final_root, temp_root = prepare_artifact_destination(repo_root, version)
    temp_root.mkdir(mode=0o700)
    try:
        copy_artifact(run_root / "snapshot/manifest.json", temp_root / "snapshot-manifest.json", "snapshot manifest")
        case_documents = []
        cases_root = run_root / "cases"
        for source_root in sorted(cases_root.iterdir(), key=lambda p: p.name):
            if source_root.name.startswith(".") or not source_root.is_dir() or source_root.is_symlink():
                stop("case directory")
            if regular_bytes(source_root / ".complete", "case completion") != b"complete\n":
                stop("case not complete")
            destination = temp_root / source_root.name
            destination.mkdir(mode=0o700)
            names = ("prompt.txt", "fixture-manifest.json", "post-state-manifest.json", "grounding-sources.json", "generation-evidence.json", "side-effect-evidence.json", "snapshot-evidence.json")
            for name in names:
                copy_artifact(source_root / name, destination / name, source_root.name + " " + name)
            generation = canonical_json(source_root / "generation-evidence.json")
            validate_generation_evidence(generation)
            fixture_manifest = canonical_json(source_root / "fixture-manifest.json")
            post_state_manifest = canonical_json(source_root / "post-state-manifest.json")
            validate_state_manifest(fixture_manifest, source_root.name)
            validate_state_manifest(post_state_manifest, source_root.name)
            grounding_sources = canonical_json(source_root / "grounding-sources.json")
            validate_grounding_source_publication(grounding_sources, source_root.name)
            snapshot = canonical_json(source_root / "snapshot-evidence.json")
            validate_snapshot_evidence(snapshot, source_root.name, (
                snapshot_digests["skill/SKILL.md"], snapshot_digests["runner.sh"], snapshot_digests["cases.json"],
            ))
            side_effect = canonical_json(source_root / "side-effect-evidence.json")
            validate_side_effect_evidence(
                side_effect, source_root.name, generation["generation_read_only"],
                fixture_manifest, post_state_manifest,
            )
            if generation["case_id"] != source_root.name:
                stop("generation case identity")
            if generation["snapshot_manifest_sha256"] != digest(regular_bytes(run_root / "snapshot/manifest.json", "snapshot manifest")):
                stop("generation snapshot manifest binding")
            if generation["post_state_manifest_sha256"] != digest(regular_bytes(source_root / "post-state-manifest.json", "post-state manifest")):
                stop("generation post-state manifest binding")
            if generation["grounding_sources_sha256"] != digest(regular_bytes(source_root / "grounding-sources.json", "grounding sources")):
                stop("generation grounding source binding")
            if generation["tracker_before_sha256"] != manifest_file_sha256(fixture_manifest, ".project/development/task_plan.md"):
                stop("generation tracker-before binding")
            if generation["tracker_after_sha256"] != manifest_file_sha256(post_state_manifest, ".project/development/task_plan.md"):
                stop("generation tracker-after binding")
            responses = []
            response_values = []
            for response in sorted(source_root.glob("response-*.txt")):
                copy_artifact(source_root / response.name, destination / response.name, source_root.name + " " + response.name)
                responses.append(published_reference(repo_root, destination / response.name, final_root / source_root.name / response.name))
                response_values.append(regular_bytes(source_root / response.name, source_root.name + " response"))
            if len(response_values) != len(generation["response_sha256"]):
                stop("generation response count")
            for index, value in enumerate(response_values):
                summary, body = response_parts(value)
                if digest(value) != generation["response_sha256"][index] or len(value) != generation["response_bytes"][index]:
                    stop("generation response binding")
                if digest(summary) != generation["summary_sha256"][index] or digest(body) != generation["body_sha256"][index]:
                    stop("generation artifact binding")
            try:
                handoff = validate_forward_case(source_root.name, response_values[-1].decode("utf-8"))
                if handoff is not None:
                    validate_generic_handoff_grounding(
                        source_root.name,
                        handoff,
                        fixture_manifest,
                        grounding_sources,
                    )
                    if generation["status_fingerprint_sha256"] != handoff["snapshot"]["status_fingerprint"]:
                        stop("generation status fingerprint binding")
            except (UnicodeError, ContractError) as error:
                stop("case semantic replay " + source_root.name + ": " + str(error))
            artifacts = {}
            for key, name in (("prompt", "prompt.txt"), ("fixture_manifest", "fixture-manifest.json"), ("post_state_manifest", "post-state-manifest.json"), ("grounding_sources", "grounding-sources.json"), ("generation_evidence", "generation-evidence.json"), ("side_effect_evidence", "side-effect-evidence.json"), ("snapshot_evidence", "snapshot-evidence.json")):
                artifacts[key] = published_reference(repo_root, destination / name, final_root / source_root.name / name)
            artifacts["responses"] = responses
            case_documents.append({"id": source_root.name, "outcome": "pass", "artifacts": artifacts, "session_command": COMMAND_TEMPLATE})
        physical_directory(temp_root, "temporary artifact root", artifact_parent)
        require_absent(final_root, "release artifact target already exists")
        os.replace(temp_root, final_root)
    except BaseException:
        if temp_root.exists() and not temp_root.is_symlink(): shutil.rmtree(temp_root)
        raise
    bindings = {
        "skill": artifact_reference(repo_root, repo_root / "skill/SKILL.md"),
        "runtime_fingerprint": artifact_reference(repo_root, repo_root / "skill/scripts/status_fingerprint.py"),
        "runner": artifact_reference(repo_root, repo_root / "tests/run-forward-evals.sh"),
        "corpus": artifact_reference(repo_root, repo_root / "evals/cases.json"),
        "status_fingerprint": artifact_reference(repo_root, repo_root / "tests/status_fingerprint.py"),
        "execution_contract": artifact_reference(repo_root, repo_root / "tests/execution_contract.py"),
        "forward_eval_evidence": artifact_reference(repo_root, repo_root / "tests/forward_eval_evidence.py"),
        "snapshot_manifest": artifact_reference(repo_root, final_root / "snapshot-manifest.json"),
    }
    result = {
        "schema_version": 7,
        "version": version,
        "status": "fresh-eval-passed",
        "runner": {"binary": "codex", "command_template": COMMAND_TEMPLATE, "snapshot_protocol": "read-only-snapshot-v2"},
        "runtime": ["skill/SKILL.md", "skill/agents/openai.yaml", "skill/scripts/status_fingerprint.py"],
        "bindings": bindings,
        "cases": case_documents,
        "metrics": product["metrics"],
        "limitations": ["Exact-response audit is performed only after host/evaluator capture; generation does not claim delivery."],
        "release_authorized": True,
    }
    temporary_result = result_path.with_name("." + result_path.name + ".tmp-" + str(os.getpid()))
    representative = {
        "schema_version": 4,
        "version": version,
        "status": "fresh-eval-passed",
        "case": "chinese-mixed-state-first-delivery",
        "outcome": "pass",
        "artifacts": next(item["artifacts"] for item in case_documents if item["id"] == "chinese-mixed-state-first-delivery"),
        "evidence_source": "aggregate-publisher-semantic-replay-v3-poststate-bound",
        "bindings": representative_bindings({
            "skill_sha256": bindings["skill"]["sha256"],
            "runtime_fingerprint_sha256": bindings["runtime_fingerprint"]["sha256"],
            "forward_runner_sha256": bindings["runner"]["sha256"],
            "corpus_sha256": bindings["corpus"]["sha256"],
            "fingerprint_sha256": bindings["status_fingerprint"]["sha256"],
            "contract_sha256": bindings["execution_contract"]["sha256"],
            "forward_evidence_sha256": bindings["forward_eval_evidence"]["sha256"],
        }),
        "release_authorized": False,
    }
    temporary_representative = representative_path.with_name("." + representative_path.name + ".tmp-" + str(os.getpid()))
    try:
        with temporary_result.open("x", encoding="utf-8") as sink:
            json.dump(result, sink, ensure_ascii=False, indent=2); sink.write("\n")
        with temporary_representative.open("x", encoding="utf-8") as sink:
            json.dump(representative, sink, ensure_ascii=False, indent=2); sink.write("\n")
        os.replace(temporary_representative, representative_path)
        os.replace(temporary_result, result_path)
        validate_repository(repo_root, require_release=True)
    except BaseException as error:
        restore_bytes(result_path, previous_result)
        restore_bytes(representative_path, previous_representative)
        if final_root.exists() and not final_root.is_symlink():
            shutil.rmtree(final_root)
        if isinstance(error, ResultValidationError):
            stop("post-publish replay: " + str(error))
        raise

if __name__ == "__main__":
    main()
