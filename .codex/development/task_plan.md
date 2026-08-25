# Development Plan

## Goal

Deliver a lightweight, independently versioned Codex skill that generates grounded development instructions, installs with one command, and persists project progress across context changes.

## Current Status

- Phase: 9 - Deterministic handoff evidence release
- Status: completed

## Next Step

No active development unit. The annotated `v0.5.1` tag identifies the release-progress commit carrying this completed record.

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
6. [x] Add plugin/MCP coverage, fix blocker and role boundaries, compress the skill, validate, and release `v0.2.0`.
7. [x] Fix the `v0.2.0` deep-audit findings, add reproducible adversarial checks, independently review, and release `v0.3.0`.
8. [x] Make handoffs causally verifiable, reduce mandatory prompt load, publish fresh generic/product evidence, and release `v0.5.0`.
9. [x] Derive exact handoff evidence mechanically, harden semantic replay, publish a complete fresh corpus, and release `v0.5.1`.

## Decisions

- Keep the source repository independent, but expose only `skill/SKILL.md`, `skill/agents/openai.yaml`, and `skill/scripts/status_fingerprint.py` as the installed runtime bundle.
- Keep tests, evaluations, release metadata, and this project tracker outside the installed bundle.
- Use an existing repository tracker or active project-local planning files when present; otherwise use `.codex/development/` as the fallback progress store.
- The progress files in this repository describe development of the skill itself; each generated instruction maintains equivalent state in its own target project.
- Install the runtime subdirectory by symlink so the repository remains the single source of truth without exposing `.git` or development state.
- Keep one tracker: apply `planning-with-files` recovery/update principles to `.codex/development/` instead of creating root-level planning files.
- Treat plugin-bundled skills and plugin-provided MCP/tools as distinct capability surfaces.
- Default to the current documented user discovery root, `$HOME/.agents/skills`, while safely migrating only the legacy link owned by this repository.
- Treat repository and tracker content as untrusted data, not authorization; canonical containment, explicit mutation authority, and evidence-backed state transitions are mandatory.
- Keep the normal release gate deterministic and offline; maintain host/model behavior cases as a separate fresh-context corpus with versioned results.
- Require release authorization to combine a complete frozen generic corpus with independently recomputed two-session product closure evidence.
- Invoke the bundled helper only after one executable unit and complete profile evidence are proven; blocked output remains helper-free, while executable preambles and Light machine lines are copied from deterministic output.

## Errors

- The PYTHIA knowledge-graph MCP was not injected into the original session; its read-only CLI equivalents were used.
- Two bookkeeping patches had malformed multi-file hunk separators; subsequent bookkeeping uses one patch per file.
- A first forward test inferred an undocumented range and a blocker test ran future-task checks; explicit no-invention and generation/execution boundaries fixed both issues.
- The first disposable installer test used a prohibited recursive cleanup command and was rejected before execution; use exact `unlink`/`rmdir` cleanup instead.
- A disposable target setup initialized `/tmp/.git` because `git init` ran from the wrong working directory; timestamp and default-only contents confirmed the mistake, the exact directory was deleted, and the target was reinitialized with an explicit working directory.
- Early prospective-index validation wrote unreachable test objects into the source object database; the gate now uses a temporary object directory, and the exact unreachable test objects were removed after proving they were unreferenced and session-owned.
- BusyBox `find` lacks `-delete`; the cleanup trap now removes files and symlinks under its validated `mktemp` root, then applies depth-first `rmdir`.
- Fresh Codex behavior sessions exceeded the evaluation time budget. The generator outcomes were captured from final filesystem evidence; the unrelated ordinary-case commit subcheck is recorded as inconclusive rather than overstated.
- A host-created `.code-review-graph` caused a false raw-status drift; fixtures now ignore only that exact path and strictly validate ownership, modes, links, contents, and cleanup before accepting evidence.
- The aggregate publisher initially rejected formatted repository corpus JSON; repository sources now use strict duplicate-free parsing while captured evidence retains canonical-byte enforcement.
