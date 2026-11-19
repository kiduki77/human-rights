---
description: "Set up hrs (human-rights) in this repository: create .human-rights/, choose the report language and the sub-agent models, and show the red pill settings."
argument-hint: "[en|ko] [balanced|quality|economy|inherit]"
disable-model-invocation: true
---

Follow the human-rights workflow skill at `${CLAUDE_PLUGIN_ROOT}/skills/human-rights/SKILL.md` (read it first if it is not loaded in this conversation).

Set up this repository. Arguments given: `$ARGUMENTS`.

1. If this is not a git repository, say that only L0/L1 will be possible and offer `git init`. Don't run it without a yes.
2. Settle two choices. Take each one from the arguments when given. Otherwise ask both in one `AskUserQuestion` call, written in the user's language:
   - **Report language** for everything humans read under `.human-rights/`: `ko` or `en`. Recommend the language the user is writing in.
   - **Sub-agent models**: which model and effort the investigator, the plan reviewer, the task worker, and the tester run with. The main conversation stays on the session model. Show each option with its values:
     - `balanced` (recommended): investigator sonnet/medium, plan reviewer opus/high, task worker sonnet/high, tester sonnet/high
     - `quality`: opus for all four (investigator medium, the others high)
     - `economy`: investigator haiku, plan reviewer sonnet/high, task worker sonnet/medium, tester sonnet/medium
     - `inherit`: all four use the session model and effort

   If `.human-rights/config.yaml` already exists, show the current values from `hr agents` and the current `docs.language`, and change only what the human picks.
3. Run `python3 "${CLAUDE_PLUGIN_ROOT}/runtime/hr.py" init --language <lang> --agents <preset>` (use `python` if `python3` is missing). Running it again is safe: existing files are kept, and an old `.workflow/` is moved.
4. Run `.human-rights/hr redpill status`.
5. Report in a few lines, in the chosen language: what was created, the report language, the sub-agent table `hr init` printed, red pill on or off, and how to start (`/hrs:new <request>`, or just describe the change in chat). Mention that `.human-rights/` is meant to be committed except what its own `.gitignore` excludes, and that the `agents:` section of `config.yaml` can be edited by hand later. Don't commit anything yourself.
