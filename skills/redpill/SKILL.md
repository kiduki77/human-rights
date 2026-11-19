---
description: "Turn red pill review drills on or off, set how often they fire, or show their results."
argument-hint: "on [N] [design|final|design,final] [en|ko] | off | status"
disable-model-invocation: true
---

Follow the human-rights workflow skill at `${CLAUDE_PLUGIN_ROOT}/skills/human-rights/SKILL.md` (read it first if it is not loaded in this conversation).

The human typed this command themselves. Map `$ARGUMENTS` to `hr redpill` and pass their message as the quote:

- `on [N] [gates] [language]` -> `.human-rights/hr redpill on [--one-in N] [--gates G] [--language L] --quote "<the command line they typed>"` (defaults: keep current settings)
- `off` -> `.human-rights/hr redpill off --quote "<the command line they typed>"`
- `status` or empty -> `.human-rights/hr redpill status`

Show the settings line `hr` prints. Never say whether a drill is active, and never read `.internal/redpill.json`.
