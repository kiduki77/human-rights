# Multi-vehicle connection and selected-vehicle control — awaiting design approval

## Conclusion
Replace the GCS's single global connection with per-vehicle sessions, so up to 4 vehicles stay connected and commands go only to the selected one. The design is ready for approval.

<!-- hr:status:start -->
<!-- hr:status:end -->

## What changes and why
Operators today must reconnect to switch vehicles, which loses telemetry from the others. This change keeps up to 4 links open and routes every command through one explicitly selected vehicle. Swarm commands and collision avoidance are out of scope.

## Key changes
| Area | Today | After |
|---|---|---|
| Connection | one global `Connection` | `VehicleRegistry` of sessions keyed by system_id |
| Commands | sent to "the" connection | sent only to the selected session; target switches wait for the pending ACK |
| Failures | one link drop stalls the GCS | per-vehicle reconnection, others unaffected |

Safety decisions confirmed by the user: deselected vehicles keep their mission (DEC-002); target switches wait for the ACK or a 3 s timeout (DEC-003).

<!-- hr:tasks:start -->
<!-- hr:tasks:end -->

## Verification
<!-- hr:results:start -->
<!-- hr:results:end -->

Not verified: nothing has run yet (design stage). TEST-013 is a human check with screen recording.

## Decisions and assumptions
<!-- hr:decisions:start -->
<!-- hr:decisions:end -->

## Decision needed
Approve the design, point at anything that looks wrong, or request changes. Check the two safety decisions above, and whether the pass criteria in the verification table are enough to call this done.

---
Details: [requirements](requirements.md) · [design](design.md) · [verification plan](verification.md) · [code investigation](details/codebase.md)
