# `hr` command reference

Call it as `.human-rights/hr <command>` (Bash) or `.human-rights\hr.cmd <command>` (PowerShell). Most commands
take `-f FEAT-NNN` (or `-f GRP-NNN` for a group) and default to the active feature.
Exit codes: `0` ok, `1` a test failed, `2` usage or data error, `3` blocked by a gate.

**Human decisions** are made in chat. The agent runs them with `--quote "<the human's exact words>"`, and the
runtime checks the quote against the human's latest captured message (see
[approvals](approvals.md#chat-decisions)). The human can also run them directly with `--by <name>`, in their own terminal. Without `--quote` the runtime
refuses a decision that does not run at a terminal (exit `3`).

| Command | Who | What it does |
|---|---|---|
| `init [--language en\|ko] [--agents preset] [--redpill on\|off --redpill-difficulty D --redpill-one-in N]` | human / agent (`/hrs:init`) | create `.human-rights/` (config, .gitignore, wrappers); safe to re-run; sets the report language, sub-agent models and drill settings the human chose. A drill setting it changes is logged as set through `hr init`, with no human decision behind it |
| `new "<title>" --slug s --request "<text>"` | agent | create a feature (`triaging`), make it active |
| `classify --axes <json\|@file\|-> [--flags a,b] [--paths p1,p2] [--concept "..." --searched a,b --consumers p1,p2] [--size single\|compound --size-reason "..."]` | agent | route / reclassify, set required gates, record the size decision (required for L2/L3). `--paths` lists the files you expect to touch; they and the real diff are checked against the owner's floor, which can raise the mode (omitted: the paths from the last classification are kept) |
| `floor` | anyone | list the owner's floor rules and, with an active feature, the touched paths each rule hits |
| `floor add <glob> <L0\|L1\|L2\|L3> --quote "<words>"` / `floor remove <glob> --quote "<words>"` | **human decision** | change `.human-rights/floor.yaml` and record it in `floor.seal`; prints what changed and who decided |
| `floor accept --quote "<words>"` | **human decision** | record `floor.yaml` as it is now, after the owner edited it by hand or when `[floor]` reports a change nobody recorded |
| `size single\|compound --reason "..."` | agent | record the size decision without scoring axes |
| `split-check [--json]` | agent | split quality hard gate for a group: features, order, shared decisions, exclusions, group checks |
| `start [-f group\|feature] [--json]` | agent | start the next waiting feature of a group (dependencies done, one at a time) and print its brief |
| `status [--json]` | anyone | state, approvals, tasks, tests, next human decision |
| `list` | anyone | all features, as a tree of groups and their features |
| `migrate [--dry-run]` | human / agent | move a workspace made by an older version to the current layout: a group becomes `groups/GRP-NNN-slug/` with its features inside |
| `resume` | agent | reconcile stored state with git/GitHub, make the feature active |
| `transition <state> [--reason]` | agent | guarded state change |
| `plan-check [--json]` | agent | plan quality hard gate |
| `task <TASK-ID> <status> [--note]` | agent | `in_progress` / `implemented` / `verified` (evidence needed) / `rework_required` / `blocked` / `cancelled` |
| `verify [--test ID...] [--task T] [--level task\|integration\|all] [--parallel N]` | agent | run planned tests, record evidence, auto-record failures. `--task` runs in that task's worktree if it has one |
| `verify --tasks T1 T2 ... [--parallel N]` | agent | several tasks' tests at once, each in its own worktree |
| `verify --adhoc "<cmd>" [--title]` | agent | L0/L1: add a test to the plan and run it |
| `schedule [--start] [--max N] [--json]` | agent | next conflict-free batch from the DAG, with reasons for deferred/waiting tasks. `--start` creates the worktrees and prints sub-agent briefs |
| `worktree create\|merge\|remove\|list\|brief [TASK] [--remove] [--force]` | agent | task worktrees; `merge` enforces verified-and-unchanged, dependency order, clean trees; aborts cleanly on conflict |
| `flag <ID>... --quote "<words>"` | **human decision** | point at approval items the human would not approve (catches a red pill plant, otherwise a review concern) |
| `redpill on [--one-in N] [--difficulty easy\|normal\|hard\|adaptive] [--gates ...] [--author agent\|builtin] [--max-flags N] [--language en|ko]\|ko] [--reason "<why>"]` / `redpill off --reason "<why>"` / `redpill reveal` (each `--quote "<words>"`) | **human decision** | Red pill mode toggle, difficulty, frequency, give up on a drill. `off` refuses without `--reason`. Every on, off and setting change is logged with who, when, and why |
| `redpill status` | anyone | Red pill settings, adaptive level, catch rate per difficulty, most-missed kinds, drills not counted for naming too many rows, approvals and rows named that were not the plant, time drills were off with reasons (never whether a drill is active) |
| `redpill brief --gate design\|final [--json]` | agent | prompt and model for `hr-redpill-author` |
| `redpill seed --gate design\|final --from <file\|->` | `hr-redpill-author` only | submit drill candidates for the current plan; the coordinating conversation never runs or reads this |
| `metrics [--all] [--json]` | anyone | lead time, approval wait, rework, failures, coverage, test time, tokens, parallel speedup, red pill results (`--all` adds the time drills were off) |
| `metrics record --kind <kind> --value N [--note] [--by]` | agent / human | host-reported values: `tokens`, `agent_seconds`, `review_minutes`, `escaped_defect`, `intent_mismatch`, `unnecessary_question`, `question_asked` |
| `templates install\|update\|status [--from DIR] [--force]` | human / agent | install the plugin's (or an org's) template pack into `.human-rights/templates/`; customized files are kept unless `--force` |
| `scaffold [overview requirements design verification codebase research tasks l0-summary review-report group] [--overwrite]` | agent | create feature docs from templates (repo first); `tasks` pre-fills from `task-graph.json`; a group gets `group` by default |
| `test-brief <TEST-ID> [--json]` | agent | work order for `hr-tester`: the approved steps and pass criteria, the evidence directory, the report shape, and the model to spawn with |
| `record-agent <TEST-ID> [--report path]` | agent | record an agent test from the tester's `report.json`; refuses a missing step result or a passed step without an evidence file |
| `review-brief [--json]` | agent | L2/L3: work order for `hr-code-reviewer` to review the written code: what to read, the diff, the three kinds of finding, the report shape, and the model to spawn with |
| `record-review [--report path]` | agent | record the reviewer's `report.json` for the current commit; refuses a report that leaves a changed file unread, and a finding without a changed file and lines inside it. Closes earlier findings whose code changed |
| `finding [--json]` | anyone | list the review findings and what was decided for each |
| `finding accept <FND-ID>... --reason "<why>" --quote "<words>"` | **human decision** | the human keeps the code a finding points at; final approval is refused while a finding has no outcome |
| `record-manual <TEST-ID> passed\|failed --quote "<words>" [--evidence url]` | **human decision** | record a human test result; a pass is refused until every script and agent test passes |
| `agents [--json]` | anyone | model and effort each sub-agent runs with |
| `failures [--classify FAIL-ID --cause-type ... --cause ... --fix-task ... --retest ...]` | agent | list / classify failures |
| `approve design\|final\|split --quote "<words>" [--flag ID...] [--risks ...]` | **human decision** | approval bound to plan hashes / code tree; `--flag` records the items the human pointed at and refuses approval while a real one is among them. `split` approves a group's feature list and creates the features |
| `reject design\|final\|split --reason ... [--to state] [--quote "<words>"]` | agent (records the human's request) | change request |
| `unblock --quote "<words>" --note ...` | **human decision** | release an escalation |
| `scope-change --task T --reason ...` | agent | change outside the task boundary found -> `clarifying` |
| `impact` | anyone | print the impact table: other places that use what this change touches |
| `impact --recheck --searched a,b [--note]` | agent | record the second search, made from the written code, for the current commit; required before `awaiting_final_approval` at L2/L3 |
| `render` | agent | refresh the `hr:*` blocks from evidence |
| `doc-check` | agent | document quality gate: structure, links, diagrams, and filler wording in documents and plan text |
| `check` | anyone | integrity: event chain, schemas, approvals, plan, docs |
| `log [-n 20]` | anyone | recent events |
| `gh status\|create-issues\|link\|sync` | agent | GitHub adapter |
| `merge-check` | agent | merge blockers (approval vs. code, live PR/CI state) |
| `abort [--reason]` | agent (after user confirmation) | cancel; records and branch are kept |

States: `created → triaging → clarifying? → investigating? → planning? → awaiting_design_approval? →
executing → verifying_tasks → integrating → awaiting_final_approval? → ready_to_merge → completed`,
plus `blocked`, `rework_required`, `cancelled`, `failed`.

Group states: `triaging → splitting → awaiting_split_approval → delivering → integrating → completed`. A
feature created by a split waits in `proposed` until `hr start` moves it to `triaging`.
