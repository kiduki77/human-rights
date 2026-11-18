# TASK-004 — Vehicle selection UI

**Purpose:** Let the operator pick the target unambiguously and always see which vehicle is selected.
**Depends on:** TASK-002 · **Risk:** medium · **Human review:** optional

## Acceptance criteria
- AC-T4-1: the selected vehicle is highlighted and command buttons show its name

## Change boundary
`src/ui/vehicle_selector.py`. Anything outside goes back through `hr scope-change`.

## Verification
| Test | Command / procedure | Result |
|---|---|---|
| TEST-004 | `pytest tests/ui/test_vehicle_selector.py` | not run |

## Result
Not implemented yet.
