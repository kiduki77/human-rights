---
description: "Approve the human-rights gate the active feature is waiting on (design or final), optionally with notes or accepted risks."
argument-hint: "[design|final] [notes or accepted risks]"
disable-model-invocation: true
---

Follow the human-rights workflow skill at `${CLAUDE_PLUGIN_ROOT}/skills/human-rights/SKILL.md` (read it first if it is not loaded in this conversation).

The human just typed this command themselves, so their message is the approval. Find the gate the feature waits on with `hr status`, then record it through the chat path in the approvals reference (`${CLAUDE_PLUGIN_ROOT}/skills/human-rights/references/approvals.md`, section "Chat decisions"), quoting their message exactly, for example:

```
.human-rights/hr approve <gate> --quote "<the command line they typed>" [--risks "<accepted risk>"]
```

Arguments they gave: `$ARGUMENTS`. If the feature is not at a gate, say so and do nothing. If `hr` refuses, relay the message as is.
