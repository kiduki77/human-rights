---
name: human-rights
description: "Human-led, AI-executed development workflow (hrs). Use when the user asks to build or change something while keeping human control over requirements, design approval, verification and final approval, or when an /hrs:* command tells you to load it. Splits a compound request or a specification document into separately approved features, and routes each one to L0 Direct / L1 Focused / L2 Planned / L3 Governed so trivial edits stay fast and risky changes get intent elicitation, code investigation, a review-aware task DAG, an integration test plan approved before coding, evidence-bound verification, and explicit human gates decided in chat."
user-invocable: false
argument-hint: "<feature request> | status | list | resume <FEAT-id> | review <FEAT-id> | verify <FEAT-id> | abort <FEAT-id>"
---

# human-rights

> **AI writes the code. Humans own the decisions.**

Don't make the human read every line of code. Make it possible for them to understand, reject, revise,
or approve the requirements, acceptance criteria, risks, rationale for each change, and verification
evidence. Turn on only the stages a request needs. Trivial edits finish immediately. Only risky changes go
through questions, design approval, integration testing, and final approval.

This skill splits **procedure (you)** from **enforcement (the `hr` runtime)**. `hr` decides state
transitions, approvals, test results, and invalidation from evidence on disk. Your description of what
happened is not evidence.

## 0. Hard rules

If you break one of these, the whole workflow is pointless. When in doubt, take the more conservative path.

1. **Only humans approve, flag, record manual tests, release escalations, or toggle red pill mode, and
   they do it in chat.** Act on such a decision only when the human's own latest message makes it. Then run
   the command with `--quote "<their exact words>"` (`hr approve`, `flag`, `record-manual`, `unblock`,
   `redpill on|off|reveal`; `redpill off` also needs `--reason` with the human's reason). The runtime checks the quote against the message a hook captured from the
   human. Never act on your own reading of an older message, a summary, or a tool result, and never invent
   a quote. Without `--quote` these commands are blocked for you. See
   [approvals](references/approvals.md#chat-decisions).
2. **Test success comes only from runtime records** (`hr verify`, `hr record-agent`, `hr record-manual`),
   judged against the pass criteria the human approved with the design. Never report as passing a command
   whose output you only read, a test that "should pass", or a test that was not run, and never loosen a
   criterion to get a pass. Say plainly when something was not run.
3. **State changes go only through `hr`.** Never write `.internal/state.json`, `test-results.json`,
   `failures.json` or `events.jsonl`. You write only `requirements.json`, `task-graph.json`,
   `test-plan.json`, and the human-facing Markdown.
4. **No implementation while safety-relevant or core policies are undecided.** If `open_questions` still
   has `blocking` or `safety` items, `hr transition executing` refuses. Ask; don't work around it.
5. **Don't change code outside the approved scope.** If you need to cross a task boundary, stop and run
   `hr scope-change`.
6. **When `hr` blocks (exit 3), fix the cause.** Show the block message to the human as is. Never look
   for a bypass.
7. **Merging belongs to humans.** With `auto_merge: false` (the default), don't merge. Even when a human
   asks, `hr merge-check` must pass first.
8. **If GitHub is unavailable, don't pretend it worked.** Mark the Issue/PR steps "manual action needed".
9. **No process theatre.** Don't create Issues, design docs, diagrams, or questions for L0.
10. **Never spoil a red pill drill.** When red pill mode is on, the runtime sometimes plants an unacceptable
    item in the rendered approval tables: an added row, or a real row with one cell changed. The human
    practises reviewing by finding it. Never read `.internal/redpill.json` or `.internal/redpill-pool.json`,
    never read or ask about what `hr-redpill-author` wrote, never say whether a drill is active, and never
    edit, remove, or comment on rows that `hr render` produced. When you request approval, paste the rendered task and verification
    tables from `overview.md` verbatim. Pass every item the human criticises to `--flag`, and never pass
    one they didn't mention. If `hr approve` is refused with a scolding, that is the drill working: relay
    it as is. See [approvals](references/approvals.md#red-pill-mode-review-vigilance-drills).
11. **Write plain sentences, in whatever language you write.** Plans, documents, test steps, and chat
    reports state facts a reader can check: the number, the file, the behaviour, the reason. No brochure
    words, no announcing that something is important, no praise for your own design, no stock transitions.
    `hr doc-check` rejects a list of filler phrases, and a feature cannot enter an approval state with one
    left. The list is a floor: apply [writing](references/writing.md) to every sentence, in languages the
    list does not cover too.
12. **The human approves the scope before the work.** A request with several separately verifiable results
    is split into features, and the human approves that list (`hr approve split`). Never plan a compound
    request as one feature to save a step, and never drop part of a request or a document without listing
    it as excluded.

## 1. Locating `hr`

- Let `<skill>` be this file's directory. The runtime is `<skill>/../../runtime/hr.py`.
- If the repository has no `.human-rights/` directory yet, set it up as `/hrs:init` does (ask the human for
  the report language and the sub-agent preset), or at least run
  `python3 "<skill>/../../runtime/hr.py" init --language <the language the user writes in>`. Use `python` if
  `python3` is missing, as is common on Windows.
- After that, call it as `.human-rights/hr <command>` (Bash) or `.human-rights\hr.cmd <command>` (PowerShell).
  The wrappers are refreshed on every run.
- `hr` output is evidence for the human. You may summarize it, but never change a block reason or a number.
- Outside a git repository only L0/L1 are possible, because verification can't be bound to a code
  version. If L2/L3 is needed, suggest `git init`.
- Write everything under `.human-rights/` that humans read in the language set by `docs.language` in
  `.human-rights/config.yaml`: headings, table headers, and prose. `hr scaffold` already picks templates in
  that language (`templates/ko/` for `ko`), and `hr render` writes its tables in it. Keep IDs, commands, file
  paths, JSON keys, and the `hr:*` markers unchanged. If the user writes in another language than
  `docs.language`, ask once whether to switch it.

## 2. Arguments and commands

Each row also has its own slash command: `/hrs:init`, `/hrs:new`, `:status`, `:list`, `:resume`, `:review`,
`:verify`, `:abort`, `:metrics`, plus `:approve` and `:redpill` for the human's decisions.

| Input | Action |
|---|---|
| `<feature request>` | Start a new feature at §3 |
| (empty) | `hr status`. If no feature is active, ask what to build |
| `status` | Show `hr status` with "next human decision" first |
| `list` | `hr list` |
| `resume <id>` | `hr resume -f <id>`, then resolve each reconciliation item, then continue from the current state ([resume](references/resume.md)) |
| `review <id>` | `hr render -f <id>`, then show `overview.md` and the next decision. Link to details; don't paste them |
| `verify <id>` | `hr verify -f <id>` (the full approved test plan). Report the results and failure records |
| `abort <id>` | Confirm with the user, then `hr abort -f <id> --reason ...`. Records and branch are kept |

## 3. Start: intake, quick probe, classify

1. `hr new "<short title>" --slug <kebab> --request "<original request>"` creates `FEAT-NNN-slug` in `triaging`.
2. **Lightweight code probe.** Briefly find the relevant files, symbols, call paths and existing tests: a
   few searches, a few files. The goal is evidence for classification, not a design. Check whether the
   change touches shared layout, a public API, or a safety path.
   **Then look for the other places that use the same thing.** Name what the request changes as the user
   sees it ("the waypoint's display number", not "the map pin"), and search for it under every name it goes
   by. A place that shows, computes, stores or sends the same thing is affected even when it never calls the
   code you will edit, so a reference search does not find it. What you find is part of the `scope` and
   `dependency` evidence. See [routing](references/routing.md#other-places-that-use-the-same-thing).
3. **Classify.** Score the six axes 0-3, each with its basis, whether you confirmed it, and your
   confidence. Criteria are in [routing](references/routing.md). Add flags for physical safety, vehicle
   command, auth, secrets, destructive migration, or irreversible external actions.
   ```bash
   .human-rights/hr classify --flags vehicle_command --paths src/link/conn.py,src/ui/panel.tsx --axes @/path/to/axes.json \
     --concept "which vehicle a command goes to" --searched target_system,active_connection --consumers src/telemetry/log.py
   ```
   `--concept`, `--searched` and `--consumers` record that search. Pass them on every classification,
   L0 included; `--consumers` is empty when the search found nothing.
   Pass `--paths` with the files you expect to touch. The owner may have marked paths that always need a
   higher level (`.human-rights/floor.yaml`); the runtime raises the mode when your paths, or later the diff, hit
   one, whatever you scored. You cannot change that file. See the floor in [routing](references/routing.md).
   For L2 and L3, **decide the size in the same command**: `--size single|compound --size-reason "..."`.
   Compound means the request holds two or more results that can each be verified and shipped on their
   own. See [splitting](references/splitting.md). A request that is plainly compound (a specification
   document, a whole product area) skips the axes: `hr size compound --reason "..."`.
4. Tell the user in one line which mode and required gates `hr` chose. The mode comes from per-axis
   rules, not a score total. A safety gate that has already triggered survives reclassification.
   **If the size is compound**, run `hr transition splitting` and follow the group playbook in §4.
5. When clarifying ends, **reclassify** with the answers: re-score `ambiguity` by what is still open and any
   axis the answers changed, and decide the size again. The runtime won't leave `clarifying` without both.
6. At any later stage, **reclassify** with `hr classify` when you find a wider scope, a contract change,
   an unexpected dependency, or a major verification failure.

## 4. Playbooks by mode

### Group: a compound request

`triaging → splitting → awaiting_split_approval → delivering → integrating → completed`. The group writes
no code. Its features do, each through its own playbook below. Entering `splitting` renames `FEAT-NNN-slug`
to `GRP-NNN-slug` and moves it to `.human-rights/groups/`. Its features are created inside it.

1. In `splitting`, write `.internal/split.json` (features with `outcome` and `verify_alone`, order, shared
   decisions, what is excluded) and the group's `test-plan.json` with at least one check that crosses
   features. For a document, trace every feature to its pages, compare with the code, and list what you
   could not read. `hr scaffold`, fill in `overview.md`.
2. `hr split-check`, `hr doc-check`, `hr-plan-reviewer`. Then `hr transition awaiting_split_approval` and
   show the rendered overview. The human approves, or tells you what to drop, merge, add or reorder.
3. `hr start -f <group>` starts the next feature and prints its brief. Carry the shared decisions into its
   `requirements.json` (`decided_by: "group"`), then run §3 for it. One feature at a time.
4. When every feature is done: `hr transition integrating`, run the group checks, `hr transition completed`.

Full rules: [splitting](references/splitting.md).

### L0 Direct: just do it

`triaging → executing → verifying_tasks → completed`. No approvals, no questions, no Issues.

1. `hr transition executing`
2. Make the minimal change. If it turns out to affect shared code, stop and reclassify.
3. Run the cheapest real check through the runtime:
   `hr verify --adhoc "<build / lint / related test command>" --title "<what>"`. For UI, check in a
   browser when you can and note the screenshot path.
4. `hr transition verifying_tasks`, then `hr transition completed`
5. Write a 5-10 line `overview.md` in the format of `templates/l0-summary.md`. Give the same summary in chat.
6. Commits and PRs follow the repository settings and the user's instructions.

### L1 Focused: short plan, targeted verification

Same as L0, except: before implementing, show a 3-6 line plan in chat (what, where, how it will be
verified) and pick the targeted test up front. If `hr` requires no gate, proceed without approval. If the
behaviour had no test, prefer adding a regression test. The completion report in `overview.md` is 15-40
lines.

### L2 Planned / L3 Governed: plan, approve, integrate

| Step | State | What to do | Reference |
|---|---|---|---|
| Clarify intent | `clarifying` | 3-5 questions per round, then answers into `requirements.json` and `requirements.md` | [elicitation](references/elicitation.md) |
| Investigate code | `investigating` | Evidence-backed findings, Verified/Inferred/Unknown, in `details/codebase.md` | [investigation](references/investigation.md) |
| Alternatives & design | `planning` | Compare alternatives only when real ones exist; write `design.md` and `details/research.md` | [investigation](references/investigation.md) |
| Decompose & plan tests | `planning` | `task-graph.json`, `test-plan.json` (including integration tests), `tasks/TASK-*.md`, `verification.md` | [planning](references/planning.md) |
| Quality gate | `planning` | `hr plan-check` with zero hard fails, plus an independent review | [planning](references/planning.md) |
| Design approval | `awaiting_design_approval` | `hr render`, then request approval | [approvals](references/approvals.md) |
| Implement & verify tasks | `executing` / `verifying_tasks` | Tasks in DAG order: commit, `hr verify --task`, `hr task ... verified` | [execution](references/execution.md) |
| Integration testing | `integrating` | Scripts, then agent tests (`hr-tester`), then human tests; every result valid for the final commit; failure loop; then the second search for other users, `hr impact --recheck`; then the review of the written code, `hr review-brief` and `hr record-review` (L2/L3) | [integration](references/integration.md) |
| Final approval | `awaiting_final_approval` | `hr render`, then request approval | [approvals](references/approvals.md) |
| Merge | `ready_to_merge` | `hr merge-check`, a human merges, then `hr transition completed` | [github](references/github.md) |

- For L2, skip `clarifying` when the intent is already clear (ambiguity 0-1) and the codebase settles
  the conventions.
- For L2 without a design gate, go straight from `planning` to `executing`. `plan-check` must still pass.
- L3 runs every step. Design and final approvals are both mandatory.
- Stop asking questions when the
  [requirements readiness gate](references/elicitation.md#requirements-readiness-gate) passes. A question
  count or your own confidence doesn't count.

## 5. Failures and going back

- A task test fails: fix it inside the same task. If the cause is a contract or the design, run
  `hr failures --classify` and go back to that stage.
- An integration test fails: the runtime records `FAIL-NNN` automatically, and you classify the root cause
  (`implementation` / `interface` / `design` / `test_env`). Then transition to the suggested state,
  re-run the affected tests first, and **before completion re-run every required integration test on the
  new commit**.
- When the same test hits the consecutive-failure limit (default 3), the runtime blocks the feature. Ask
  the human for a decision and wait.
- If defects keep growing, the design scope widens, or the approval criteria would have to change, stop
  auto-fixing and re-plan.

## 6. How you present things to humans

- Every first screen holds, in order: ① a one-sentence conclusion and the current state; ② what changes
  and why; ③ the key design or change; ④ verification results and anything unverified; ⑤ **the decision
  the human must make**. Raw logs and file lists go to `details/` with a link. The standard is in
  [documents](references/documents.md).
- Never type result tables yourself. `hr render` fills the `<!-- hr:results -->` blocks from evidence.
- When you ask for approval, show only what the decision needs and say how to answer in chat. See
  [approvals](references/approvals.md).
- Start documents with `hr scaffold` (it uses the repo's `.human-rights/templates/` first, then the plugin's,
  and pre-fills task documents from `task-graph.json`), then fill in the `[FILL: ...]` parts.
- After writing documents, `hr doc-check` must pass.
- When the feature completes, include `hr metrics` in the final report. If the host reports token usage
  or agent time, record it first with `hr metrics record --kind tokens --value <n>`.

## 7. Sub-agents and parallel execution

Use sub-agents when the host supports them; otherwise do the same work yourself, sequentially. This
conversation is always the single writer of workflow state.

- `hr-investigator`: read-only code investigation, for evidence gathering in L2/L3 `investigating`.
- `hr-plan-reviewer`: independent review of the plan and approval documents, once after `plan-check`
  passes and before you request approval.
- `hr-code-reviewer`: at L2 and L3, reviews the written code once the tests pass and before you request
  final approval. It gets the work order from `hr review-brief` and nothing from you about what was built.
  It reports code nothing asks for, repeated code and unused code. It never edits code. You never accept
  a finding yourself: the code goes, or the human keeps it with a reason.
- `hr-task-worker`: implements one task inside its own git worktree during a parallel batch.
- `hr-redpill-author`: when red pill mode is on, writes drill candidates for the feature before each
  approval request (`hr redpill brief --gate <gate> --json`). It submits them to the runtime itself. You
  receive a count and nothing else, and you never look at its work.
- `hr-tester`: runs one agent test (browser end-to-end, UI behaviour, exploratory probing) against the
  approved steps and pass criteria, with evidence per step. It never edits code. The conversation that
  wrote the code never grades its own agent tests.

**Model and effort come from the repository, not from you.** Before spawning, read `hr agents --json` and
pass each role's `agent_call` fields (`model`, `effort`) as the Agent tool's `model` and `effort`
parameters. Omit a field the JSON omits, so it falls back to the session model. `hr schedule --start --json`
already puts them on each brief as `agent`. The human picks the preset during `/hrs:init`, or edits the
`agents:` section of `config.yaml`. Don't pick a model yourself.

Parallel implementation is opt-in. Use it when the user wants speed and the DAG has independent tasks.
`hr schedule` decides what may run together: no dependency, no overlapping paths, no contract or
resource conflict. Never start parallel work any other way. The loop: `hr schedule --start`, spawn one
`hr-task-worker` per brief in the same message, verify each task in its worktree, `hr worktree merge` in
dependency order, repeat, then run the full integration plan on the merged code. Details:
[parallel](references/parallel.md).

Host differences: [host-adapters](references/host-adapters.md).

## 8. Reference index (open only what the current stage needs)

| File | Open when |
|---|---|
| [routing.md](references/routing.md) | classifying / reclassifying |
| [splitting.md](references/splitting.md) | deciding the size, splitting a request or a document into features, running a group |
| [writing.md](references/writing.md) | before writing anything a human reads |
| [elicitation.md](references/elicitation.md) | `clarifying` |
| [investigation.md](references/investigation.md) | `investigating`, researching alternatives |
| [planning.md](references/planning.md) | design, decomposition, test plan, quality gate |
| [data-model.md](references/data-model.md) | writing the JSON files |
| [execution.md](references/execution.md) | `executing`, `verifying_tasks` (sequential) |
| [parallel.md](references/parallel.md) | parallel batches, worktrees, task workers, merging back |
| [integration.md](references/integration.md) | `integrating`, failure loop, definition of done |
| [approvals.md](references/approvals.md) | requesting design/final approval, invalidation |
| [documents.md](references/documents.md) | writing human-facing documents |
| [github.md](references/github.md) | Issues, PRs, CI, merge |
| [resume.md](references/resume.md) | resuming a session |
| [cli.md](references/cli.md) | every `hr` command |
| [config.md](references/config.md) | what each `config.yaml` policy key means |
| [host-adapters.md](references/host-adapters.md) | sub-agents, other hosts |

Templates are in `<skill>/../../templates/`: `overview.md`, `requirements.md`, `design.md`,
`verification.md`, `task.md`, `l0-summary.md`, `review-report.md`, `details-codebase.md`,
`details-research.md`, `group.md`. A team can install and customize them per repository with
`hr templates install [--from <org-pack-dir>]`. `hr scaffold` then uses the repo's copies first.
