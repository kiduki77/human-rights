# GitHub: Issues, PRs, CI, merging

GitHub is the source of truth for Issue, PR, and CI state. `.workflow` stores only ids, links, and the
last sync time. Never decide something is done from a local cache.

## Availability

`hr gh status` reports whether `gh` is installed and authenticated and the repo has a GitHub remote.
`config.yaml` `github.enabled`: `auto` (use it when available), `true` (required), or `false` (never).
If it is unavailable, mark the Issue/PR steps "manual action needed (<reason>)". Never report them as done.

## Issues (default: L2/L3 only, `github.issue_modes`)

- `hr gh create-issues [--dry-run]` creates one feature Issue from `overview.md` and one Issue per task
  from `tasks/TASK-NNN.md`, then records their numbers.
- When a design gate is required, the runtime refuses until the design approval is valid. Issues come
  only from an approved plan.
- To link existing Issues instead: `hr gh link --issue 42` (feature) or `hr gh link --task TASK-001 --issue 43`.

## Commits and PRs

- One verifiable commit per task, with `FEAT-id TASK-id` in the message.
- Open a draft PR with `gh pr create --draft ...`, then record it with `hr gh link --pr <n> [--task TASK-ID]`.
  Put the `overview.md` summary and the evidence table in the PR body.
- Never merge dependent PRs in parallel.
- Run final verification on **exactly the code that will be merged**. If you rebase or merge `main` in,
  the code tree changes, so the runtime invalidates the final approval and you re-verify.

## Live state

- `hr gh sync` fetches the live state, CI checks, and review decision of every recorded PR.
- `hr resume` also checks the PRs.

## Merging

1. `hr merge-check` needs: state `ready_to_merge`; a valid final approval if required (the code matches
   the approved code); each recorded PR open, not a draft, CI green, no conflicts; and the PR head equal
   to the local HEAD.
2. `auto_merge: false` (default): a human merges, or tells you to explicitly. Even then, merge only after
   `hr merge-check` passes.
3. After merging: `hr transition completed`.

Never change branch protection or repository rules. Never turn on auto-merge.
