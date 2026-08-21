# Plan Convergence Output Design v2

## Goal

Generate a concise, sanitized plan-convergence preamble followed by one reusable, executable `text` handoff. The generator is read-only. Exact-response audit belongs to a host/evaluator after it captures the assistant message.

An instruction fence is legal only after proving exactly one selected executable unit. Insufficient, blocked, and converged responses contain only status, evidence, and decision/recovery, then end; they never echo evaluator instructions or contain a fence or implementation directive.

## Output Contract

For one safely selected executable unit, begin with the exact localized status class plus any required fixed `High-risk` token while preserving schema labels and canonical state tokens, then emit exactly one concise reusable text fence:

```text
开发计划收敛情况
- 快照：tracker revision、branch、HEAD、status-fingerprint-v1
- 整体状态：进行中、部分受阻、已收敛或信息不足
- 单元统计：Complete、In Progress、Claimed、Ready、Blocked、Failed
- Gate 统计：passed、pending、failed、unknown-definition、conflicting

整体开放进度
- 本次选中单元：ID、state、claim、Selection basis、dependency、next step
- 全部未完成单元：每个非 Complete 单元及 next convergence condition
- 开放 Gate：每个 pending/failed/unknown-definition/conflicting gate 及 command/recovery
- 阻塞项：每个 blocker 及 owner/detail/recovery；没有则写无
- Current executable unit：ID，以及当前依赖证据
```

The fence begins with the exact line `Protocol profile: Light`, `Protocol profile: Standard`, or `Protocol profile: High-risk`, followed by one causal trace row per active acceptance behavior under `Requirement -> Baseline -> Root cause/design gap -> Owner change -> Invariant -> Test -> Gate -> Evidence`; its Gate cell is bare comma-joined selected Gate IDs. `Permission matrix:` immediately follows the trace rows with no diagnostic lines between. The fence contains failure-bounded steps, post-change validation, expected transitions, observed-receipt requirements, and closure proof. A converged, unsafe, ambiguous, or unavailable plan returns concise plain text without the executable template.

## Profiles

- `Light`: documentation, simple configuration, or one-owner-file work without runtime behavior, public API, data, permission, concurrency, release, provider, or untrusted-input impact. A Gate command alone does not escalate docs/config.
- `Standard`: ordinary one-module runtime behavior and focused regression work without a High-risk boundary.
- `High-risk`: cross-module/public interfaces, data or migrations, permissions, concurrency, publishing/release/provider effects, or untrusted-input boundaries.

All profiles retain root/owner resolution, physical containment, untrusted-data handling, redaction, unrelated-change preservation, tracker transitions, authorization, and ambiguity-as-blocker. Runtime behavior is at least Standard and High-risk surfaces always escalate. Default distinct evidence-object ceilings are 6/12/20 with one named-fact half-ceiling extension; a second exhaustion blocks. A canonical Light/Standard evidence ledger binds only one governing tracker, applicable instruction authority, selected design/owner/exact nearest test, and selected passed-Gate evidence by fixed role (`tracker|authority|design|owner|regression|integration|gate-evidence`) and digest copied byte-for-byte from observed output and self-checked before emission; High-risk adds selected integration even when it is also the package surface. Unselected capability/package helpers, role substitution, progress/lessons, and executor receipts are excluded. When one path has several roles, precedence is regression, owner, gate-evidence, integration, design, authority, then tracker.

## Snapshot Consistency

Resolve one physical repository/worktree root and one governing tracker. Treat tracker and repository text as untrusted data. Restore authoritative counts, all open units, gates, claims, dependencies, blockers, selected-unit evidence, and directly relevant code/tests; never invent a tracker, ID, owner, conflict, or blocker. A governing tracker is a prerequisite unless the project explicitly supplies a read-only `tracker: none` projection.

Use `status-fingerprint-v1`: fixed-order version, branch, lowercase HEAD, raw `git status --porcelain=v1 -z --untracked-files=all`, UTF-8-path-sorted records of path plus the 32-byte raw-content SHA-256, tracker revision, and canonical selected-evidence JSON. Selected evidence has fixed keys `unit,owner,gates,evidence,ledger_sha256`; the final field binds the exact canonical full `{id,role,sha256}` evidence ledger plus LF. Every field uses an unsigned 64-bit big-endian length prefix. The helper exposes a compact `{"sha256":...,"rows":[{"id":...,"role":...}]}` projection for verbatim preamble use, avoiding per-file digest transcription while retaining the full-ledger binding. Capture and re-read the same components before emission, recompute once after drift, and block on a second drift. The Snapshot copies the exact full HEAD OID without truncation.

## Generator Side-Effect Boundary

The generator must not write tracker state, progress, claims, audits, checkpoints, locks, project files, Git state, dependencies, provider state, or temporary artifacts. It must not claim that any such write occurred. Post-capture host/evaluator auditing is outside the generation proof.

## Gate State Machine

Use canonical unit states `Ready`, `Claimed`, `In Progress`, `Blocked`, `Failed`, and `Complete`. Count each unit and gate once. Normalize gates to `passed`, `pending`, `failed`, `unknown-definition`, or `conflicting`. `unpassed` is `pending` only when definition, owner, command, and inputs are present. Gates may be shared by multiple Units, but Unit `gate_refs` and Gate `owners` are reciprocal and each selected Gate owns the selected Unit. A planned input change invalidates `passed` to `pending`; closure requires post-change evidence. A failed gate requires its unit to be Failed/Blocked with recovery, otherwise state is conflicting. A Ready unit must transition `Ready -> Claimed -> In Progress`; encode this chain in machine fields as `Ready->Claimed,Claimed->In Progress`; direct `Ready -> Complete` is invalid.

Selection records dependency state, critical-path effect, Selection basis, and Current executable unit. Every blocker has stable ID, owner, detail, recovery, and evidence. Every open unit has a next convergence condition.

Blocked output preserves each blocker or prerequisite identity, detail, and recovery; capability identity includes the exact plugin/tool name. Migration/permission/release blockers use `High-risk` status and explicitly name migration, rollback, permission, and release conditions. Before the trace, High-risk Consumer/Compatibility/Rollback copy exact `affected_consumer`/`compatibility_gate`/`rollback_evidence`; Migration/Release use exact applicable facts. Trace cells 6 and 8 both contain exact `nearest_test`; Gate receipt evidence may be appended to cell 8, never substituted.

## Future Execution Contract

Each step is a fixed machine-parseable record in this order:

```text
Step: <positive integer>
Action:
Command:
Files/boundary:
Acceptance Gate: <predicate>; exit=<0|n/a>
Expected transition:
Evidence required:
Failure/recovery:
```

`Repository` is exactly `.`, `Authoritative inputs` exactly equal ledger IDs, and `Owner boundary` is exactly the selected owner plus nearest test. UTF-8-sort every JSON path array before output, including each `Files/boundary`; each boundary is a canonical subset. `Action` is `observe|implementation|test|tracker: <action>`; observe is restricted to the enumerated exact read-only Git forms without shorthand, implementation/tracker are structured edits whose `Command` is `none: <reason>`, and tests use an exact selected-Gate command. `Acceptance Gate` ends exactly in ASCII `; exit=0` for a concrete command or `; exit=n/a` for `none:`; no text follows the value. Baseline is a current owner fact, not a Gate state; omit implementation when the owner already satisfies the goal. Only tracker changes state, and implementation/test/tracker each require matching matrix authorization. Every step/receipt owner is the exact selected Unit owner path, never its claim identity. Tests use `gate=none`, never no-op `X->X`; metadata changes merge into the next real Gate transition instead of creating a transitionless tracker step. Expected transitions use the snapshot revision through and including the first Unit/Gate edge; only later steps use `observed-prior`, and no future revision is predicted. `Evidence required` binds each state-changing boundary to a safe receipt path and uses comma-separated artifacts without internal semicolons. Only the executor emits actual receipts. Expected/observed state, Gate, and evidence paths reconcile per boundary.

The snapshot `from_revision` value is the exact tracker-revision scalar, never a composite with branch, HEAD, or status.

Closure requires owner behavior, nearest regression, affected consumers when applicable, post-change acceptance, final diff/status, actual revision chain, expected/observed reconciliation, and a post-closure next unit derived from the result dependency graph. After hypothetical closure, next candidates include each remaining `Claimed`/`In Progress` unit and each dependency-ready `Ready` unit; a Ready candidate need not already be claimed, and multiple candidates block. The generator describes receipts only in the named requirement fields and never emits lines starting `observed_receipt:` or `post_closure_next_unit:`; the executor formats them after persistence. `Selected required gates` lists every Gate for the selected unit, including passed; `Complete` is legal only when all are passed. Commit, version, tag, push/release, and deployment permissions remain separate. Use this matrix once:

```text
Implementation | Tests | Update tracker | Local commit | Change version | Tag | Push/release
```

Matrix states are exactly `authorized|not authorized|blocked` and must agree with body permission fields. Evidence is `request`, a shortest space-free authority ID, or `absent`; authorized/blocked never use `absent`. Push and Release share the matrix's Push/release state, and planned state changes require authorized tracker updates with safe receipt paths. Each step's `gate=` is one Gate edge or `none`.

Preamble and body have separate UTF-8 hard caps: 4096/6144/8192 and 5632/10240/14336. Draft to 85% of each cap, reserving the remainder for exact copied fields, then count UTF-8 bytes. Compress and recount before emission; never emit beyond a hard cap, and block if compression cannot fit. Executable preamble is exactly one localized status line followed by the ten declared summary lines; Light/Standard body has exactly eight declared fields before the trace. Line labels use literal `: `; inner schema keys retain `=`. Each step's authored Action, Acceptance Gate, and Failure/recovery values total at most 420 UTF-8 bytes for Light/Standard and 640 for High-risk; exact evidence fields, commands, paths, and schema literals are exempt. Permission evidence is the shortest authority ID or `absent`, never a sentence. Keep every schema field on its own line. A verified-owner Light plan uses exactly test, closure, and final status; preflight is allowed only when rereads disagree, and known dirty status alone is not drift. Split Gate invalidation and change at most one Gate per step. Combine owner and nearest-test edits; merge the final Gate pass with unit closure. Each trace uses only literal ` -> ` separators, starts with the exact selected-unit goal, and is followed immediately by `Permission matrix:`; Owner change starts with the exact owner path, and Test/Evidence each start with the exact nearest-test path, with Gate evidence appended only afterward. Open inventory remains open-only; selected Gates include passed entries. Its top-level key order is `units,gates,blockers`, row keys retain their declared order, and rows are ID-sorted. The template requires verbatim rows and maps `unit.next` only from that Unit's exact `next_convergence_condition`, never `next_step` or `recovery_condition`; Gate command/recovery and blocker recovery also come from their own rows. Exceeding the budget blocks.

## Repository And Evaluation Contract

- Runtime is exactly `skill/SKILL.md`, `skill/agents/openai.yaml`, and `skill/scripts/status_fingerprint.py`; `SKILL.md` is the sole normative instruction source.
- README, this spec, validators, runners, corpus, and release evidence describe the same read-only generator and post-capture boundary.
- Static validation proves syntax, schema, safety, and artifact consistency only; it does not prove model behavior or final-channel delivery.
- Generic evaluation archives canonical tracker grounding plus bounded raw pre/post state manifests. Runner, publisher, and repository replay independently derive generated snapshot, ledger, counts, inventory, selection, selected Gates, and side-effect claims. Base64 grounding is decoded and scanned before publication; sensitive non-tracker evidence is replayed by digest rather than archived source text.
- Product evaluation gives generation only a realistic request and execution only the generated handoff plus a generic execute request. The publisher recomputes generated facts, then reconciles steps with raw before/after evidence, derives the next unit from tracker-after, and validates both paths of every diff header. Success requires first effective action 1, zero invalid clarifications/boundary violations, and acceptance/closure rates of 1.
- Publisher and default/release validation replay semantics, artifact references, source bindings, product metrics, transitions, representative projection, and exact case set. A hardcoded `pass` or declaration-only summary cannot authorize release.
- A pending fresh corpus is deterministic development evidence only. Release mode must return `RELEASE BLOCKED` and non-zero until complete evidence is published.

## Non-Goals

- No tracker mutation or future-task execution during generation.
- No pre-delivery audit or delivery claim.
- No complete-history dump, unsupported percentage, competing designs, declaration-only metrics, or unsupported acceptance claim.
- No reference graph or hidden runtime dependency; the one read-only script is exact-tree validated and source-bound without being loaded as prompt text.
