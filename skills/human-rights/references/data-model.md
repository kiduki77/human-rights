# Data model: the files you write and the files the runtime writes

Location: `<feature or group directory>/.internal/`. A feature on its own is at
`.human-rights/features/<FEAT-id>/`, a group at `.human-rights/groups/<GRP-id>/`, and a group's features
inside it at `groups/<GRP-id>/features/<FEAT-id>/` (see [Groups](#groups)). Take the path from what `hr`
prints, not from a pattern. Schemas: the plugin's `schemas/*.schema.json`.
`hr check` validates them when `pip install jsonschema` is available.
The machine-readable JSON drives execution. The human-facing Markdown is a rendering of it. Don't hand-copy
the same fact into several places.

| File | Writer | Content |
|---|---|---|
| `requirements.json` | agent | revision, goal, scope, requirements (+acceptance), decisions, open_questions, assumptions, impact (L2/L3: other places that use what changes) |
| `task-graph.json` | agent (`status` / `verified_evidence` via `hr task`) | tasks |
| `test-plan.json` | agent (in L0/L1, `hr verify --adhoc` may add tests) | tests |
| `state.json` | **runtime only** | state, mode, gates, approvals, git/GitHub links |
| `test-results.json` | **runtime only** | runs: result, commit_sha, code_tree, dirty, log hash |
| `failures.json` | **runtime only** (classify with `hr failures --classify`) | FAIL-NNN records |
| `findings.json` | **runtime only** (`hr record-review`, `hr finding accept`) | reviews of the written code (REV-NNN, bound to a commit and code tree) and their findings (FND-NNN: kind, file, lines, outcome) |
| `events.jsonl` | **runtime only** | hash-chained event log (tamper evidence) |
| `logs/` | runtime (git-ignored) | raw test output |
| `../evidence/<TEST-id>/` | `hr-tester` (git-ignored; hashes are kept in `test-results.json`) | per-step evidence and `report.json` of agent tests |
| `../evidence/code-review/` | `hr-code-reviewer` (git-ignored) | `report.json` of the latest review of the written code |

The design approval is bound to the hashes of `requirements.json`, `test-plan.json`, the plan fields of
`task-graph.json` (runtime fields such as status are excluded), and `design.md`. If any of them changes,
the approval is invalidated and the state goes back to `planning`.

Final approval and test results are bound to the **code tree fingerprint**: the HEAD tree hash with
`.human-rights/` excluded. So committing `.human-rights/` documents never breaks an approval, while a one-character
code change does.

## Groups

A group (a compound request) has `kind: "group"` in `state.json` and two files you write:

- `.internal/split.json`: `children` (each `key`, `title`, `outcome`, `verify_alone`, optional `depends_on`,
  `expected_mode`, `sources`, `code_status`), `shared_decisions`, `excluded`, and optional `source`
  (`kind: request|document`, `path`, `unread`). Schema: `schemas/split.schema.json`. Example and rules:
  [splitting](splitting.md).
- `.internal/test-plan.json`: the checks of the features working together. Same shape as a feature's test
  plan, plus `children` on each test (the feature keys it exercises).

The runtime writes the rest: `children` (key to feature id), `approvals.split`, and on each created feature
`parent` and `group_key`. A feature records its size decision in `size`.

Where a group lives, and what it is called:

```text
.human-rights/
├── features/FEAT-012-fix-typo/          a feature on its own
└── groups/GRP-001-login/                a group: overview.md, split.json, the group checks
    ├── features/FEAT-002-signup/        its features, each with the usual files
    ├── features/FEAT-003-login/
    └── groups/GRP-004-reset/            a feature of the group that was split again
        └── features/FEAT-005-reset-by-email/
```

- `hr transition splitting` renames the feature from `FEAT-NNN-slug` to `GRP-NNN-slug` and moves its
  directory under `groups/`. Going back from `splitting` to `clarifying` or `investigating` reverses both.
  The number is kept, and numbers are never shared between a `FEAT-` and a `GRP-`, so `-f FEAT-001` still
  finds `GRP-001-login`.
- Events written before the rename keep the old id. A `renamed` event records the change, and a `moved`
  event records a directory move without a rename.
- A workspace created before this layout keeps working. `hr list` says so, and `hr migrate` moves it
  (`--dry-run` shows the moves first).

## Minimal examples

`requirements.json`

```json
{"revision": 1,
 "goal": "...", "scope": {"in": ["..."], "out": ["..."]},
 "requirements": [{"id": "REQ-001", "text": "...", "priority": "must", "source": "user",
                   "acceptance": [{"id": "AC-001", "text": "a verifiable sentence"}]}],
 "decisions": [{"id": "DEC-001", "question": "...", "answer": "...", "decided_by": "user", "safety": true}],
 "open_questions": [{"id": "Q-001", "text": "...", "blocking": true, "safety": false, "status": "open"}],
 "assumptions": [{"id": "ASM-001", "text": "...", "risk": "low"}]}
```

`task-graph.json`

```json
{"tasks": [{"id": "TASK-001", "title": "...", "purpose": "...", "status": "planned",
            "depends_on": [], "requirement_ids": ["REQ-001"],
            "scope": {"modules": ["..."], "paths": ["src/..."]},
            "contracts": {"provides": ["VehicleRegistry"], "consumes": []},
            "acceptance_criteria": [{"id": "AC-T1-1", "text": "..."}],
            "verification": ["TEST-001"], "risk": "medium", "human_review": "optional"}]}
```

`test-plan.json`

```json
{"regression": {"scope": "targeted", "rationale": "only src/x changes; its callers are covered by TEST-012"},
 "tests": [{"id": "TEST-001", "title": "...", "type": "unit", "level": "task",
            "task_ids": ["TASK-001"], "requirement_ids": ["REQ-001"],
            "command": "pytest tests/unit/test_x.py", "environment": "local",
            "pass_criteria": "the 6 boundary cases in test_x.py pass", "covers": ["src/x"], "required": true},
           {"id": "TEST-020", "title": "...", "type": "e2e", "level": "integration", "runner": "agent",
            "command": null, "environment": "dev stack + browser", "estimated_seconds": 300,
            "pass_criteria": "all 2 steps observed",
            "steps": [{"do": "enter 0.3 in the interval box", "expect": "the start button is disabled"},
                      {"do": "enter 2 and start", "expect": "the panel shows 'interval 2 s'"}], "required": true},
           {"id": "TEST-021", "title": "...", "type": "safety", "level": "integration", "runner": "human",
            "command": null, "human_reason": "needs a real vehicle stream",
            "pass_criteria": "...", "steps": [{"do": "...", "expect": "..."}], "required": true}]}
```

Test `type`: unit, component, contract, integration, e2e, regression, security, safety, performance, manual,
static (lint, format, type check: never requirement evidence).
`runner`: `command` (default when `command` is set), `agent`, `human` (default otherwise).

A decision that differs from what the user answered:
`{"id": "DEC-005", "question": "...", "answer": "0.5-6 s", "decided_by": "code",
  "overrides_user_answer": "0.5-10 s", "reason": "the engine pairs frames only within 6.5 s"}`.
A task: add `"changes_flow": true | false`.

Optional fields for parallel execution:

| File | Field | Meaning |
|---|---|---|
| `task-graph.json` task | `resources: [..]` | shared resources; tasks sharing one never run in parallel |
| `task-graph.json` task | `parallel_safe: false` | never run this task in parallel |
| `test-plan.json` test | `parallel_safe: true` | opt-in: may run concurrently with other parallel-safe tests |
| `test-plan.json` test | `resources: [..]` | tests sharing a resource never run together |
| `test-plan.json` test | `exclusive: true` | always run alone |

The runtime adds `parallel` to `state.json` (integration branch, worktrees, batches), and adds
`worktree_task` and `concurrency` to each run in `test-results.json`.

