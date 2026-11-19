# TASK-001 — Per-vehicle connection sessions

**Purpose:** Replace the global connection with a registry of sessions keyed by system_id.
**Depends on:** none · **Risk:** medium · **Human review:** optional

## Acceptance criteria
- AC-T1-1: sessions can be looked up, added and removed by system_id; duplicate ids are refused

## Flow
```mermaid
sequenceDiagram
  participant Link
  participant Reg as VehicleRegistry
  Link->>Reg: add(system_id, session)
  Reg-->>Link: refused if duplicate
  Link->>Reg: get(system_id)
  Reg-->>Link: session
```

## Change boundary
`src/link/registry.py`, `src/link/session.py`. Anything outside goes back through `hr scope-change`.

## Verification
| Test | Command / procedure | Result |
|---|---|---|
| TEST-001, TEST-012 | `pytest tests/unit/test_registry.py` | not run |

## Result
Not implemented yet.
