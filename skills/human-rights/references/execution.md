# Implementing tasks and per-task verification

Precondition: `hr transition executing` succeeded. Any required design approval is valid, no open
questions remain, and plan-check passes.

## GitHub (depending on configuration)

For L2/L3, when the mode is in `github.issue_modes` in `config.yaml` and `hr gh status` reports
available, run `hr gh create-issues`. Showing a `--dry-run` first is fine. If GitHub is unavailable, write
"Issue creation: manual action needed (<reason>)" in the report. Never pretend it succeeded.

## Task loop (DAG order, sequential by default)

Follow the task table order (topological) in `hr status` / `overview.md`. Start a task only when all its
dependencies are `verified`.

1. Branching: one feature branch (`hr/<FEAT-id>`), or a branch or worktree per task. Sequential branches
   are enough at first.
2. `hr task TASK-001 in_progress`
3. Implement within the approved `scope.paths` / `modules`. If you need a change outside the boundary,
   **stop**: run `hr scope-change --task TASK-001 --reason "<what and why>"`, explain it to the user, and
   reclassify or re-plan. The same rule applies to small mechanical fixes in another task's scope.
4. Leave each task as one verifiable commit, with `FEAT-id TASK-id` in the message. `.human-rights/` document
   changes can go in the same commit or a separate one; the runtime looks only at the code tree.
5. `hr task TASK-001 implemented`, then `hr verify --task TASK-001`.
   - With uncommitted code changes, results don't count as L2/L3 evidence. Commit and re-run.
   - On failure, fix based on the printed output tail and the log path. When the same test fails as many
     times in a row as the limit allows (default 3), the runtime escalates to a human. Stop there.
6. When it passes: `hr task TASK-001 verified`. The runtime binds the run ids, commit SHA, and code tree.
7. Links: `hr gh link --task TASK-001 --commit <sha>`. If you opened a draft PR, add `--pr N`.
8. Fill in "Result" in `tasks/TASK-001.md` in 2-3 lines.

When a `human_review: required` task finishes, show the human a short summary: what changed and why, the
risk, and evidence links. Don't make them read all the code. If they find a problem, move the task to
`rework_required`.

When every task is done: `hr transition verifying_tasks`, then `completed` (L0/L1) or `integrating`
(L2/L3). `verifying_tasks → integrating` opens only when every task is `verified`.

`hr schedule` shows which task is next in DAG order even when you work sequentially.

## Parallelism

When the user wants speed and the DAG has independent tasks, use [parallel.md](parallel.md) instead
of this loop. `hr schedule --start` creates one worktree per conflict-free task, `hr-task-worker`
sub-agents implement them concurrently, and `hr worktree merge` brings them back in dependency order.
Integration is always re-verified on the exact merged code version.
