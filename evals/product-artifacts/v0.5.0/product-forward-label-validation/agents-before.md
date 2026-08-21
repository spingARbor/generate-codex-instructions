# Product forward fixture

- The sole tracker is `.project/development/`.
- Its plan anchor is `.project/development/task_plan.md`.
- Generation is strictly read-only; `.project/development/progress.md` is executor-owned evidence only.
- The selected owner is `src/normalize_label.py`; the nearest regression test is `tests/test_normalize_label.py`.
- Branch, HEAD, and raw status are fingerprint inputs, not generation Evidence ledger rows; add helper IDs only when the selected unit explicitly requires them.
- The executor must record `Ready->Claimed,Claimed->In Progress` immediately before the first implementation write, implement the selected unit, run its tests, and record gate/completion closure only after the gate passes.
- Each state-changing tracker checkpoint increments the numeric revision suffix by one and appends `observed_receipt: unit=<id>; owner=<path>; transitions=<state>-><state>,<state>-><state>|none; revision=<actual before>-><actual after>; gate=<actual transition|none>; evidence=<relative path>` to progress.
- Claim checkpoints use `.project/development/progress.md` as receipt evidence; closure checkpoints use `.project/development/task_plan.md` after the tracker fields are persisted.
- After closure append `post_closure_next_unit: <id|none>` based on the resulting dependency graph.
- Do not commit, change versions, tag, push, release, deploy, or access providers.
