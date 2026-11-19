---
description: "Turn red pill review drills on or off, set their difficulty and how often they fire, or show your results."
argument-hint: "on [N] [easy|normal|hard|adaptive] [design|final|design,final] | off | status"
disable-model-invocation: true
---

Follow the human-rights workflow skill at `${CLAUDE_PLUGIN_ROOT}/skills/human-rights/SKILL.md` (read it first if it is not loaded in this conversation).

The human typed this command themselves. Map `$ARGUMENTS` to `hr redpill` and pass their message as the quote:

- `on [N] [difficulty] [gates]` -> `.human-rights/hr redpill on [--one-in N] [--difficulty D] [--gates G] --quote "<the command line they typed>"` (defaults: keep current settings)
- `off` -> `.human-rights/hr redpill off --quote "<the command line they typed>"`
- `status` or empty -> `.human-rights/hr redpill status`

Show what `hr` prints: the settings, the catch rate per difficulty, and the kinds of flaw missed most often. Never say whether a drill is active, and never read `.internal/redpill.json` or `.internal/redpill-pool.json`.
