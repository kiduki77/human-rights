# Host adapters

The skill text, templates, schemas, and runtime are host-independent. Only command registration,
sub-agents, and human-only command execution differ by host.

## Claude Code (primary)

- Invoked as `/human-rights ...` through the plugin's skill.
- The human runs human-only commands with the `!` prefix (`! .workflow/hr approve design --by alice`).
  Those don't go through tool hooks. When the agent tries the same command through its tools, the plugin
  hook `hooks/approval_guard.py` denies it. The same hook blocks direct writes to runtime-owned files.
- Questions: use `AskUserQuestion` when it fits (3-5 questions, each with a recommended option first).
- Sub-agents: `hr-investigator` (read-only) and `hr-plan-reviewer` (independent review) through the Agent tool.
  Give each a self-contained brief: the goal, the feature directory path, and what is already ruled out.
- Parallel batches: spawn one `hr-task-worker` per task **in a single message** (so they run concurrently),
  each with the `prompt` from `hr schedule --start --json` verbatim. Workers write only inside their
  worktree and never run `hr`. The coordinator verifies, records, and merges.
- A `SessionStart` hook reminds a new session about the active feature.

## Codex / Cursor / other hosts

- Point the host at `skills/human-rights/SKILL.md` as its instructions (or as a custom prompt/rule).
- If the host has no hooks, nothing technically blocks the agent from running human-only commands.
  Enforce merges with GitHub branch protection (required reviews, required checks), and treat
  `.workflow` approvals as records that get cross-checked against GitHub's approval history.
- Parallel batches work on any host that can run shell commands. The briefs are plain text, so a host
  with its own background agents can take them as is. Without sub-agents, work through the briefs one at
  a time; the worktrees, merge order, and integration rules stay the same.
- Without sub-agents, do the investigation and review steps sequentially in the same agent. For the
  review, re-read the plan files from disk and judge them against the quality-gate table, not against
  your memory of writing them.
- If the host can't run shell commands, the workflow can't run. The runtime is required for gates.
