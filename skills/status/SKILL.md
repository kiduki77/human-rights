---
description: "Show the active human-rights feature's state, with the next human decision first."
argument-hint: "[FEAT-id]"
disable-model-invocation: true
---

Follow the human-rights workflow skill at `${CLAUDE_PLUGIN_ROOT}/skills/human-rights/SKILL.md` (read it first if it is not loaded in this conversation).

Run `hr status` (with `-f $ARGUMENTS` if an ID was given). Lead with the next human decision, then state, approvals, tasks, tests and open flags. If no feature is active, say so and ask what to build.
