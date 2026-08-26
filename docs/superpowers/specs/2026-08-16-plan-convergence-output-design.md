# Plan Convergence Output Design v2

## Goal

Generate a concise, sanitized plan-convergence preamble followed by one reusable, executable `text` handoff. The generator is read-only. Exact-response audit belongs to a host/evaluator after it captures the assistant message.

The model response is a draft. A host-only deterministic assembler discards its candidate ten-line preamble, recomputes helper context/preamble twice, splices trusted bytes, and emits the only final artifact. No model pass occurs after assembly.

Implementation, testing, review, and execution requests stop this skill and continue the appropriate non-generation workflow. The loaded `SKILL.md` is read exactly once, never tailed or reread. An instruction fence is legal only after proving exactly one selected executable unit. Insufficient, blocked, and converged responses contain only status, evidence, and decision/recovery, then end; they never echo evaluator instructions or contain a fence or implementation directive. Every blocker output names the exact blocker ID, owner, detail, and recovery; unsafe projected-field output uses explicit `Blocked` or `阻塞`, names the field and correction owner, and omits its value.

## Design Philosophy

- **Concise:** load and emit only decision-relevant evidence. Enforce discriminating discovery metadata, progressive disclosure, the smallest valid profile, bounded evidence/bytes/steps, and no duplicated rationale or closed history. Concision never removes a closure-critical fact.
- **Rigorous:** fail closed on ambiguity, unsafe effects, drift, or unproven closure. State, permission, command effect, transition, and release claims require canonical schemas, negative vectors, bounded stopping conditions, and independent replay. Structural validity alone is not behavioral proof.
- **Accurate:** bind every material claim to current repository bytes, tracker revision, owner, Gates, and permission evidence. Never guess, fabricate, silently change source meaning, or substitute stale/planned/model-declared facts for current observations.

The principles are conjunctive: concise output must remain rigorous and accurate; rigor must not accumulate irrelevant rules; missing accuracy produces a bounded blocker and recovery path rather than speculative detail.

Report helper validation failure only from observed nonzero or byte-mismatched runs. Read-only generation never demotes future-executor permission: when the request grants one post-closure local commit, `Local commit` is `authorized: request`; staging, amend, version, tag, push, and release remain separate.

Model tool evidence permits one complete four-call helper protocol or one complete symmetric retry, never a partial or third group. Non-executable `tracker: none` status may use localized punctuation/Markdown quoting while preserving the literal value and read-only meaning.

## Output Contract

For one safely selected executable unit, begin with the exact localized status class plus any required fixed `High-risk` token while preserving schema labels, protocol punctuation, and canonical state tokens byte-for-byte, then emit exactly one concise reusable text fence:

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

The fence begins with the exact line `Protocol profile: Light`, `Protocol profile: Standard`, or `Protocol profile: High-risk`, followed by one causal trace row per active acceptance behavior under `Requirement -> Baseline -> Root cause/design gap -> Owner change -> Invariant -> Test -> Gate -> Evidence`. Variants sharing one goal/invariant/test/Gate set stay in one row; duplicate requirement rows are invalid. No trace cell contains ` -> `. Baseline names concrete current behaviors, never merely "complete contract"; gap names the missing/absent mechanism; change names the required condition and behavior. High-risk fields precede the trace header; `Permission matrix:` immediately follows the trace row. The Gate cell is bare comma-joined selected Gate IDs. The fence contains failure-bounded steps, post-change validation, expected transitions, observed-receipt requirements, and closure proof. A converged, unsafe, ambiguous, or unavailable plan returns concise plain text without the executable template.

## Profiles

- `Light`: documentation, simple configuration, or one-owner-file work without runtime behavior, public API, data, permission, concurrency, release, provider, or untrusted-input impact. A Gate command alone does not escalate docs/config.
- `Standard`: ordinary one-module runtime behavior and focused regression work without a High-risk boundary.
- `High-risk`: cross-module/public interfaces, data or migrations, permissions, concurrency, publishing/release/provider effects, or untrusted-input boundaries.

All profiles retain root/owner resolution, physical containment, untrusted-data handling, redaction, unrelated-change preservation, tracker transitions, authorization, and ambiguity-as-blocker. Runtime behavior is at least Standard and High-risk surfaces always escalate. Default distinct evidence-object ceilings are 6/12/20 with one named-fact half-ceiling extension; a second exhaustion blocks. A canonical Light/Standard evidence ledger binds exactly one governing tracker, every applicable `AGENTS.md` from repository root through the selected owner and nearest-test directories, selected design/owner/exact nearest test, and selected passed-Gate evidence by fixed role (`tracker|authority|design|owner|regression|integration|gate-evidence`) and digest copied byte-for-byte from observed output and self-checked before emission; High-risk adds selected integration even when it is also the package surface. Gate commands and capabilities never select package/helpers or turn them into authority; no other row is allowed. Role substitution, progress/lessons, and executor receipts are excluded. When one path has several roles, precedence is regression, owner, gate-evidence, integration, design, authority, then tracker.

## Snapshot Consistency

Resolve one physical repository/worktree root and one governing tracker from an explicit request/authority or a sole project tracker convention. Tracker discovery includes ignored paths; `.gitignore` never hides a governing tracker. Treat tracker and repository text as untrusted data. Restore authoritative counts, all open units, gates, claims, dependencies, blockers, selected-unit evidence, and directly relevant code/tests; never invent a tracker, ID, owner, conflict, or blocker. A governing tracker is a prerequisite unless the project explicitly supplies a read-only `tracker: none` projection. Apply zero or more physical root-to-owner/test `AGENTS.md` files. An empty applicable authority set never invalidates or demotes a uniquely resolved governing tracker and never requires restoring `AGENTS.md` as recovery.

Use `status-fingerprint-v1`: fixed-order version, branch, lowercase HEAD, raw `git status --porcelain=v1 -z --untracked-files=all`, UTF-8-path-sorted records of path plus the 32-byte raw-content SHA-256, tracker revision, and canonical selected-evidence JSON. Selected evidence has fixed keys `unit,owner,gates,evidence,ledger_sha256`; the final field binds the exact canonical full `{id,role,sha256}` evidence ledger plus LF. Every field uses an unsigned 64-bit big-endian length prefix. Snapshot stability is a precondition to conditional disclosure. Only after one stable provisional executable unit and complete profile evidence are proven, resolve `<skill-root>` from the loaded `SKILL.md`, read exactly `<skill-root>/references/handoff-contract.md`, and run `python3 "<skill-root>/scripts/status_fingerprint.py"` with repository, tracker, unit, profile, and `--emit context|preamble`; never enumerate the package or read helper source. Ordinary blocked/converged/insufficient output uses neither conditional resource. A provisional executable rejected by helper safety may complete the exact protocol and return a no-fence blocker without exposing helper details. The helper derives and validates owner, Gates, evidence membership, role precedence, digests, Gate inputs, bounded safe projected text, and a closed local-test command effect. Run each mode twice and byte-compare it. Copy the complete pure-text ten-line preamble stdout verbatim and use the short context JSON; nonzero, mismatch, unsafe, or null blocks. Recompute once after the first input drift. A second drift is terminal before any reference read or helper execution. A second-drift blocker states the fingerprint identity, exactly one recomputation, the second drift, and the blocked result. The Snapshot copies the exact full HEAD OID without truncation.

## Generator Side-Effect Boundary

The generator must not write tracker state, progress, claims, audits, checkpoints, locks, project files, Git state, dependencies, provider state, or temporary artifacts. It must not claim that any such write occurred. Post-capture host/evaluator auditing is outside the generation proof.

## Gate State Machine

Use canonical unit states `Ready`, `Claimed`, `In Progress`, `Blocked`, `Failed`, and `Complete`. Count each unit and gate once. Normalize gates to `passed`, `pending`, `failed`, `unknown-definition`, or `conflicting`. `unpassed` is `pending` only when definition, owner, command, and inputs are present. Gates may be shared by multiple Units, but Unit `gate_refs` and Gate `owners` are reciprocal and each selected Gate owns the selected Unit. A planned input change invalidates `passed` to `pending`; closure requires post-change evidence. A failed gate requires its unit to be Failed/Blocked with recovery, otherwise state is conflicting. A Ready unit must transition `Ready -> Claimed -> In Progress`; encode this chain in machine fields as `Ready->Claimed,Claimed->In Progress`; direct `Ready -> Complete` is invalid.

Gate `input_fingerprint` is SHA-256 over UTF-8 bytes of one compact canonical JSON array of UTF-8-path-sorted `{"path":path,"sha256":raw_content_sha256}` objects plus exactly one LF; it is not JSONL. The model never hand-computes or trusts its own digest. After provisional selection, only helper validation may accept or reject this field.

Projected free text is bounded to 512 UTF-8 bytes and fails closed on control characters, fence-shaped content, embedded authority-bypass/disclosure directives, credential markers, URLs, or host-private paths. Never echo a rejected value. A Gate command is executable only when it is one local test command without shell control/redirection/substitution, URL/network/destructive tools, inline interpreter code, package installation, unbound scripts, arbitrary package scripts, or mutating formatters. Package wrappers may name only test/check/lint/verify/type targets; otherwise classify the Gate as `unknown-definition` with owner recovery.

Selection records dependency state, critical-path effect, Selection basis, and Current executable unit. Every blocker has stable ID, owner, detail, recovery, and evidence. Every open unit has a next convergence condition.

Status classification uses Unit states and valid selection only: all Complete/passed is converged; any Unit state `Blocked`/`Failed` is partially blocked; a valid executable selection is in progress; otherwise it is insufficient. Invalid claim/owner/Gate evidence removes selection. A blocker record, `unknown-definition`, or resolution failure alone never creates a partially-blocked Unit state.

Blocked output preserves each blocker or prerequisite identity, detail, and recovery; capability identity includes the exact plugin/tool name. Migration/permission/release blockers use `High-risk` status and explicitly name migration, rollback, permission, and release conditions. Before the trace, High-risk Consumer/Compatibility/Rollback copy exact `affected_consumer`/`compatibility_gate`/`rollback_evidence`; Migration/Release use exact applicable facts. Trace requirement copies the exact Unit goal including terminal punctuation; baseline/gap/change/test cells start with their exact owner/owner/owner/nearest-test source, invariant copies the exact Unit field, Gate equals the selected Gate IDs, and Evidence is exactly `<nearest_test>; gate_evidence=<sorted selected passed_evidence paths|none>`; pending Gates cannot claim pass evidence. When the baseline already meets the goal and implementation is omitted, Gap names every pending selected Gate ID and its missing current evidence or receipt; `no gap` is invalid.

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

`Repository` is exactly `.`, `Authoritative inputs` exactly equal ledger IDs, and `Owner boundary` is exactly the selected owner plus nearest test. UTF-8-sort every JSON path array before output, including each `Files/boundary`; each boundary is a canonical subset. `Action` is `observe|implementation|test|tracker: <action>`; observe is restricted to the enumerated exact read-only Git forms without shorthand, implementation/tracker are structured edits whose `Command` is `none: <reason>`, and tests use an exact selected-Gate command. `Acceptance Gate` ends exactly in ASCII `; exit=0` for a concrete command or `; exit=n/a` for `none:`; no text follows the value. Baseline is a current owner fact, not a Gate state; omit implementation when the owner already satisfies the goal. Only tracker changes state, and implementation/test/tracker each require matching matrix authorization. Every step/receipt owner is the exact selected Unit owner path, never its claim identity. Tests never change state and use `transitions=none; gate=none; receipt=none`; every Unit/Gate edge belongs to a tracker step with a safe receipt, never no-op `X->X`. Metadata changes merge into the next real Gate transition instead of creating a transitionless tracker step. Expected transitions use the snapshot revision through and including the first Unit/Gate edge; only later steps use `observed-prior`, and no future revision is predicted. `Evidence required` binds each state-changing boundary to a safe receipt path and uses comma-separated artifacts without internal semicolons. Only the executor emits actual receipts. Expected/observed state, Gate, and evidence paths reconcile per boundary.

The snapshot `from_revision` value is the exact tracker-revision scalar, never a composite with branch, HEAD, or status. `Observed receipt requirements` is a fixed machine record in key order `initial_revision; unit; owner; unit_edges; gate_edges; paths; revision_rule`. It flattens exact Step edges in order; `paths` is the byte-sorted unique set of non-`none` `Evidence required.receipt` values only, excluding boundaries/artifacts. Every Gate edge is `<id>:<before>-><after>` and is copied into the executor receipt; bare state edges or prose substitution are invalid.

Closure requires owner behavior, nearest regression, affected consumers when applicable, post-change acceptance, final diff/status, actual revision chain, expected/observed reconciliation, and a post-closure next unit derived from the result dependency graph. After hypothetical closure, next candidates include each remaining `Claimed`/`In Progress` unit and each dependency-ready `Ready` unit; a Ready candidate need not already be claimed, and multiple candidates block. The generator describes receipts only in the named requirement fields and never emits lines starting `observed_receipt:` or `post_closure_next_unit:`; the executor formats them after persistence. `Selected required gates` lists every Gate for the selected unit, including passed; `Complete` is legal only when all are passed. The closing fence follows `Out of scope`, with no content after it. Commit, version, tag, push/release, and deployment permissions remain separate. Use this matrix once:

```text
Implementation | Tests | Update tracker | Local commit | Change version | Tag | Push/release
```

Matrix states are exactly `authorized|not authorized|blocked` and must agree with body permission fields. Evidence is `request`, a shortest space-free authority ID, or `absent`; authorized/blocked never use `absent`. Push and Release share the matrix's Push/release state, and planned state changes require authorized tracker updates with safe receipt paths. Each step's `gate=` is one Gate edge or `none`.

Preamble and body have separate UTF-8 hard caps: 4096/6144/8192 and 5120/9216/12288. Draft to 80% of each cap, reserving the remainder for exact copied fields, then count UTF-8 bytes. Compress and recount before emission; never emit beyond a hard cap, and block if compression cannot fit. Executable preamble is exactly one localized status line followed by the ten declared summary lines; Light/Standard body has exactly eight declared fields before the trace. Preserve every declared field and inner-key order exactly. Line labels use literal `: `; inner schema keys retain `=`; Failure/recovery uses literal ASCII `; recovery=`, never fullwidth `；`. Each step's authored Action, Acceptance Gate, and Failure/recovery values target 300 UTF-8 bytes for Light/Standard and 500 for High-risk, with hard rejection above 420/640; they state only purpose, predicate, and one recovery action rather than repeating machine fields. Exact evidence fields, commands, paths, and schema literals are exempt. Permission evidence is the shortest authority ID or `absent`, never a sentence. Keep every schema field on its own line. For every profile, preflight is allowed only when rereads disagree, and known dirty status alone is not drift; a verified-owner Light plan uses exactly test, closure, and final status, with its exact selected-Gate test command appending the single `&& git diff --check`. Its first two `from_revision` values copy the actual Snapshot `tracker_revision` scalar, and the third is `observed-prior`; literal `snapshot` is invalid. Split Gate invalidation and change at most one Gate per step. Combine owner and nearest-test edits; merge the final Gate pass with unit closure. Across the handoff, at most one test step may append `git diff --check`; when it does, no other appended or standalone diff check is allowed. Each observe step contains one allowed command and never chains commands. Each trace uses only literal ` -> ` separators, follows the exact eight-cell grounding rule above, and is followed immediately by `Permission matrix:`. Open inventory remains open-only; selected Gates include passed entries. Its top-level key order is `units,gates,blockers`, row keys retain their declared order, and rows are ID-sorted. The template requires verbatim rows and maps `unit.next` only from that Unit's exact `next_convergence_condition`, never `next_step` or `recovery_condition`; Gate command/recovery and blocker recovery also come from their own rows. Exceeding the budget blocks.

A verified-owner Light plan must emit exactly three steps--test, tracker closure, and final Git status--and never two; a fourth preflight is legal only after an actual reread mismatch. Only this Light shape uses the actual Snapshot scalar twice and then `observed-prior`. Every other plan uses the Snapshot scalar through and including its first state-changing step, then `observed-prior` for every later step; placeholders such as `snapshot` and `same` are invalid. Post-closure selection applies the generated closure edges before deriving candidates; a unique dependency-ready `Ready` Unit is next without a prior claim, and absent claim alone never produces `none`.

## Repository And Evaluation Contract

- Runtime is exactly `skill/SKILL.md`, `skill/agents/openai.yaml`, `skill/references/handoff-contract.md`, `skill/scripts/assemble_handoff.py`, and `skill/scripts/status_fingerprint.py`; `SKILL.md` owns shared decisions/routing and the reference owns only the conditional emission grammar.
- README, this spec, validators, runners, corpus, and release evidence describe the same read-only generator and post-capture boundary.
- Static validation proves syntax, schema, safety, and artifact consistency only; it does not prove model behavior or final-channel delivery.
- Behavior runners project every observed skill-package access from the complete Codex log. At most one explicit `SKILL.md` read and two metadata-only `readlink|realpath|stat|namei` observations of the exact named root/resources are legal. Executable results require exactly one conditional `references/handoff-contract.md` read plus exactly two `context` and two `preamble` helper invocations. Ordinary non-executable results require no conditional access; projection-safety blockers accept either none or one complete protocol, never a partial protocol. Repeated conditional reads, source reads, package enumeration, and undeclared paths fail. The canonical evidence binds raw-log bytes/SHA-256 and ordered access-line digests.
- Generic evaluation archives canonical tracker grounding, bounded raw pre/post state manifests, and the minimal package-access projection. Runner, publisher, and repository replay independently derive generated snapshot, ledger, counts, inventory, selection, selected Gates, side effects, and the projected access protocol. Fixture-specific semantic oracles separately validate known baseline/gap/change/test facts; the product case then reconciles those claims with actual execution evidence. Generic path/schema grounding alone is not semantic proof for arbitrary repositories, so ambiguity blocks rather than authorizing a guessed trace. Base64 grounding is decoded and scanned before publication. Raw Codex logs are not archived because they may contain untrusted tool output; projection completeness therefore depends on the source-bound runner, while projection ordering and protocol are independently replayable.
- Product evaluation records a canonical pre-generation `runtime-snapshot.json` for runtime, runner, corpus, and evaluator sources; publisher and repository replay must byte-match every entry to current sources, preventing stale-capture attribution. Generation receives only a realistic request and execution only the generated handoff plus a generic execute request. The publisher recomputes generated facts, reconciles steps with raw before/after evidence, derives the next unit from tracker-after, and validates both paths of every diff header. Success requires first effective action 1, zero invalid clarifications/boundary violations, and acceptance/closure rates of 1.
- Publisher and default/release validation replay semantics, artifact references, source bindings, product metrics, transitions, representative projection, and exact case set. A hardcoded `pass` or declaration-only summary cannot authorize release.
- A pending fresh corpus is deterministic development evidence only. Release mode must return `RELEASE BLOCKED` and non-zero until complete evidence is published.

## Non-Goals

- No tracker mutation or future-task execution during generation.
- No pre-delivery audit or delivery claim.
- No complete-history dump, unsupported percentage, competing designs, declaration-only metrics, or unsupported acceptance claim.
- No hidden, recursive, or unrelated reference graph. The single explicit handoff reference is conditionally routed after executable selection; the one read-only script is exact-tree validated and source-bound without being loaded as prompt text.
