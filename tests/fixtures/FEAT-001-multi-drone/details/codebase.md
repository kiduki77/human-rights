# Code investigation — multi-vehicle connection and control

**Summary:** The GCS holds exactly one global connection, every command helper reads it directly, and telemetry handlers key nothing by system_id. Those three facts drive the design.

| # | Finding | Evidence | Status |
|---|---|---|---|
| 1 | A single module-level connection object is created at startup | `src/link/conn.py:12` (illustrative) | Verified |
| 2 | Command helpers call `conn.send()` without a target | `src/command/*.py` (illustrative) | Verified |
| 3 | Telemetry handlers overwrite one shared state dict | `src/telemetry/state.py:30-58` (illustrative) | Verified |
| 4 | The MAVLink library supports several connections per process | library docs for the pinned version | Inferred |

## Reusable modules and tests
The existing single-vehicle regression suite (`tests/regression`, marker `single_vehicle`) becomes TEST-012.

## Impact and constraints
- Compatibility: single-vehicle flows must keep working (REQ-005).
- Concurrency: one receive loop per session; the registry is the only shared structure.
- Performance: 4 telemetry streams at 10 Hz each.
- Security / safety: command targeting is the safety boundary (DEC-002, DEC-003).

> Paths, symbols and commands in this example are illustrative, not the result of analysing a real GCS repository.
