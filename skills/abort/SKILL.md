---
description: "Abort a human-rights feature after confirmation; records and branch are kept."
argument-hint: "[FEAT-id] [reason]"
disable-model-invocation: true
---

Follow the human-rights workflow skill at `${CLAUDE_PLUGIN_ROOT}/skills/human-rights/SKILL.md` (read it first if it is not loaded in this conversation).

Confirm with the human first, then run `hr abort -f <id> --reason "..."` for `$ARGUMENTS`. Records and the branch are kept.
