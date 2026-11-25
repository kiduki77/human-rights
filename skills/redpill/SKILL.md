---
description: "Turn red pill review drills on or off, set their difficulty and how often they fire, or show your results."
argument-hint: "on [N] [easy|normal|hard|adaptive] [design|final|design,final] | off <reason> | status"
disable-model-invocation: true
---

Follow the human-rights workflow skill at `${CLAUDE_PLUGIN_ROOT}/skills/human-rights/SKILL.md` (read it first if it is not loaded in this conversation).

The human typed this command themselves. Map `$ARGUMENTS` to `hr redpill` and pass their message as the quote:

- `on [N] [difficulty] [gates]` -> `.human-rights/hr redpill on [--one-in N] [--difficulty D] [--gates G] --quote "<the command line they typed>"` (defaults: keep current settings)
- `off <reason>` -> `.human-rights/hr redpill off --reason "<the reason they typed>" --quote "<the command line they typed>"`. The reason is the human's. When they typed `off` alone, ask why they are turning drills off, wait for the answer, and pass their words. The command refuses without a reason.
- `status` or empty -> `.human-rights/hr redpill status`

Show what `hr` prints: the settings, the catch rate per difficulty, the kinds of flaw missed most often, the approvals and the rows named that were not the plant, and the periods drills were off with their reasons. Keep every number unchanged, and do not describe the rows named as mistakes: some are real concerns. Never say whether a drill is active, and never read `.internal/redpill.json` or `.internal/redpill-pool.json`.
