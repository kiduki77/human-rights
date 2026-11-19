# `hr` command reference

Call it as `.human-rights/hr <command>` (Bash) or `.human-rights\hr.cmd <command>` (PowerShell). Most commands
take `-f FEAT-NNN` and default to the active feature.
Exit codes: `0` ok, `1` a test failed, `2` usage or data error, `3` blocked by a gate.

**Human decisions** are made in chat. The agent runs them with `--quote "<the human's exact words>"`, and the
runtime checks the quote against the human's latest captured message (see
[approvals](approvals.md#chat-decisions)). The human can also run them directly with `--by <name>`.

| Command | Who | What it does |
|---|---|---|
| `init [--language en|ko]` | human / agent (`/hrs:init`) | create `.human-rights/` (config, .gitignore, wrappers); safe to re-run; `--language` sets `docs.language` |
| `new "<title>" --slug s --request "<text>"` | agent | create a feature (`triaging`), make it active |
| `classify --axes <json\|@file\|-> [--flags a,b]` | agent | route / reclassify, set required gates |
| `status [--json]` | anyone | state, approvals, tasks, tests, next human decision |
| `list` | anyone | all features |
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
| `redpill on [--one-in N] [--gates ...] [--language en\|ko]` / `redpill off` / `redpill reveal` (each `--quote "<words>"`) | **human decision** | Red pill mode toggle, frequency, give up on a drill |
| `redpill status` | anyone | Red pill settings and drill results (never whether a drill is active) |
| `metrics [--all] [--json]` | anyone | lead time, approval wait, rework, failures, coverage, test time, tokens, parallel speedup |
| `metrics record --kind <kind> --value N [--note] [--by]` | agent / human | host-reported values: `tokens`, `agent_seconds`, `review_minutes`, `escaped_defect`, `intent_mismatch`, `unnecessary_question`, `question_asked` |
| `templates install\|update\|status [--from DIR] [--force]` | human / agent | install the plugin's (or an org's) template pack into `.human-rights/templates/`; customized files are kept unless `--force` |
| `scaffold [overview requirements design verification codebase research tasks l0-summary review-report] [--overwrite]` | agent | create feature docs from templates (repo first); `tasks` pre-fills from `task-graph.json` |
| `test-brief <TEST-ID> [--json]` | agent | work order for `hr-tester`: the approved steps and pass criteria, the evidence directory, the report shape, and the model to spawn with |
| `record-agent <TEST-ID> [--report path]` | agent | record an agent test from the tester's `report.json`; refuses a missing step result or a passed step without an evidence file |
| `record-manual <TEST-ID> passed\|failed --quote "<words>" [--evidence url]` | **human decision** | record a human test result; a pass is refused until every script and agent test passes |
| `agents [--json]` | anyone | model and effort each sub-agent runs with |
| `failures [--classify FAIL-ID --cause-type ... --cause ... --fix-task ... --retest ...]` | agent | list / classify failures |
| `approve design\|final --quote "<words>" [--flag ID...] [--risks ...]` | **human decision** | approval bound to plan hashes / code tree; `--flag` records the items the human pointed at and refuses approval while a real one is among them |
| `reject design\|final --reason ... [--to state] [--quote "<words>"]` | agent (records the human's request) | change request |
| `unblock --quote "<words>" --note ...` | **human decision** | release an escalation |
| `scope-change --task T --reason ...` | agent | change outside the task boundary found -> `clarifying` |
| `render` | agent | refresh the `hr:*` blocks from evidence |
| `doc-check` | agent | document quality gate |
| `check` | anyone | integrity: event chain, schemas, approvals, plan, docs |
| `log [-n 20]` | anyone | recent events |
| `gh status\|create-issues\|link\|sync` | agent | GitHub adapter |
| `merge-check` | agent | merge blockers (approval vs. code, live PR/CI state) |
| `abort [--reason]` | agent (after user confirmation) | cancel; records and branch are kept |

States: `created → triaging → clarifying? → investigating? → planning? → awaiting_design_approval? →
executing → verifying_tasks → integrating → awaiting_final_approval? → ready_to_merge → completed`,
plus `blocked`, `rework_required`, `cancelled`, `failed`.
