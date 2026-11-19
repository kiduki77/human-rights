---
description: "Resume a human-rights feature: reconcile stored state with git/GitHub, then continue from where it stopped."
argument-hint: "[FEAT-id]"
disable-model-invocation: true
---

Follow the human-rights workflow skill at `${CLAUDE_PLUGIN_ROOT}/skills/human-rights/SKILL.md` (read it first if it is not loaded in this conversation).

Resume `$ARGUMENTS` (the active feature if empty) following the resume reference (`${CLAUDE_PLUGIN_ROOT}/skills/human-rights/references/resume.md`): run `hr resume`, resolve every reconciliation item, then continue from the current state.
