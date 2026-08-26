#!/usr/bin/env python3

from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tool_access_evidence import ToolAccessError, project_tool_access, validate_tool_access


def fail(message):
    raise SystemExit("FAIL: tool access evidence self-test: " + message)


def rejected(label, raw):
    try:
        project_tool_access("case", raw)
    except ToolAccessError:
        return
    fail(label + " accepted")


def main():
    counted_skill = "\n".join((
        "/usr/bin/zsh -lc 'wc -l ../../../snapshot/skill/SKILL.md' in /tmp/fixture",
        "/usr/bin/zsh -lc \"sed -n '1,240p' ../../../snapshot/skill/SKILL.md\" in /tmp/fixture",
    )).encode("utf-8")
    counted_document = project_tool_access("counted-skill", counted_skill)
    validate_tool_access(counted_document, "counted-skill", False)
    executable = "\n".join((
        "Use the skill at /repo/skill/SKILL.md and respond entirely in English.",
        "/usr/bin/zsh -lc 'sed -n 1,80p ../../../snapshot/skill/SKILL.md' in /tmp/fixture",
        "/usr/bin/zsh -lc 'readlink -f ../../../snapshot/skill/SKILL.md && stat -c %F ../../../snapshot/skill ../../../snapshot/skill/SKILL.md ../../../snapshot/skill/references/handoff-contract.md ../../../snapshot/skill/scripts/status_fingerprint.py' in /tmp/fixture",
        "/usr/bin/zsh -lc 'namei -l ../../../snapshot/skill/SKILL.md' in /tmp/fixture",
        "/usr/bin/zsh -lc \"wc -l ../../../snapshot/skill/references/handoff-contract.md\nsed -n '1,220p' ../../../snapshot/skill/references/handoff-contract.md\" in /tmp/fixture",
        "/usr/bin/zsh -lc 'python3 ../../../snapshot/skill/scripts/status_fingerprint.py --repository . --tracker .project/development/task_plan.md --unit U1 --profile Standard --emit context' in /tmp/fixture",
        "/usr/bin/zsh -lc 'python3 ../../../snapshot/skill/scripts/status_fingerprint.py --repository . --tracker .project/development/task_plan.md --unit U1 --profile Standard --emit context' in /tmp/fixture",
        "/usr/bin/zsh -lc 'python3 ../../../snapshot/skill/scripts/status_fingerprint.py --repository . --tracker .project/development/task_plan.md --unit U1 --profile Standard --emit preamble' in /tmp/fixture",
        "/usr/bin/zsh -lc 'python3 ../../../snapshot/skill/scripts/status_fingerprint.py --repository . --tracker .project/development/task_plan.md --unit U1 --profile Standard --emit preamble' in /tmp/fixture",
    )).encode()
    document = project_tool_access("case", executable)
    validate_tool_access(document, "case", True)
    relative = "\n".join((
        "/usr/bin/zsh -lc 'cat ../../../snapshot/skill/SKILL.md' in /tmp/fixture",
        "/usr/bin/zsh -c 'pwd -P' in /tmp/snapshot/skill",
        "/usr/bin/zsh -lc 'cat references/handoff-contract.md' in /tmp/snapshot/skill",
        "/usr/bin/zsh -lc 'python3 /tmp/snapshot/skill/scripts/status_fingerprint.py --repository . --tracker .project/development/task_plan.md --unit U1 --profile Standard --emit context' in /tmp/fixture",
        "/usr/bin/zsh -lc 'python3 /tmp/snapshot/skill/scripts/status_fingerprint.py --repository . --tracker .project/development/task_plan.md --unit U1 --profile Standard --emit context' in /tmp/fixture",
        "/usr/bin/zsh -lc 'python3 /tmp/snapshot/skill/scripts/status_fingerprint.py --repository . --tracker .project/development/task_plan.md --unit U1 --profile Standard --emit preamble' in /tmp/fixture",
        "/usr/bin/zsh -lc 'python3 /tmp/snapshot/skill/scripts/status_fingerprint.py --repository . --tracker .project/development/task_plan.md --unit U1 --profile Standard --emit preamble' in /tmp/fixture",
    )).encode("utf-8")
    validate_tool_access(project_tool_access("relative", relative), "relative", True)
    mixed_access = "\n".join((
        "/usr/bin/zsh -lc 'cat /tmp/snapshot/skill/SKILL.md' in /tmp/fixture",
        "/usr/bin/zsh -lc \"realpath /tmp/snapshot/skill && sed -n '1,220p' /tmp/snapshot/skill/references/handoff-contract.md\" in /tmp/fixture",
        "/usr/bin/zsh -lc 'python3 /tmp/snapshot/skill/scripts/status_fingerprint.py --repository . --tracker .project/development/task_plan.md --unit U1 --profile Standard --emit context' in /tmp/fixture",
        "/usr/bin/zsh -lc 'python3 /tmp/snapshot/skill/scripts/status_fingerprint.py --repository . --tracker .project/development/task_plan.md --unit U1 --profile Standard --emit context' in /tmp/fixture",
        "/usr/bin/zsh -lc 'python3 /tmp/snapshot/skill/scripts/status_fingerprint.py --repository . --tracker .project/development/task_plan.md --unit U1 --profile Standard --emit preamble' in /tmp/fixture",
        "/usr/bin/zsh -lc 'python3 /tmp/snapshot/skill/scripts/status_fingerprint.py --repository . --tracker .project/development/task_plan.md --unit U1 --profile Standard --emit preamble' in /tmp/fixture",
    )).encode("utf-8")
    validate_tool_access(project_tool_access("mixed", mixed_access), "mixed", True)
    numbered = mixed_access.replace(
        b"sed -n '1,220p' /tmp/snapshot/skill/references/handoff-contract.md",
        b"nl -ba /tmp/snapshot/skill/references/handoff-contract.md",
    )
    validate_tool_access(project_tool_access("numbered", numbered), "numbered", True)
    sed_last = mixed_access.replace(b"sed -n '1,220p'", b"sed -n '1,$p'")
    validate_tool_access(project_tool_access("sed-last", sed_last), "sed-last", True)
    helper_retry = mixed_access + b"\n" + b"\n".join(mixed_access.splitlines()[-4:])
    validate_tool_access(project_tool_access("helper-retry", helper_retry), "helper-retry", True)
    unrelated_skill = mixed_access + b"\n" + (
        b"/usr/bin/zsh -lc 'printf named-skill && sed -n 1,80p "
        b"/home/ubuntu/.codex/skills/planning-with-files/SKILL.md' in /tmp/fixture"
    )
    unrelated_document = project_tool_access("unrelated", unrelated_skill)
    validate_tool_access(unrelated_document, "unrelated", True)
    if unrelated_document["accesses"] != project_tool_access("mixed", mixed_access)["accesses"]:
        fail("unrelated skill access entered target-package projection")
    semicolon_metadata = mixed_access.replace(b"realpath /tmp/snapshot/skill && sed", b"realpath /tmp/snapshot/skill; sed")
    validate_tool_access(project_tool_access("semicolon", semicolon_metadata), "semicolon", True)
    combined = "\n".join((
        "/usr/bin/zsh -lc 'cat /tmp/snapshot/skill/SKILL.md' in /tmp/fixture",
        "/usr/bin/zsh -lc 'cat /tmp/snapshot/skill/references/handoff-contract.md' in /tmp/fixture",
        "/usr/bin/zsh -lc 'a=$(python3 /tmp/snapshot/skill/scripts/status_fingerprint.py --repository . --tracker .project/development/task_plan.md --unit U1 --profile Standard --emit context)\nb=$(python3 /tmp/snapshot/skill/scripts/status_fingerprint.py --repository . --tracker .project/development/task_plan.md --unit U1 --profile Standard --emit context)\nc=$(python3 /tmp/snapshot/skill/scripts/status_fingerprint.py --repository . --tracker .project/development/task_plan.md --unit U1 --profile Standard --emit preamble)\nd=$(python3 /tmp/snapshot/skill/scripts/status_fingerprint.py --repository . --tracker .project/development/task_plan.md --unit U1 --profile Standard --emit preamble)' in /tmp/fixture",
    )).encode("utf-8")
    validate_tool_access(project_tool_access("combined", combined), "combined", True)
    for label, extra in (
        ("duplicate SKILL read", document["accesses"][0]),
        ("duplicate reference read", document["accesses"][3]),
    ):
        duplicate = dict(document, accesses=[extra] + document["accesses"])
        duplicate["accesses"] = [dict(row, event=index) for index, row in enumerate(duplicate["accesses"], 1)]
        try:
            validate_tool_access(duplicate, "case", True)
        except ToolAccessError:
            pass
        else:
            fail(label + " accepted")
    non_executable = project_tool_access("blocked", executable.splitlines()[0] + b"\n")
    validate_tool_access(non_executable, "blocked", False)
    validate_tool_access(dict(document, case_id="projected-field-injection"), "projected-field-injection", False)
    tampered = dict(document, accesses=document["accesses"][:-1])
    try:
        validate_tool_access(tampered, "case", True)
    except ToolAccessError:
        pass
    else:
        fail("missing helper invocation accepted")
    rejected(
        "helper source read",
        b"/usr/bin/zsh -lc 'sed -n 1,40p /repo/skill/scripts/status_fingerprint.py' in /tmp/fixture\n",
    )
    rejected(
        "package listing",
        b"/usr/bin/zsh -lc 'find /repo/skill -maxdepth 2 -type f' in /tmp/fixture\n",
    )
    rejected(
        "undeclared package metadata",
        b"/usr/bin/zsh -lc 'stat /repo/skill/private.txt' in /tmp/fixture\n",
    )
    print("PASS: bounded skill-package tool access evidence")


if __name__ == "__main__":
    main()
