# Integration testing and the failure recovery loop

## Running it

1. Make sure all code is committed (the code line in `hr status` says clean).
2. `hr verify --level all` runs every approved required test (task and integration) on **the same commit**.
   Tests marked `parallel_safe` run concurrently (up to `verification.max_parallel_tests`, or `--parallel N`).
   Tests sharing a resource, and exclusive tests, run alone. If the code changes mid-run, the result is `error`.
   Results recorded in task worktrees are for other code versions and never count here.
3. Agent tests (`[AGENT]` in the output): for each, `hr test-brief TEST-020 --json`, spawn `hr-tester` with
   the `prompt` verbatim and the `agent` fields as the Agent tool's `model` and `effort`, then
   `hr record-agent TEST-020`. The runtime rejects a report that lacks a result or an evidence file for any
   step. Never perform an agent test yourself in the conversation that wrote the code, and never edit the
   report. Without sub-agents, run the steps yourself in a fresh pass, with the same evidence rules.
   Read the tester's `findings`: a real defect outside the steps becomes a fix or a disclosed risk.
4. Human tests (`[HUMAN]`) come last, only when every script and agent test passes on the current code;
   the runtime refuses an earlier pass. Show the steps and their pass criteria from `verification.md`, and
   ask the human to report the result in chat. Record their reply:
   `hr record-manual TEST-013 passed --quote "<their words>" [--evidence <link>]`
5. `hr render` refreshes the result tables in `verification.md` and `overview.md`.

## Handling failures

The runtime creates a `FAIL-NNN` record for each failure, holding the test, requirements, suspect tasks,
observed and expected results, evidence, and retry count. You investigate the root cause and classify it:

```bash
.human-rights/hr failures --classify FAIL-002 --cause-type interface \
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
- **Before completion, every required test must be valid for the final commit.** After a code change the
  runtime keeps a passing result only if the test declares `covers` and no changed file falls under it;
  everything else becomes `stale` and has to run again. `hr status` shows what is stale. Don't re-run what
  the runtime still shows as passing, and never edit `covers` to avoid a re-run: that is a plan change.
- When the same failure hits the consecutive limit (default 3), the feature becomes `blocked` (escalation).
  Give the human the evidence and the options (keep trying / redesign / cut scope / abort) and wait. Only a
  human can release it. When they decide in chat, record it: `hr unblock --quote "<their words>" --note "<decision>"`.
- If new defects keep appearing, the design scope widens, or the approval criteria would have to change,
  stop auto-fixing and re-plan.

## Definition of Done

- [ ] Every must requirement maps to a verification item (`plan-check` coverage)
- [ ] Every required task passed its own verification (`verified` + evidence)
- [ ] Integration, regression, and required safety tests pass **for the current commit** (run on it, or
      carried over because nothing they cover changed)
- [ ] Every agent test has per-step evidence, and every human test was recorded after the machine tests
- [ ] The last verification and the approved code version match (the runtime compares code tree fingerprints)
- [ ] No unresolved critical defects; remaining issues are disclosed with agreed handling (`--risks`)
- [ ] Required human approvals are done and GitHub protection rules are satisfied (`hr merge-check`)
- [ ] The human-facing final report (`overview.md`) exists and `hr doc-check` passes

When all hold: `hr transition awaiting_final_approval` (with a final gate) or `ready_to_merge`.
