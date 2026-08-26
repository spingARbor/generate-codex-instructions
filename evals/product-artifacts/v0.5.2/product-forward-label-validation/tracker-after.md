# Development tracker

schema_version: 2
tracker_revision: r3
goal: Enforce the documented empty-label validation contract.

## Unit registry

### U1

state: Complete
selected: true
priority: 1
independently_executable: true
goal: Reject empty and whitespace-only labels at the owner boundary.
owner: src/normalize_label.py
authoritative_design: docs/design.md
nearest_test: tests/test_normalize_label.py
scope: Change only the normalization owner and its focused regression test.
next_step: Add the ValueError guard and regression test, then run the focused unittest gate.
next_convergence_condition: G1 passes at the current tracker revision and the owner records U1 Complete.
gate_refs: G1
invariants: Valid labels remain trimmed; non-string values still raise TypeError; the public function path stays stable.
non_goals: API redesign, dependencies, packaging, version, commit, release, or unrelated refactor.

## Required gate registry

### G1

required: true
status: passed
gate_type: acceptance
owners: U1
command: python3 -m unittest discover -s tests -v
inputs_json: ["src/normalize_label.py","tests/test_normalize_label.py"]
input_fingerprint: 23abfbb27939616f74f9b21cb410fd23bef19010bc8209445341dda9dde3e54d
passed_evidence: python3 -m unittest discover -s tests -v; exit=0; tests=4; result=OK
evidence: The executor must run the acceptance command after the owner and regression test changes.
recovery_condition: Implement U1, run the exact acceptance command, and record the current passing result.

## Decisions and blockers

selection_decision: Select U1 because it is the sole Ready, independently executable unit and has no unmet dependency.
