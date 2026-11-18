# Parallel execution: DAG scheduling, worktrees, sub-agents

Parallelism is an optimization, never a default. Go parallel only when the user wants speed and the
plan has independent tasks. Sequential execution ([execution.md](execution.md)) is always correct;
parallel execution is correct only when the runtime says the tasks can't collide.

## What may run together

`hr schedule` picks the next batch from the task DAG. A task joins a batch only if:

- all its `depends_on` tasks are `verified` **and merged** into the integration branch;
- it has no dependency relation with any other task in the batch or already running;
- no `scope.paths` overlap with them (directories cover their files; a glob covers its prefix);
- no contract conflict: it doesn't provide what another consumes, and doesn't provide the same contract
  as another;
- no shared `resources` (a DB, a port, a device, a SITL rig);
- it declares `scope.paths` at all. An unknown footprint never runs in parallel. Neither does
  `parallel_safe: false`;
- the batch is under `scheduler.max_parallel_tasks` (config, default 3).

Every deferred task is printed with its reason. If a task you expected to run in parallel is deferred,
the plan is telling you something: either accept the serialization or fix the plan (and re-approve).
Never hand-start worktrees to get around it.

To make tasks parallelizable, declare their footprint precisely in `task-graph.json` at planning time:
exact `scope.paths`, the `contracts` they provide and consume, and the `resources` they need.

## The loop

1. `hr schedule`: preview the next batch (deferred and waiting tasks are listed with reasons).
2. `hr schedule --start` creates one worktree per task. Each is on branch `hr/<FEAT>/<TASK>`, starts from
   the integration branch HEAD, and lives in a sibling `<repo>.hr-worktrees/` directory. The tasks become
   `in_progress`, and a brief is printed for each. The main checkout must have no uncommitted code changes.
3. Spawn one `hr-task-worker` sub-agent per task **in the same message** so they run concurrently. Pass
   each its brief verbatim (`hr worktree brief <TASK> --json` gives the `prompt` field again). Without
   sub-agents, work through the briefs yourself one at a time, still inside each worktree.
4. As workers report back, for each task:
   - review the report. If it asks for a scope change, run `hr scope-change` and re-plan; don't merge;
   - `hr task <TASK> implemented`;
   - verify. One at a time: `hr verify --task <TASK>`, which runs in that task's worktree automatically.
     Or several at once: `hr verify --tasks TASK-002 TASK-003`;
   - `hr task <TASK> verified`. The evidence is bound to the worktree's code version.
5. Merge in dependency order: `hr worktree merge <TASK> --remove`. The runtime refuses when:
   - the task is not verified, or changed after it was verified;
   - the worktree has uncommitted changes;
   - a dependency is not merged yet (dependent work is never merged in parallel);
   - the main checkout is not on the integration branch, or has uncommitted code changes.

   On a conflict, the merge is aborted, the integration branch is unchanged, and the task becomes
   `rework_required`. Fix it in its worktree (rebase onto the integration branch, re-verify, merge again).
   A conflict between "independent" tasks means their declared boundaries were wrong, so tell the user
   and fix the plan.
6. Repeat `hr schedule --start` until every task is verified and merged. `verifying_tasks → integrating`
   is refused while any worktree is unmerged.

## Integration on the exact integrated code

After merging, the integration branch holds a code version no single task was tested on. The runtime
treats every worktree result as `stale` for it. In `integrating`, run the full required test plan on the
merged commit:

```bash
.workflow/hr verify --level all          # parallel-safe tests run concurrently, the rest alone
```

Tests run concurrently only if they opt in with `parallel_safe: true`. Tests that share a `resources`
entry never run together, and `exclusive: true` tests always run alone. The concurrency limit is
`verification.max_parallel_tests`, or `--parallel N`. If the code under test changes while a test runs,
its result is recorded as `error`, never as a pass. Final approval binds to this merged code.

## Housekeeping

- `hr worktree list`: every worktree and its status (active / merged / removed / discarded).
- `hr worktree remove <TASK> --force`: discard an unmerged worktree (the branch is kept; the task goes
  back to `rework_required`).
- `hr resume` reports missing worktrees, uncommitted changes in them, and code changed after verification.
- `hr metrics` shows each parallel batch's serial time vs. wall time (the speedup you actually got).
