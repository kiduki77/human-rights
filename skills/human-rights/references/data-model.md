# Data model: the files you write and the files the runtime writes

Location: `.human-rights/features/<FEAT-id>/.internal/`. Schemas: the plugin's `schemas/*.schema.json`.
`hr check` validates them when `pip install jsonschema` is available.
The machine-readable JSON drives execution. The human-facing Markdown is a rendering of it. Don't hand-copy
the same fact into several places.

| File | Writer | Content |
|---|---|---|
| `requirements.json` | agent | revision, goal, scope, requirements (+acceptance), decisions, open_questions, assumptions |
| `task-graph.json` | agent (`status` / `verified_evidence` via `hr task`) | tasks |
| `test-plan.json` | agent (in L0/L1, `hr verify --adhoc` may add tests) | tests |
| `state.json` | **runtime only** | state, mode, gates, approvals, git/GitHub links |
| `test-results.json` | **runtime only** | runs: result, commit_sha, code_tree, dirty, log hash |
| `failures.json` | **runtime only** (classify with `hr failures --classify`) | FAIL-NNN records |
| `events.jsonl` | **runtime only** | hash-chained event log (tamper evidence) |
| `logs/` | runtime (git-ignored) | raw test output |
| `../evidence/<TEST-id>/` | `hr-tester` (git-ignored; hashes are kept in `test-results.json`) | per-step evidence and `report.json` of agent tests |

The design approval is bound to the hashes of `requirements.json`, `test-plan.json`, the plan fields of
`task-graph.json` (runtime fields such as status are excluded), and `design.md`. If any of them changes,
the approval is invalidated and the state goes back to `planning`.

Final approval and test results are bound to the **code tree fingerprint**: the HEAD tree hash with
`.human-rights/` excluded. So committing `.human-rights/` documents never breaks an approval, while a one-character
code change does.

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

