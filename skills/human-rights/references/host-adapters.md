# Host adapters

The skill text, templates, schemas, and runtime are host-independent. Only command registration,
sub-agents, and how human decisions reach the runtime differ by host.

## Claude Code (primary)

- Invoked through the per-action commands (`/hrs:new <request>`, `/hrs:resume`, `:status`, `:review`,
  `:approve`, `:redpill`, ...), or automatically when the user asks for a human-gated change in plain chat.
- Human decisions happen in chat. The `UserPromptSubmit` hook `hooks/prompt_capture.py` stores each
  message the human types. The agent records a decision with `hr ... --quote "<their words>"`, and the runtime
  checks the quote against that stored message. The plugin hook `hooks/approval_guard.py` denies those
  commands when they have no `--quote`, and blocks direct writes to the prompt log and to runtime-owned files.
- The human can still run any decision directly with the `!` prefix (`! .human-rights/hr approve design --by alice`).
- Questions: use `AskUserQuestion` when it fits (3-5 questions, each with a recommended option first).
- Sub-agents: `hr-investigator` (read-only) and `hr-plan-reviewer` (independent review) through the Agent tool.
  Give each a self-contained brief: the goal, the feature directory path, and what is already ruled out.
- Parallel batches: spawn one `hr-task-worker` per task **in a single message** (so they run concurrently),
  each with the `prompt` from `hr schedule --start --json` verbatim. Workers write only inside their
  worktree and never run `hr`. The coordinator verifies, records, and merges.
- A `SessionStart` hook reminds a new session about the active feature.

## Codex / Cursor / other hosts

- Point the host at `skills/human-rights/SKILL.md` as its instructions (or as a custom prompt/rule).
- If the host has no prompt hook, `--quote` has nothing to check against and is refused. The human runs
  decisions directly (`.human-rights/hr approve design --by <name>`) in their own terminal.
- If the host has no tool hooks, nothing technically blocks the agent from running those commands.
  Enforce merges with GitHub branch protection (required reviews, required checks), and treat
  `.human-rights` approvals as records that get cross-checked against GitHub's approval history.
- Parallel batches work on any host that can run shell commands. The briefs are plain text, so a host
  with its own background agents can take them as is. Without sub-agents, work through the briefs one at
  a time; the worktrees, merge order, and integration rules stay the same.
- Without sub-agents, do the investigation and review steps sequentially in the same agent. For the
  review, re-read the plan files from disk and judge them against the quality-gate table, not against
  your memory of writing them.
- If the host can't run shell commands, the workflow can't run. The runtime is required for gates.
