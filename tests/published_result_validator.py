#!/usr/bin/env python3
"""Independently replay checked-in evaluation results from archived artifacts."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

from forward_eval_evidence import (
    EvidenceFailure,
    contains_sensitive_evidence,
    manifest_file_sha256,
    validate_generation_evidence,
    validate_assembly_evidence,
    validate_grounding_source_publication,
    validate_side_effect_evidence,
    validate_snapshot_evidence,
    validate_state_manifest,
)
from product_forward_evidence import (
    ProductEvidenceError,
    RAW_ARTIFACTS,
    derive_product_result,
    validate_runtime_snapshot,
)
from execution_contract import (
    ContractError,
    validate_forward_case,
    validate_generic_handoff_grounding,
)
from tool_access_evidence import ToolAccessError, validate_tool_access


class ResultValidationError(ValueError):
    pass


COMMAND_TEMPLATE = "codex exec --ephemeral --sandbox workspace-write --add-dir <disposable-fixture> -C <disposable-fixture> -o <evaluator-output> -"
GENERIC_ARTIFACTS = {
    "prompt": "prompt.txt",
    "draft": "draft.txt",
    "assembly_manifest": "assembly-manifest.json",
    "assembly_preamble": "assembly-preamble.txt",
    "assembly_context": "assembly-context.json",
    "fixture_manifest": "fixture-manifest.json",
    "post_state_manifest": "post-state-manifest.json",
    "grounding_sources": "grounding-sources.json",
    "generation_evidence": "generation-evidence.json",
    "side_effect_evidence": "side-effect-evidence.json",
    "snapshot_evidence": "snapshot-evidence.json",
    "tool_access_evidence": "tool-access-evidence.json",
}


def digest(value):
    return hashlib.sha256(value).hexdigest()


def _regular_bytes(path, label):
    try:
        metadata = path.lstat()
        value = path.read_bytes()
    except OSError as error:
        raise ResultValidationError(label) from error
    if (
        not stat.S_ISREG(metadata.st_mode)
        or path.is_symlink()
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
    ):
        raise ResultValidationError(label + " ownership")
    return value


def _json(path, label, *, compact=False):
    raw = _regular_bytes(path, label)
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ResultValidationError(label + " JSON") from error
    if compact:
        expected = (json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        if raw != expected:
            raise ResultValidationError(label + " canonical bytes")
    return document


def _safe_relative(value, prefix):
    if not isinstance(value, str) or value.startswith("/") or "\\" in value:
        raise ResultValidationError("artifact path")
    path = PurePosixPath(value)
    if path.as_posix() != value or any(part in ("", ".", "..") for part in path.parts):
        raise ResultValidationError("artifact path normalization")
    if not value.startswith(prefix + "/"):
        raise ResultValidationError("artifact path containment")
    return path


def _reference(repo_root, reference, expected_path, *, trusted_source=False):
    if not isinstance(reference, dict) or tuple(reference) != ("path", "sha256", "bytes"):
        raise ResultValidationError("artifact reference schema")
    if reference["path"] != expected_path:
        raise ResultValidationError("artifact reference path")
    _safe_relative(reference["path"], expected_path.rsplit("/", 1)[0])
    value = _regular_bytes(repo_root / reference["path"], "artifact " + expected_path)
    if reference["sha256"] != digest(value) or reference["bytes"] != len(value):
        raise ResultValidationError("artifact reference binding " + expected_path)
    if not trusted_source and contains_sensitive_evidence(value):
        raise ResultValidationError("artifact contains sensitive marker " + expected_path)
    return value


def _response_parts(value):
    try:
        lines = value.decode("utf-8").splitlines(keepends=True)
    except UnicodeError as error:
        raise ResultValidationError("response UTF-8") from error
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
        raise ResultValidationError("response fence")
    if not regions:
        return value, b""
    opening, closing, info = regions[0]
    if info != "text":
        raise ResultValidationError("response fence language")
    return "".join(lines[:opening]).encode("utf-8"), "".join(lines[opening + 1:closing]).encode("utf-8")


def _validate_fixture_manifest(document, case_id):
    if not isinstance(document, dict) or tuple(document) != ("schema_version", "case_id", "git", "files"):
        raise ResultValidationError("fixture manifest schema")
    if document["schema_version"] != 2 or document["case_id"] != case_id:
        raise ResultValidationError("fixture manifest identity")
    git = document["git"]
    if not isinstance(git, dict) or tuple(git) != ("branch", "head", "status_hex") or not git["branch"]:
        raise ResultValidationError("fixture Git identity")
    if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", git["head"]) is None:
        raise ResultValidationError("fixture HEAD")
    try:
        bytes.fromhex(git["status_hex"])
    except (TypeError, ValueError) as error:
        raise ResultValidationError("fixture Git status") from error
    last = None
    for entry in document["files"]:
        if not isinstance(entry, dict) or tuple(entry) != ("path", "mode", "bytes", "sha256"):
            raise ResultValidationError("fixture manifest entry")
        path = entry["path"]
        _safe_relative("fixture/" + path, "fixture")
        encoded = path.encode("utf-8")
        if last is not None and encoded <= last:
            raise ResultValidationError("fixture manifest ordering")
        last = encoded
        if not re.fullmatch(r"100(?:600|644|755)|120000", entry["mode"]):
            raise ResultValidationError("fixture mode")
        if type(entry["bytes"]) is not int or entry["bytes"] < 0 or re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None:
            raise ResultValidationError("fixture digest")


def _current_bindings(repo_root):
    return {
        "skill_sha256": digest(_regular_bytes(repo_root / "skill/SKILL.md", "skill")),
        "handoff_contract_sha256": digest(_regular_bytes(repo_root / "skill/references/handoff-contract.md", "handoff contract")),
        "runtime_assembler_sha256": digest(_regular_bytes(repo_root / "skill/scripts/assemble_handoff.py", "runtime assembler")),
        "runtime_fingerprint_sha256": digest(_regular_bytes(repo_root / "skill/scripts/status_fingerprint.py", "runtime fingerprint")),
        "forward_runner_sha256": digest(_regular_bytes(repo_root / "tests/run-forward-evals.sh", "forward runner")),
        "product_runner_sha256": digest(_regular_bytes(repo_root / "tests/run-product-forward-eval.sh", "product runner")),
        "corpus_sha256": digest(_regular_bytes(repo_root / "evals/cases.json", "corpus")),
        "fingerprint_sha256": digest(_regular_bytes(repo_root / "tests/status_fingerprint.py", "status fingerprint")),
        "contract_sha256": digest(_regular_bytes(repo_root / "tests/execution_contract.py", "execution contract")),
        "forward_evidence_sha256": digest(_regular_bytes(repo_root / "tests/forward_eval_evidence.py", "forward evidence")),
        "tool_access_evidence_sha256": digest(_regular_bytes(repo_root / "tests/tool_access_evidence.py", "tool access evidence")),
    }


def representative_bindings(core):
    required = {
        "skill_sha256", "handoff_contract_sha256", "runtime_assembler_sha256", "runtime_fingerprint_sha256", "forward_runner_sha256", "corpus_sha256",
        "fingerprint_sha256", "contract_sha256",
        "forward_evidence_sha256", "tool_access_evidence_sha256",
    }
    if not isinstance(core, dict) or not required.issubset(core):
        raise ResultValidationError("representative binding source")
    return {
        "skill_sha256": core["skill_sha256"],
        "handoff_contract_sha256": core["handoff_contract_sha256"],
        "runtime_assembler_sha256": core["runtime_assembler_sha256"],
        "runtime_fingerprint_sha256": core["runtime_fingerprint_sha256"],
        "runner_sha256": core["forward_runner_sha256"],
        "corpus_sha256": core["corpus_sha256"],
        "fingerprint_sha256": core["fingerprint_sha256"],
        "contract_sha256": core["contract_sha256"],
        "forward_evidence_sha256": core["forward_evidence_sha256"],
        "tool_access_evidence_sha256": core["tool_access_evidence_sha256"],
    }


def validate_product_result(repo_root, version, product):
    core = _current_bindings(repo_root)
    pending_bindings = {
        "skill_sha256": core["skill_sha256"],
        "handoff_contract_sha256": core["handoff_contract_sha256"],
        "runtime_assembler_sha256": core["runtime_assembler_sha256"],
        "runtime_fingerprint_sha256": core["runtime_fingerprint_sha256"],
        "runner_sha256": core["product_runner_sha256"],
        "corpus_sha256": core["corpus_sha256"],
        "fingerprint_sha256": core["fingerprint_sha256"],
        "contract_sha256": core["contract_sha256"],
        "tool_access_evidence_sha256": core["tool_access_evidence_sha256"],
    }
    if product.get("version") != version or product.get("case") != "product-forward-label-validation":
        raise ResultValidationError("product identity")
    if product.get("status") == "pending-fresh-eval":
        if product.get("schema_version") != 1:
            raise ResultValidationError("pending product schema")
        if product.get("metrics") is not None or product.get("evidence") is not None or product.get("release_authorized") is not False:
            raise ResultValidationError("pending product claims")
        if product.get("bindings") != pending_bindings:
            raise ResultValidationError("pending product bindings")
        return False
    if product.get("status") != "fresh-eval-passed" or product.get("schema_version") != 4:
        raise ResultValidationError("product status")
    if product.get("evidence_source") != "publisher-recomputed-v3-prestate-and-observed-bound" or product.get("release_authorized") is not False:
        raise ResultValidationError("product provenance")
    expected_bindings = {
        "skill_sha256": core["skill_sha256"],
        "handoff_contract_sha256": core["handoff_contract_sha256"],
        "runtime_assembler_sha256": core["runtime_assembler_sha256"],
        "runtime_fingerprint_sha256": core["runtime_fingerprint_sha256"],
        "runner_sha256": core["product_runner_sha256"],
        "publisher_sha256": digest(_regular_bytes(repo_root / "tests/publish-product-forward-results.py", "product publisher")),
        "evidence_helper_sha256": digest(_regular_bytes(repo_root / "tests/product_forward_evidence.py", "product evidence helper")),
        "transition_helper_sha256": digest(_regular_bytes(repo_root / "tests/execution_contract.py", "transition helper")),
        "corpus_sha256": core["corpus_sha256"],
        "fingerprint_sha256": core["fingerprint_sha256"],
        "tool_access_evidence_sha256": core["tool_access_evidence_sha256"],
    }
    if product.get("bindings") != expected_bindings:
        raise ResultValidationError("product bindings")
    artifact_root = "evals/product-artifacts/v" + version + "/product-forward-label-validation"
    artifacts = product.get("artifacts")
    expected_names = RAW_ARTIFACTS + ("capture-manifest.json",)
    if not isinstance(artifacts, dict) or tuple(artifacts) != expected_names:
        raise ResultValidationError("product artifact inventory")
    for name in expected_names:
        _reference(repo_root, artifacts[name], artifact_root + "/" + name)
    root = repo_root / artifact_root
    actual_names = tuple(path.name for path in sorted(root.iterdir(), key=lambda item: expected_names.index(item.name) if item.name in expected_names else len(expected_names)))
    if actual_names != expected_names:
        raise ResultValidationError("product artifact directory")
    try:
        validate_runtime_snapshot(root, repo_root)
        derived = derive_product_result(root)
    except ProductEvidenceError as error:
        raise ResultValidationError("product replay: " + str(error)) from error
    if product.get("metrics") != derived["metrics"] or product.get("evidence") != derived["evidence"]:
        raise ResultValidationError("product derived claims")
    try:
        tool_access = json.loads(_regular_bytes(
            root / "generation-tool-access-evidence.json", "product tool access"
        ).decode("utf-8"))
        validate_tool_access(tool_access, "product-forward-label-validation", True)
    except (UnicodeError, json.JSONDecodeError, ToolAccessError) as error:
        raise ResultValidationError("product tool access replay: " + str(error)) from error
    return True


def validate_repository(repo_root, require_release=False):
    repo_root = Path(repo_root).resolve(strict=True)
    version = _regular_bytes(repo_root / "VERSION", "VERSION").decode("ascii").strip()
    if re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version) is None:
        raise ResultValidationError("VERSION")
    corpus = _json(repo_root / "evals/cases.json", "corpus")
    expected_cases = {item["id"] for item in corpus.get("cases", [])} - {"product-forward-closure"}
    core = _current_bindings(repo_root)
    result = _json(repo_root / ("evals/results-v" + version + ".json"), "release result")
    product = _json(repo_root / ("evals/product-forward-results-v" + version + ".json"), "product result")
    representative = _json(repo_root / ("evals/representative-forward-results-v" + version + ".json"), "representative result")
    product_ready = validate_product_result(repo_root, version, product)
    if result.get("version") != version:
        raise ResultValidationError("result version")
    if result.get("status") == "pending-fresh-eval":
        if result.get("schema_version") != 4 or result.get("runtime") != ["skill/SKILL.md", "skill/agents/openai.yaml", "skill/references/handoff-contract.md", "skill/scripts/assemble_handoff.py", "skill/scripts/status_fingerprint.py"]:
            raise ResultValidationError("pending result schema/runtime")
        if result.get("cases") != [] or result.get("metrics") is not None or result.get("release_authorized") is not False:
            raise ResultValidationError("pending result claims")
        if result.get("bindings") != core:
            raise ResultValidationError("pending result bindings")
        expected_representative_bindings = representative_bindings(core)
        if representative.get("schema_version") != 1 or representative.get("case") != "chinese-mixed-state-first-delivery" or representative.get("status") != "pending-fresh-eval" or representative.get("release_authorized") is not False or representative.get("bindings") != expected_representative_bindings:
            raise ResultValidationError("pending representative result")
        if require_release:
            raise ResultValidationError("release evidence is pending")
        return False
    if result.get("status") != "fresh-eval-passed" or result.get("schema_version") != 7:
        raise ResultValidationError("fresh result schema")
    if result.get("runtime") != ["skill/SKILL.md", "skill/agents/openai.yaml", "skill/references/handoff-contract.md", "skill/scripts/assemble_handoff.py", "skill/scripts/status_fingerprint.py"]:
        raise ResultValidationError("fresh runtime binding")
    if not product_ready:
        raise ResultValidationError("fresh result lacks fresh product evidence")
    if result.get("release_authorized") is not True or result.get("metrics") != product.get("metrics"):
        raise ResultValidationError("fresh release authorization")
    source_bindings = result.get("bindings")
    expected_sources = {
        "skill": "skill/SKILL.md",
        "handoff_contract": "skill/references/handoff-contract.md",
        "runtime_assembler": "skill/scripts/assemble_handoff.py",
        "runtime_fingerprint": "skill/scripts/status_fingerprint.py",
        "runner": "tests/run-forward-evals.sh",
        "corpus": "evals/cases.json",
        "status_fingerprint": "tests/status_fingerprint.py",
        "execution_contract": "tests/execution_contract.py",
        "forward_eval_evidence": "tests/forward_eval_evidence.py",
        "tool_access_evidence": "tests/tool_access_evidence.py",
        "snapshot_manifest": "evals/artifacts/v" + version + "/snapshot-manifest.json",
    }
    if not isinstance(source_bindings, dict) or set(source_bindings) != set(expected_sources):
        raise ResultValidationError("fresh source bindings")
    source_values = {
        key: _reference(repo_root, source_bindings[key], path, trusted_source=True)
        for key, path in expected_sources.items()
    }
    snapshot_manifest = json.loads(source_values["snapshot_manifest"].decode("utf-8"))
    expected_snapshot = {
        "skill/SKILL.md": digest(source_values["skill"]),
        "skill/references/handoff-contract.md": digest(source_values["handoff_contract"]),
        "skill/scripts/assemble_handoff.py": digest(source_values["runtime_assembler"]),
        "skill/scripts/status_fingerprint.py": digest(source_values["runtime_fingerprint"]),
        "runner.sh": digest(source_values["runner"]),
        "cases.json": digest(source_values["corpus"]),
        "status_fingerprint.py": digest(source_values["status_fingerprint"]),
        "execution_contract.py": digest(source_values["execution_contract"]),
        "forward_eval_evidence.py": digest(source_values["forward_eval_evidence"]),
        "tool_access_evidence.py": digest(source_values["tool_access_evidence"]),
    }
    if snapshot_manifest.get("schema_version") != 1:
        raise ResultValidationError("snapshot manifest schema")
    if {entry.get("path"): entry.get("sha256") for entry in snapshot_manifest.get("files", [])} != expected_snapshot:
        raise ResultValidationError("snapshot manifest sources")
    cases = result.get("cases")
    if not isinstance(cases, list) or {item.get("id") for item in cases} != expected_cases or len(cases) != len(expected_cases):
        raise ResultValidationError("fresh case set")
    for case in cases:
        case_id = case.get("id")
        if tuple(case) != ("id", "outcome", "artifacts", "session_command") or case["outcome"] != "pass" or case["session_command"] != COMMAND_TEMPLATE:
            raise ResultValidationError("case result schema")
        artifacts = case["artifacts"]
        if not isinstance(artifacts, dict) or set(artifacts) != set(GENERIC_ARTIFACTS) | {"responses"}:
            raise ResultValidationError("case artifact schema")
        root = "evals/artifacts/v" + version + "/" + case_id
        values = {
            key: _reference(repo_root, artifacts[key], root + "/" + filename)
            for key, filename in GENERIC_ARTIFACTS.items()
        }
        fixture = json.loads(values["fixture_manifest"].decode("utf-8"))
        _validate_fixture_manifest(fixture, case_id)
        post_state = json.loads(values["post_state_manifest"].decode("utf-8"))
        generation = json.loads(values["generation_evidence"].decode("utf-8"))
        assembly = json.loads(values["assembly_manifest"].decode("utf-8"))
        side_effect = json.loads(values["side_effect_evidence"].decode("utf-8"))
        snapshot = json.loads(values["snapshot_evidence"].decode("utf-8"))
        grounding_sources = json.loads(values["grounding_sources"].decode("utf-8"))
        tool_access = json.loads(values["tool_access_evidence"].decode("utf-8"))
        try:
            validate_state_manifest(fixture, case_id)
            validate_state_manifest(post_state, case_id)
            validate_grounding_source_publication(grounding_sources, case_id)
            validate_generation_evidence(generation)
            validate_assembly_evidence(
                assembly, values["draft"],
                _reference(repo_root, artifacts["responses"][-1], root + "/response-" + str(len(artifacts["responses"])) + ".txt"),
                values["assembly_preamble"], values["assembly_context"],
                source_values["runtime_assembler"],
            )
            validate_side_effect_evidence(
                side_effect, case_id, generation["generation_read_only"], fixture, post_state
            )
            validate_snapshot_evidence(snapshot, case_id, tuple(expected_snapshot[path] for path in ("skill/SKILL.md", "runner.sh", "cases.json")))
        except EvidenceFailure as error:
            raise ResultValidationError("case evidence " + case_id + ": " + str(error)) from error
        if generation["snapshot_manifest_sha256"] != digest(source_values["snapshot_manifest"]):
            raise ResultValidationError("case snapshot manifest binding")
        if generation["post_state_manifest_sha256"] != digest(values["post_state_manifest"]):
            raise ResultValidationError("case post-state manifest binding")
        if generation["grounding_sources_sha256"] != digest(values["grounding_sources"]):
            raise ResultValidationError("case grounding source binding")
        if generation["tracker_before_sha256"] != manifest_file_sha256(fixture, ".project/development/task_plan.md"):
            raise ResultValidationError("case tracker-before binding")
        if generation["tracker_after_sha256"] != manifest_file_sha256(post_state, ".project/development/task_plan.md"):
            raise ResultValidationError("case tracker-after binding")
        if generation["draft_sha256"] != assembly["draft_sha256"] or generation["assembly_manifest_sha256"] != digest(values["assembly_manifest"]) or generation["assembly_mode"] != assembly["mode"]:
            raise ResultValidationError("case assembly binding")
        responses = artifacts["responses"]
        if not isinstance(responses, list) or len(responses) != len(generation["response_sha256"]):
            raise ResultValidationError("case response count")
        response_values = []
        for index, reference in enumerate(responses, 1):
            value = _reference(repo_root, reference, root + "/response-" + str(index) + ".txt")
            response_values.append(value)
            summary, body = _response_parts(value)
            if generation["response_sha256"][index - 1] != digest(value) or generation["response_bytes"][index - 1] != len(value):
                raise ResultValidationError("case response binding")
            if generation["summary_sha256"][index - 1] != digest(summary) or generation["body_sha256"][index - 1] != digest(body):
                raise ResultValidationError("case response part binding")
        try:
            handoff = validate_forward_case(case_id, response_values[-1].decode("utf-8"))
            if handoff is not None:
                validate_generic_handoff_grounding(
                    case_id,
                    handoff,
                    fixture,
                    grounding_sources,
                )
                if generation["status_fingerprint_sha256"] != handoff["snapshot"]["status_fingerprint"]:
                    raise ResultValidationError("case status fingerprint binding")
            validate_tool_access(tool_access, case_id, handoff is not None)
        except (UnicodeError, ContractError, ToolAccessError) as error:
            raise ResultValidationError("case semantic replay " + case_id + ": " + str(error)) from error
        actual = {path.name for path in (repo_root / root).iterdir()}
        expected = set(GENERIC_ARTIFACTS.values()) | {"response-" + str(index) + ".txt" for index in range(1, len(responses) + 1)}
        if actual != expected:
            raise ResultValidationError("case artifact directory")
    representative_case = next(item for item in cases if item["id"] == "chinese-mixed-state-first-delivery")
    expected_representative = {
        "schema_version": 4,
        "version": version,
        "status": "fresh-eval-passed",
        "case": representative_case["id"],
        "outcome": representative_case["outcome"],
        "artifacts": representative_case["artifacts"],
        "evidence_source": "aggregate-publisher-semantic-replay-v3-poststate-bound",
        "bindings": representative_bindings(core),
        "release_authorized": False,
    }
    if representative != expected_representative:
        raise ResultValidationError("representative projection")
    return True
