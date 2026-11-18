# Resuming across sessions

`.workflow/` is the memory. Never trust what you remember from an earlier conversation. Reconcile the
stored state with the real files, git, and GitHub.

## Procedure

1. `hr resume -f <FEAT-id>` checks:
   - the integrity of the event log hash chain (edited or deleted records)
   - approvals still valid (the plan files and code are unchanged since approval)
   - HEAD or branch changes since the last recorded point, and uncommitted changes
   - tasks marked `verified` whose code changed afterwards
   - live state of recorded PRs and CI (if GitHub is available)
2. Resolve each reconciliation item before going on:
   - **An unrecorded commit**: find out what it changed. If it touched code, the evidence for the affected
     tasks is stale and must be re-verified.
   - **Approval invalidated**: tell the human what changed, then request re-approval.
   - **Event log problem**: report it to the human. Don't repair it yourself. Approval history must be
     cross-checked against the GitHub approval history.
   - **A PR was closed or merged outside the workflow**: GitHub is the truth. Explain the situation and
     agree with the human on the next state.
3. Read the documents for the current state (`overview.md`, and `requirements.md` / `design.md` as
   needed) and continue from the step for that state in SKILL.md §4.
4. Start your reply to the user with a short summary: where we are, what changed, what's next.
