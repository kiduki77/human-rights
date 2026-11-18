# Design, review-aware task decomposition, test plan

## Design output (`design.md`)

- Feature goal and the confirmed acceptance criteria (link to the requirements document)
- Core structure, interfaces, state transitions
- Task DAG and change boundaries (`hr render` fills the `<!-- hr:tasks -->` block)
- Per-task verification plus the **feature-level integration test plan** (`verification.md`)
- Choices a human must make before implementation
- A sequence diagram only for complex interactions, async flows, or safety boundaries

## Task rules (`task-graph.json`)

Each task has `id`, `title`, `purpose`, `responsibility`, `depends_on`, `requirement_ids`,
`scope.paths` / `scope.modules`, `contracts.provides` / `contracts.consumes`, `acceptance_criteria`,
`verification` (test ids), `risk`, and `human_review`.

- One cohesive change responsibility, whose completion can be judged on its own.
- Don't split by file count or line count. Don't over-split inseparable changes such as shared state,
  interfaces, or DB schemas.
- Use `depends_on` to make tasks that build a data model or public API run first.
- Tasks that create a shared contract list it under `contracts.provides`; tasks that use it list it under
  `consumes`. The runtime hard-fails a task that consumes a contract without depending on its provider,
  and two tasks that provide the same contract.
- Judge parallelism by contract and resource conflicts as well as file conflicts. Tasks that touch the
  same paths without a dependency produce a warning. Never run them in parallel.
- Declare each task's footprint precisely so the scheduler can parallelize it safely: exact
  `scope.paths`, `contracts`, and `resources` (a DB, a port, a device, a SITL rig). Tasks with no paths, or
  with `parallel_safe: false`, always run alone. See [parallel.md](parallel.md).
- `risk: high` requires `human_review: required`.
- Keep the human-facing `tasks/TASK-NNN.md` short (template `task.md`).

## Test plan (`test-plan.json`): fixed before design approval

Integration tests are never improvised after implementation. Before approval, define the acceptance
criteria, targets, procedure, environment, evidence and pass criteria.

- `level: "task"`: per-task unit, component, or contract tests.
- `level: "integration"`: cross-feature integration/E2E, regression across the impact area, and security,
  safety, performance or fault tests where relevant. L2/L3 need at least one required integration test,
  and L3 should have a regression test.
- If a test has a `command`, the runtime runs it. For checks only a human can do, use `command: null`
  with a `procedure` and `automation: "manual"`. A human records the result with `record-manual`.
- Link every must requirement to at least one test, through `requirement_ids` or a task's `verification`.
- Take quantitative pass criteria only from user decisions or design decisions with stated evidence.
- Commands run from the repository root (or the task's worktree root). Confirm during investigation
  that they really exist.
- Concurrency is opt-in per test: mark a test `parallel_safe: true` only if it can share the machine with
  other tests. List what it needs exclusively in `resources`, and use `exclusive: true` for tests that
  must run alone (load tests, hardware rigs).

## Quality gate

1. `hr plan-check` must report zero hard fails. A hard fail is any of: a missing must requirement, a
   missing verification method, a dependency cycle, a risky policy decided without the user, an
   unresolved interface conflict, an open blocking or safety question, or (L2/L3) no integration test.
   Fix warnings, or record in `design.md` why one stays.
2. Independent review: give `hr-plan-reviewer` only the feature directory path, not your own conclusions.
   It reviews requirement coverage, cohesion, verifiability, dependency soundness, reviewability, and
   integrability. A high auxiliary score never outweighs a hard fail. If the plan falls short, re-decompose
   and check again.
3. `hr render`, then `hr doc-check` must pass.
4. With a design gate: `hr transition awaiting_design_approval`, then see [approvals.md](approvals.md).
   Without one (some L2): `hr transition executing`.
