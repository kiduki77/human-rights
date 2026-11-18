# TASK-003 — Per-vehicle reconnection

**Purpose:** Isolate link failures so they do not propagate to other vehicles.
**Depends on:** TASK-001 · **Risk:** high · **Human review:** required

## Acceptance criteria
- AC-T3-1: disconnecting one vehicle does not change any other vehicle's connection

## Change boundary
`src/link/reconnect.py`. Anything outside goes back through `hr scope-change`.

## Verification
| Test | Command / procedure | Result |
|---|---|---|
| TEST-003 | `pytest tests/integration/test_reconnection.py` | not run |

## Result
Not implemented yet.
