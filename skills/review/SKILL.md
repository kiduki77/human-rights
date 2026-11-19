---
description: "Show a human-rights feature's overview and the decision it needs."
argument-hint: "[FEAT-id]"
disable-model-invocation: true
---

Follow the human-rights workflow skill at `${CLAUDE_PLUGIN_ROOT}/skills/human-rights/SKILL.md` (read it first if it is not loaded in this conversation).

Run `hr render` for `$ARGUMENTS` (the active feature if empty), then show `overview.md` and the next decision. Link to details instead of pasting them. At an approval gate, paste the rendered tables verbatim.
