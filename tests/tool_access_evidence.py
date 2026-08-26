#!/usr/bin/env python3
"""Project and validate bounded skill-package access evidence from Codex logs."""

import hashlib
import json
from pathlib import Path
import re
import shlex
import sys


class ToolAccessError(ValueError):
    pass


READER_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:cat|sed|head|tail|nl|less|more|awk|perl|ruby|grep|rg|dd|xxd|od|sha(?:1|224|256|384|512)sum)\b"
)
SHELL_EVENT_PATTERN = re.compile(
    r"^(?:/usr/bin/|/bin/)?(?:zsh|bash|dash|sh)\s+-(?:l)?c\s+"
)
METADATA_COMMANDS = {"namei", "pwd", "readlink", "realpath", "stat"}
CONTENT_READ_COMMANDS = {"cat", "head", "nl", "sed", "tail", "wc"}
SED_PROGRAM_PATTERN = re.compile(r"[0-9]+(?:,(?:[0-9]+|\$))?p")
DECLARED_SKILL_SUFFIXES = (
    "/skill", "/skill/SKILL.md", "/skill/references/handoff-contract.md",
    "/skill/scripts/status_fingerprint.py",
)
DECLARED_RELATIVE_PATHS = {
    "SKILL.md": "/skill/SKILL.md",
    "references/handoff-contract.md": "/skill/references/handoff-contract.md",
    "scripts/status_fingerprint.py": "/skill/scripts/status_fingerprint.py",
}


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _shell_events(text):
    pending = []
    for line in text.splitlines():
        if pending:
            pending.append(line)
            if " in " in line:
                yield "\n".join(pending)
                pending = []
            continue
        if not SHELL_EVENT_PATTERN.search(line):
            continue
        if " in " in line:
            yield line
        else:
            pending = [line]


def _shell_segments(line):
    outer = line.rsplit(" in ", 1)[0]
    try:
        outer_arguments = shlex.split(outer, posix=True)
        if len(outer_arguments) < 3 or outer_arguments[1] not in {"-c", "-lc"}:
            return []
        tokens = shlex.split(
            outer_arguments[2].replace("\n", " && ").replace(";", " && "),
            posix=True,
        )
    except ValueError:
        return []
    segments, current = [], []
    for token in tokens:
        if token == "&&":
            if not current:
                return []
            segments.append(current)
            current = []
        else:
            current.append(token)
    if current:
        segments.append(current)
    return segments


def _skill_cwd(line):
    cwd = line.rsplit(" in ", 1)[1].strip() if " in " in line else ""
    return cwd.rstrip("/").endswith("/skill")


def _target_skill_path(token):
    normalized = token.strip("'\"").replace("\\", "/")
    return "/" in normalized and "skill" in normalized.split("/")


def _skill_references(segment, line):
    references = [token for token in segment[1:] if _target_skill_path(token)]
    if _skill_cwd(line):
        references.extend(
            normalized for token, normalized in DECLARED_RELATIVE_PATHS.items()
            if token in segment[1:]
        )
    return references


def _declared_references(references, allowed_suffixes=DECLARED_SKILL_SUFFIXES):
    return bool(references) and all(
        any(reference.rstrip("/").endswith(suffix) for suffix in allowed_suffixes)
        for reference in references
    )


def _metadata_observation(line):
    related = [segment for segment in _shell_segments(line) if _skill_references(segment, line)]
    if not related and _skill_cwd(line):
        related = [segment for segment in _shell_segments(line) if Path(segment[0]).name == "pwd"]
    if not related:
        return False
    if any(
        Path(segment[0]).name not in METADATA_COMMANDS
        or any(token in {";", "|", "<", ">", "`"} or "$(" in token for token in segment)
        for segment in related
    ):
        return False
    references = [
        reference for segment in related for reference in _skill_references(segment, line)
        if reference
    ]
    return (
        _declared_references(references)
        if references else _skill_cwd(line) and all(Path(segment[0]).name == "pwd" for segment in related)
    )


def _content_read(line, suffix):
    related = [segment for segment in _shell_segments(line) if _skill_references(segment, line)]
    if not related or any(Path(segment[0]).name not in CONTENT_READ_COMMANDS for segment in related):
        return False
    has_reader = False
    for segment in related:
        command = Path(segment[0]).name
        if any(token in {";", "|", "<", ">", "`"} or "$(" in token for token in segment):
            return False
        if command == "wc":
            if "-l" not in segment:
                return False
        elif command == "sed":
            if "-n" not in segment or not any(SED_PROGRAM_PATTERN.fullmatch(token) for token in segment):
                return False
            has_reader = True
        else:
            has_reader = True
    references = [reference for segment in related for reference in _skill_references(segment, line)]
    return has_reader and _declared_references(references, (suffix,))


def _classify_declared_event(line):
    classified = []
    touched = False
    for segment in _shell_segments(line):
        references = _skill_references(segment, line)
        command = Path(segment[0]).name
        if not references and _skill_cwd(line) and command == "pwd":
            classified.append(("observe", "skill", "none"))
            touched = True
            continue
        if not references:
            continue
        touched = True
        if command in METADATA_COMMANDS:
            if not _declared_references(references):
                return None
            classified.append(("observe", "skill", "none"))
            continue
        if command not in CONTENT_READ_COMMANDS:
            return None
        if any(token in {";", "|", "<", ">", "`"} or "$(" in token for token in segment):
            return None
        if command == "wc":
            if "-l" not in segment or not _declared_references(references):
                return None
            continue
        if command == "sed" and (
            "-n" not in segment
            or not any(SED_PROGRAM_PATTERN.fullmatch(token) for token in segment)
        ):
            return None
        if _declared_references(references, ("/skill/SKILL.md",)):
            classified.append(("read", "skill/SKILL.md", "none"))
        elif _declared_references(references, ("/skill/references/handoff-contract.md",)):
            classified.append(("read", "skill/references/handoff-contract.md", "none"))
        else:
            return None
    if not touched:
        return []
    unique = []
    for access in classified:
        if access not in unique:
            unique.append(access)
    return unique


def project_tool_access(case_id, raw_log):
    if not isinstance(case_id, str) or not case_id or not isinstance(raw_log, bytes):
        raise ToolAccessError("tool access input")
    accesses = []
    for line in _shell_events(raw_log.decode("utf-8", errors="replace")):
        segments = _shell_segments(line)
        if (
            " in " not in line
            or not SHELL_EVENT_PATTERN.search(line)
            or not (_skill_cwd(line) or any(_skill_references(segment, line) for segment in segments))
        ):
            continue
        reader = READER_PATTERN.search(line)
        declared = _classify_declared_event(line)
        if declared is not None:
            for kind, path, mode in declared:
                accesses.append({
                    "event": len(accesses) + 1,
                    "kind": kind,
                    "path": path,
                    "emit": mode,
                    "line_sha256": _digest(line.encode("utf-8")),
                })
            continue
        if "skill/scripts/status_fingerprint.py" in line:
            occurrences = line.count("skill/scripts/status_fingerprint.py")
            emits = re.findall(r"--emit(?:=|\s+)(context|preamble)(?:\s|['\"\)\n]|$)", line)
            if (
                reader
                or occurrences < 1
                or len(emits) != occurrences
                or len(re.findall(r"\bpython3?\b", line)) < occurrences
                or any(line.count(flag) < occurrences for flag in ("--repository", "--tracker", "--unit", "--profile", "--emit"))
            ):
                raise ToolAccessError("generator inspected helper source or used an unsupported helper command")
            for emit in emits:
                accesses.append({
                    "event": len(accesses) + 1,
                    "kind": "execute",
                    "path": "skill/scripts/status_fingerprint.py",
                    "emit": emit,
                    "line_sha256": _digest(line.encode("utf-8")),
                })
            continue
        else:
            raise ToolAccessError("generator accessed an undeclared skill-package path")
    return {
        "schema_version": 1,
        "case_id": case_id,
        "raw_log_bytes": len(raw_log),
        "raw_log_sha256": _digest(raw_log),
        "accesses": accesses,
    }


def validate_tool_access(document, case_id, executable):
    if not isinstance(document, dict) or tuple(document) != (
        "schema_version", "case_id", "raw_log_bytes", "raw_log_sha256", "accesses"
    ):
        raise ToolAccessError("tool access schema")
    if document["schema_version"] != 1 or document["case_id"] != case_id:
        raise ToolAccessError("tool access identity")
    if type(document["raw_log_bytes"]) is not int or document["raw_log_bytes"] < 0:
        raise ToolAccessError("tool access byte count")
    if re.fullmatch(r"[0-9a-f]{64}", document["raw_log_sha256"] or "") is None:
        raise ToolAccessError("tool access log digest")
    accesses = document["accesses"]
    if not isinstance(accesses, list):
        raise ToolAccessError("tool access list")
    allowed = {
        "skill": ("observe", "none"),
        "skill/SKILL.md": ("read", "none"),
        "skill/references/handoff-contract.md": ("read", "none"),
        "skill/scripts/status_fingerprint.py": ("execute", None),
    }
    for index, access in enumerate(accesses, 1):
        if not isinstance(access, dict) or tuple(access) != (
            "event", "kind", "path", "emit", "line_sha256"
        ):
            raise ToolAccessError("tool access row")
        if access["event"] != index or access["path"] not in allowed:
            raise ToolAccessError("tool access ordering")
        kind, emit = allowed[access["path"]]
        if access["kind"] != kind or (emit is not None and access["emit"] != emit):
            raise ToolAccessError("tool access operation")
        if access["path"].endswith("status_fingerprint.py") and access["emit"] not in {"context", "preamble"}:
            raise ToolAccessError("tool access helper mode")
        if re.fullmatch(r"[0-9a-f]{64}", access["line_sha256"] or "") is None:
            raise ToolAccessError("tool access line digest")
    reference_reads = sum(
        access["path"] == "skill/references/handoff-contract.md" for access in accesses
    )
    skill_reads = sum(access["path"] == "skill/SKILL.md" for access in accesses)
    metadata_reads = sum(access["path"] == "skill" for access in accesses)
    helper_modes = [
        access["emit"] for access in accesses
        if access["path"] == "skill/scripts/status_fingerprint.py"
    ]
    helper_rounds = helper_modes.count("context")
    full_protocol = (
        metadata_reads <= 2
        and skill_reads <= 1
        and reference_reads == 1
        and helper_rounds in {2, 4}
        and helper_modes.count("preamble") == helper_rounds
        and len(helper_modes) == helper_rounds * 2
    )
    projection_blocked = case_id in {"projected-field-injection", "unsafe-gate-command"}
    if executable:
        if not full_protocol:
            raise ToolAccessError("executable tool access protocol")
    elif projection_blocked:
        no_conditional_access = metadata_reads <= 2 and skill_reads <= 1 and not reference_reads and not helper_modes
        if not (no_conditional_access or full_protocol):
            raise ToolAccessError("projection-blocked tool access protocol")
    elif metadata_reads > 2 or skill_reads > 1 or reference_reads or helper_modes:
        raise ToolAccessError("non-executable tool access protocol")
    return document


def main():
    if len(sys.argv) not in (4, 5) or (len(sys.argv) == 5 and sys.argv[4] != "--executable"):
        raise SystemExit("usage: tool_access_evidence.py CASE_ID RAW_LOG OUTPUT_JSON [--executable]")
    document = project_tool_access(sys.argv[1], Path(sys.argv[2]).read_bytes())
    if len(sys.argv) == 5:
        validate_tool_access(document, sys.argv[1], True)
    Path(sys.argv[3]).write_text(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
