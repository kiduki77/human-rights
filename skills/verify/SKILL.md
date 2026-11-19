---
description: "Run a human-rights feature's full approved test plan and report evidence."
argument-hint: "[FEAT-id]"
disable-model-invocation: true
---

Follow the human-rights workflow skill at `${CLAUDE_PLUGIN_ROOT}/skills/human-rights/SKILL.md` (read it first if it is not loaded in this conversation).

Run `hr verify` for `$ARGUMENTS` (the active feature if empty). Report results and failure records exactly as `hr` prints them; say plainly what was not run.
