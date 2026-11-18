# Verification plan — multi-vehicle connection and control

**Summary:** Done when commands provably reach only the selected vehicle, link failures stay isolated, single-vehicle behaviour is unchanged, and a human has confirmed missions survive selection switches.

## Feature integration test plan
| Test | Requirements | Type | Environment | Pass criteria | Automated / human |
|---|---|---|---|---|---|
| TEST-010 | REQ-001, 002, 003 | e2e | sitl-4 | AC-001..003 | automated |
| TEST-011 | REQ-004 | integration | sitl-4 | AC-004 | automated |
| TEST-012 | REQ-005 | regression | sitl-1 | all pass | automated |
| TEST-013 | REQ-006 | safety | sitl-2 + operator | AC-006 + recording | human |

## Per-task verification
| Task | Test | Command / procedure |
|---|---|---|
| TASK-001 | TEST-001 | `pytest tests/unit/test_registry.py` |
| TASK-002 | TEST-002 | `pytest tests/unit/test_command_router.py` |
| TASK-003 | TEST-003 | `pytest tests/integration/test_reconnection.py` |
| TASK-004 | TEST-004 | `pytest tests/ui/test_vehicle_selector.py` |

## Results
<!-- hr:results:start -->
<!-- hr:results:end -->

## Residual risk
Real radio links behave differently from SITL; a field check is outside this feature and is noted for the release checklist.

> Source of truth: `.internal/test-plan.json`; results in `.internal/test-results.json` (only runtime records count)
