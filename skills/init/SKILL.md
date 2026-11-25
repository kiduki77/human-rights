---
description: "Set up hrs (human-rights) in this repository: create .human-rights/, choose the report language, the sub-agent models, and the red pill review drills."
argument-hint: "[en|ko] [balanced|quality|economy|inherit] [redpill off|easy|normal|hard|adaptive [N]]"
disable-model-invocation: true
---

Follow the human-rights workflow skill at `${CLAUDE_PLUGIN_ROOT}/skills/human-rights/SKILL.md` (read it first if it is not loaded in this conversation).

Set up this repository. Arguments given: `$ARGUMENTS`.

1. If this is not a git repository, say that only L0/L1 will be possible and offer `git init`. Don't run it without a yes.
2. Settle four choices. Take each one from the arguments when given. Otherwise ask them in one `AskUserQuestion` call, written in the user's language:
   - **Report language** for everything humans read under `.human-rights/`: `ko` or `en`. Recommend the language the user is writing in.
   - **Sub-agent models**: which model and effort the investigator, the plan reviewer, the code reviewer, the task worker, the tester, and the red pill author run with. The main conversation stays on the session model. Show each option with its values:
     - `balanced` (recommended): investigator sonnet/medium, plan reviewer and code reviewer opus/high, the other three sonnet/high
     - `quality`: opus for all six (investigator medium, the others high)
     - `economy`: investigator haiku, plan reviewer and code reviewer sonnet/high, the other three sonnet/medium
     - `inherit`: all six use the session model and effort
   - **Red pill drills**: explain in one sentence that an approval request sometimes contains one planted item that must not be approved, written for the feature at hand, so the human practises finding flaws. Options:
     - `Off`
     - `Adaptive` (recommended): starts easy, moves up after 2 clean catches in a row, down after 2 misses in a row
     - `Normal`: the flaw sounds routine and has to be thought through
     - `Hard`: a real row is altered, and it is only wrong against the requirements or decisions

     `Easy` (the flaw is stated outright in the row) is available through the free-text answer.
   - **How often** (skip when drills are off): about 1 in 3, 1 in 5 (recommended), 1 in 10 approval requests, or every time.

   If `.human-rights/config.yaml` already exists, show the current values from `hr agents`, `hr redpill status` and the current `docs.language`, and change only what the human picks.
3. Run `python3 "${CLAUDE_PLUGIN_ROOT}/runtime/hr.py" init --language <lang> --agents <preset> --redpill <on|off> [--redpill-difficulty <level> --redpill-one-in <N>]` (use `python` if `python3` is missing). Running it again is safe: existing files are kept, and an old `.workflow/` is moved. The human chose the drill settings in this conversation, so `init` may set them; later changes go through `/hrs:redpill`, and turning drills off there needs a reason, which `hr` records. Do not use `init --redpill off` to turn drills off in a workspace that already has them on: `hr` logs that change as made without a human decision.
4. Report in a few lines, in the chosen language: what was created, the report language, the sub-agent table and the red pill line `hr init` printed, and how to start (`/hrs:new <request>`, or just describe the change in chat). Mention that `.human-rights/` is meant to be committed except what its own `.gitignore` excludes, and that `config.yaml` can be edited by hand later. Don't commit anything yourself.
