# Development Plan

## Goal

Deliver a lightweight, independently versioned Codex skill that generates grounded development instructions, installs with one command, and persists project progress across context changes.

## Current Status

- Phase: 6 - Plugin-aware lightweight revision
- Status: in_progress

## Next Step

Commit the validated plugin-aware contract, record release evidence, and create the annotated `v0.2.0` tag.

## Requirements

- Keep the repository in `/home/ubuntu/generate-codex-instructions`.
- Reuse relevant installed skills, plugins, MCP tools, and repository-native capabilities.
- Ground instructions in design documents, owner code, tests, and current state.
- Select one convergent work unit and solve root causes.
- Validate syntax, behavior, redundancy, and scope.
- Persist project plan, progress, evidence, errors, and lessons inside the target project.
- Bind those records to the project the generated instruction will modify, never to the installed skill directory.
- Require truthful closure and focused version control.
- Support one-command installation into Codex.

## Phases

1. [x] Research official Codex skill rules and prototype the workflow.
2. [x] Create the independent repository, skill bundle, installer, and persistent-progress contract.
3. [x] Validate structure, installer idempotence, progress behavior, and lightweight size.
4. [x] Forward-test instruction generation and independently review the final artifacts.
5. [x] Install locally, remove prototype artifacts from PYTHIA, commit, and tag the release.
6. [ ] Add plugin/MCP coverage, fix blocker and role boundaries, compress the skill, validate, and release `v0.2.0`.

## Decisions

- Use the repository root as the skill directory.
- Keep `SKILL.md`, `agents/openai.yaml`, and `install.sh` as the only runtime/install artifacts.
- Use an existing repository tracker or active project-local planning files when present; otherwise use `.codex/development/` as the fallback progress store.
- The progress files in this repository describe development of the skill itself; each generated instruction maintains equivalent state in its own target project.
- Install by symlink so the repository remains the single source of truth.
- Keep one tracker: apply `planning-with-files` recovery/update principles to `.codex/development/` instead of creating root-level planning files.
- Treat plugin-bundled skills and plugin-provided MCP/tools as distinct capability surfaces.

## Errors

- The PYTHIA knowledge-graph MCP was not injected into the original session; its read-only CLI equivalents were used.
- Two bookkeeping patches had malformed multi-file hunk separators; subsequent bookkeeping uses one patch per file.
- A first forward test inferred an undocumented range and a blocker test ran future-task checks; explicit no-invention and generation/execution boundaries fixed both issues.
- The first disposable installer test used a prohibited recursive cleanup command and was rejected before execution; use exact `unlink`/`rmdir` cleanup instead.
- A disposable target setup initialized `/tmp/.git` because `git init` ran from the wrong working directory; timestamp and default-only contents confirmed the mistake, the exact directory was deleted, and the target was reinitialized with an explicit working directory.
