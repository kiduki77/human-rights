# Requirements — multi-vehicle connection and control

**Summary:** One operator monitors and commands up to 4 vehicles from one GCS without reconnecting, and commands never reach a vehicle that is not selected.

## Scope
| In | Out |
|---|---|
| Up to 4 simultaneous connections | Swarm commands (one command to many vehicles) |
| Vehicle selection UI | Collision avoidance between vehicles |
| Command routing to the selected vehicle | Multiple remote GCS instances |
| Per-vehicle link failure isolation | |

## Confirmed decisions
| ID | Question | Decision | Decided by |
|---|---|---|---|
| DEC-001 | Maximum vehicles | 4 | user |
| DEC-002 | Deselected vehicle keeps its mission? | Yes, no automatic LOITER (safety) | user |
| DEC-003 | Target change while a command is in flight | After ACK or 3 s timeout (safety) | user |
| DEC-004 | Link protocol | Keep the existing MAVLink library | existing code |

## Requirements and acceptance criteria
| Requirement | Priority | Acceptance criteria |
|---|---|---|
| REQ-001 Up to 4 vehicles connected at once | must | AC-001: 4 SITL vehicles for 10 min, heartbeats at most 1 s apart |
| REQ-002 Commands only to the selected vehicle | must | AC-002: with B selected, every command targets B; A/C/D receive none |
| REQ-003 Telemetry never mixes | must | AC-003: each panel shows only its own system_id |
| REQ-004 One link failure does not affect others | must | AC-004: with A cut, B's command latency within baseline +50 ms |
| REQ-005 Single-vehicle workflow unchanged | must | AC-005: all single-vehicle regression tests pass |
| REQ-006 Deselected vehicle keeps its mission | must | AC-006: switching A to B leaves A's mode and waypoint progress unchanged |

## Proposed defaults and assumptions
- Q-002 (non-blocking): a 5th connection attempt shows the toast "Up to 4 vehicles can be connected".
- ASM-001 (low risk): system_ids are unique; a duplicate is refused.

## Open items
None blocking.

> Source of truth: `.internal/requirements.json` (revision 2)
