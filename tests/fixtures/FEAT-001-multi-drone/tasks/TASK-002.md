# TASK-002 — Route commands to the selected vehicle

**Purpose:** Make every command path go out through exactly one selected session.
**Depends on:** TASK-001 · **Risk:** high · **Human review:** required

## Acceptance criteria
- AC-T2-1: commands are refused when no vehicle is selected
- AC-T2-2: a target switch during a pending ACK applies after the ACK or timeout

## Change boundary
`src/command/router.py`. Anything outside goes back through `hr scope-change`.

## Verification
| Test | Command / procedure | Result |
|---|---|---|
| TEST-002 | `pytest tests/unit/test_command_router.py` | not run |

## Result
Not implemented yet.
