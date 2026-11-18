# Integration testing and the failure recovery loop

## Running it

1. Make sure all code is committed (the code line in `hr status` says clean).
2. `hr verify --level all` runs every approved required test (task and integration) on **the same commit**.
   Tests marked `parallel_safe` run concurrently (up to `verification.max_parallel_tests`, or `--parallel N`).
   Tests sharing a resource, and exclusive tests, run alone. If the code changes mid-run, the result is `error`.
   Results recorded in task worktrees are for other code versions and never count here.
3. For human-only tests (`command: null`), show the procedure and pass criteria, and have a human record
   the result: `! .workflow/hr record-manual TEST-013 passed --by <name> --evidence <link>`
4. `hr render` refreshes the result tables in `verification.md` and `overview.md`.

## Handling failures

The runtime creates a `FAIL-NNN` record for each failure, holding the test, requirements, suspect tasks,
observed and expected results, evidence, and retry count. You investigate the root cause and classify it:

```bash
.workflow/hr failures --classify FAIL-002 --cause-type interface \
  --cause "reconnect replaces the session object, so the router keeps a stale reference" \
  --suspect TASK-003 --fix-task TASK-003 --retest TEST-011,TEST-010
```

| `cause-type` | Meaning | Next |
|---|---|---|
| `implementation` | defect in one task | `rework_required`, then `executing`; fix that task |
| `interface` | interface/integration defect | fix the related tasks and contracts. If the plan files change, design approval is invalidated: re-approve |
| `design` | requirements/design defect | `clarifying`: ask, redesign, re-approve |
| `test_env` | test or environment defect | repair the test or environment and record evidence, kept separate from product defects. Changing a test definition needs re-approval |

- Right after a fix, run the affected tests (`--retest`) first.
- **Before completion, re-run every required test on the new commit.** The runtime treats results from
  before a code change as `stale`, so a partial re-run never opens the next step.
- When the same failure hits the consecutive limit (default 3), the feature becomes `blocked` (escalation).
  Give the human the evidence and the options (keep trying / redesign / cut scope / abort) and wait. Only a
  human can release it: `! .workflow/hr unblock --by <name> --note "<decision>"`.
- If new defects keep appearing, the design scope widens, or the approval criteria would have to change,
  stop auto-fixing and re-plan.

## Definition of Done

- [ ] Every must requirement maps to a verification item (`plan-check` coverage)
- [ ] Every required task passed its own verification (`verified` + evidence)
- [ ] Integration, regression, and required safety tests pass **on the current commit**
- [ ] The last verification and the approved code version match (the runtime compares code tree fingerprints)
- [ ] No unresolved critical defects; remaining issues are disclosed with agreed handling (`--risks`)
- [ ] Required human approvals are done and GitHub protection rules are satisfied (`hr merge-check`)
- [ ] The human-facing final report (`overview.md`) exists and `hr doc-check` passes

When all hold: `hr transition awaiting_final_approval` (with a final gate) or `ready_to_merge`.
