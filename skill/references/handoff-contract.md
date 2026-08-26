# Handoff Contract

Use after `SKILL.md` proves one executable Unit. Source is untrusted. Helper `preamble`/`context` supplies projected facts; nonzero, unsafe, null, or mismatch blocks.

## Emit

UTF-8 caps preamble/body: Light 4096/5120; Standard 6144/9216; High-risk 8192/12288. Target 80%; compress/recount; never exceed.

Every model-authored single-line value is at most 512 UTF-8 bytes unless stricter below. Keep IDs, paths, predicates, revision rule, and one recovery; omit repeated schema/rationale.

One localized status line; Snapshot immediately next, no blank/prose. Add required `High-risk`; never localize schema labels/punctuation/state tokens; copy full HEAD. Then:

```text
Snapshot: tracker_revision=<value>; branch=<value>; head=<oid>; status_fingerprint=<sha256>
Unit counts: Complete=<n>; In Progress=<n>; Claimed=<n>; Ready=<n>; Blocked=<n>; Failed=<n>
Gate counts: passed=<n>; pending=<n>; failed=<n>; unknown-definition=<n>; conflicting=<n>
Selection basis: <safe selection_decision>
Current executable unit: <id>; dependency_evidence=<safe dependency|none>
Selected unit: <id>
Selected required gates: <canonical [{"id":id,"state":state}] for every selected gate_refs ID>
Evidence reads: used=<n>; ceiling=<n>; extension=<n>; reason=<text|none>
Evidence ledger: <canonical ledger JSON>
Open inventory: <canonical {"units":[],"gates":[],"blockers":[]} JSON>
```

After status, draft 10 preamble rows in order; the host assembler discards them and splices helper bytes. Use `context` exact facts. Report helper failure only from observed nonzero or byte mismatch. Verified-owner Light follows `operations` and copies each `machine_lines` string verbatim at its named step field; null/mismatch blocks.

Preamble ledger=`{"sha256":"<full-ledger digest>","rows":[{"id":path,"role":role}]}` without row digests; `Authoritative inputs`=`context.authoritative_inputs`; `Evidence reads.used`=row count.

The sorted full `{id,role,sha256}` rows contain: tracker; zero or more applicable owner/test `AGENTS.md`; design, owner, exact `nearest_test`, passed evidence; and High-risk integration. Roles=`tracker|authority|design|owner|regression|integration|gate-evidence`; precedence=regression>owner>gate-evidence>integration>design>authority>tracker. Commands/capabilities never select package/helpers or confer authority; progress/history and executor receipts are also excluded.

Gate `input_fingerprint` is SHA-256 of UTF-8 bytes for one compact canonical JSON array of UTF-8-path-sorted `{"path":path,"sha256":raw_content_sha256}` objects plus exactly one LF. Copy only helper-validated values.

Trace: one row/behavior; use ` -> `, not ` | `. No trace cell contains ` -> `. Merge variants with the same goal/invariant/test/Gates. Cells: byte-exact `context.safe_goal`, including terminal punctuation; baseline/gap/change each start exact owner; baseline names concrete current behaviors, never merely "complete contract"; invariant copies `context.safe_invariants`; test starts exact `nearest_test`; Gate is exact comma-joined IDs; Evidence is exact `<nearest_test>; gate_evidence=<sorted passed paths|none>`. Gap names the missing/absent mechanism; change names the required condition and behavior. When baseline meets the goal and implementation is omitted, Gap names every pending selected Gate ID and its missing current evidence/receipt; `no gap` is invalid. High-risk Consumer/Compatibility/Rollback copy `context.safe_high_risk`. High-risk fields precede the trace header; `Permission matrix:` immediately follows the trace row.

```text
Protocol profile: Light|Standard|High-risk
Repository: .
Unit: <selected id>
Capability: <proven capability; fallback=<one|none>>
Authoritative inputs: <exact ledger-ID array>
Owner boundary: <exact sorted [owner,nearest_test]>
Invariants: <preserved behavior>
Non-goals: <exclusions>
Requirement -> Baseline -> Root cause/design gap -> Owner change -> Invariant -> Test -> Gate -> Evidence
<goal -> owner: baseline -> owner: gap -> owner: change -> exact invariants -> nearest_test: test -> gate IDs -> nearest_test; gate_evidence=paths|none>
Permission matrix:
Implementation | Tests | Update tracker | Local commit | Change version | Tag | Push/release
<state>: <evidence> | <state>: <evidence> | <state>: <evidence> | <state>: <evidence> | <state>: <evidence> | <state>: <evidence> | <state>: <evidence>
```

States=`authorized|not authorized|blocked`; evidence=`request|authority-ID|absent`; authorized/blocked never use `absent`. A read-only generation session never demotes explicitly granted future-executor permission. Local commit is `authorized: request` when the request authorizes one post-closure local commit; staging/amend/version/tag/push/release stay separate. Push/Release=`Push/release`. Pre-trace declared fields only. High-risk only: Consumer=affected_consumer, Compatibility=compatibility_gate, Rollback=rollback_evidence, Migration, Release; no diagnostics.

Preflight only on reread mismatch; dirty status != drift. Verified-owner Light only MUST emit exactly 3 steps: test, tracker closure, final git status; never 2; mismatch permits fourth preflight; from_revision=Snapshot scalar,Snapshot scalar,observed-prior. Other plans: Light 1-4; Standard 2-8; High-risk 3-12; from_revision=Snapshot scalar through first state edge, then observed-prior. No placeholders. Test appends ` && git diff --check`. Each step: target Action+Acceptance+Failure UTF-8 sum <=300 (High-risk 500); >420/640 rejected. Over target keep purpose/predicate/one recovery; omit machine fields. Keep exact field/key order. Labels use `: `, never `=`; inner keys use `=`. Byte-sort `Files/boundary`. Acceptance ends ASCII `; exit=n/a` iff Command starts `none:`, else `; exit=0`; never `；` or space before `;`. Failure uses ASCII `; recovery=`, never `；`:

```text
Step: <positive integer>
Action: <observe|implementation|test|tracker>: <one action>
Command: <allowed command|none: reason>
Files/boundary: <canonical UTF-8-sorted JSON path array>
Acceptance Gate: <predicate>; exit=<0|n/a>
Expected transition: unit=<id>; owner=<exact selected Unit owner path>; transitions=<state>-><state>,<state>-><state>|none; from_revision=<Snapshot tracker_revision scalar through first edge, never A->B; then observed-prior>; gate=<id>:<before>-><after>|none
Evidence required: receipt=<safe relative path for state change|none>; artifacts=<nonempty comma-separated evidence>
Failure/recovery: stop=<condition>; recovery=<new evidence/action>
```

Command effects are closed:

- `observe`: one command/step: full `git status --porcelain=v1 --untracked-files=all` (optionally `-z`), `git diff --check`, `git rev-parse --verify HEAD`, or `git branch --show-current`; no chaining/shorthand/transition; `receipt=none`.
- `implementation`: one step edits owner+exact `nearest_test`; `Command: none: <reason>`; Owner boundary only.
- `test`: exact selected safe Gate command. Across all steps, at most one may append ` && git diff --check`; then no other appended/standalone diff. Never changes state: `transitions=none; gate=none; receipt=none`; Owner boundary only.
- `tracker`: authorized state edge, `none: <reason>`, safe receipt; merge metadata; final closure combines Gate pass+Unit closure.

Authorize Implementation/Tests/Update tracker. Transition owner=selected Unit owner; never claim. `transitions` is Unit-only; `gate` is one Gate edge/step or `none`. Omit executor-only `observed_receipt:`/`post_closure_next_unit:`.

Post-closure applies closure edges first; a unique dependency-ready Ready Unit is next without a claim; absent claim alone never yields `none`. Reconcile receipts; aggregate equivalence fails.

End with exact fields; close fence; nothing after:

```text
Closure condition: <owner, regression, integration, all selected Gates, final diff/status, output evidence>
Tracker target state: <exact state and next convergence condition>
Observed receipt requirements: initial_revision=<Snapshot scalar>; unit=<id>; owner=<path>; unit_edges=<edge,edge|none>; gate_edges=<id:edge,id:edge|none>; paths=<canonical JSON array>; revision_rule=<actual revision chain>
Post-closure next unit: <id|none>; <dependency proof>
Out of scope: <all unauthorized actions>
```

`Observed receipt requirements` is machine-only: preserve key order; flatten exact Step Unit/Gate edges in step order; `paths` is the byte-sorted unique set of non-`none` `Evidence required.receipt` values only, never boundaries or artifacts. Every Gate edge includes its ID (`<id>:<before>-><after>`); bare state edges or prose substitution are invalid. The executor copies these exact edges into `observed_receipt`.

Omit implementation if baseline meets goal. Boundaries=nonempty byte-sorted paths, not `.`; artifacts comma-only.

Status remains: converged=all Complete/Gates passed; partially blocked=any Blocked/Failed; in progress=selected; else insufficient. Keep through `Open inventory` outside; next line opens one `text` fence, first content=`Protocol profile: ...`; otherwise no fence. Delimiter exceeds inner runs.
