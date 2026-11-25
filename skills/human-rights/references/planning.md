# Design, review-aware task decomposition, test plan

## Design output (`design.md`)

- Feature goal and the confirmed acceptance criteria (link to the requirements document)
- Core structure, interfaces, state transitions
- Task DAG and change boundaries (`hr render` fills the `<!-- hr:tasks -->` block)
- Per-task verification plus the **feature-level integration test plan** (`verification.md`)
- Choices a human must make before implementation
- **What the design introduces**: every new module, layer or dependency, each with the requirement behind
  it, the existing thing in the repository that was considered, and why it was not used. "Nothing new" is a
  valid answer. The default is the smallest safe change to the existing structure, and this list is where
  a departure from it is argued. At L2 and L3 `hr doc-check` fails when the section is missing or empty:
  it looks for the line `<!-- hr:introduces -->` under the section heading, in any language.
- **A diagram of what changes** whenever the change crosses a module or process boundary, or any task
  changes a flow: a sequence diagram for calls across boundaries, a state diagram for changed states, or a
  before/after component diagram. `hr doc-check` fails without one. A reviewer reads a picture faster than
  a paragraph.
- Behaviour and interfaces only. Code expressions (a regex, a comparison, decorator lists) belong in the
  task documents, not in `design.md`.

## Task rules (`task-graph.json`)

Each task has `id`, `title`, `purpose`, `responsibility`, `depends_on`, `requirement_ids`,
`scope.paths` / `scope.modules`, `contracts.provides` / `contracts.consumes`, `acceptance_criteria`,
`verification` (test ids), `risk`, and `human_review`.

- One cohesive change responsibility, whose completion can be judged on its own.
- Every task serves a requirement: list it in `requirement_ids`. A task nothing asks for is a warning at
  L0 and L1, and a hard fail at L2 and L3. Link it to the requirement it serves or remove it.
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
- Set `changes_flow` on every task. `true` when the task changes an interface, a message between
  components, or a state machine; its `tasks/TASK-NNN.md` then needs a Mermaid diagram of that interaction.
  `false` for a change inside one component (reading one more field, a validation rule, a label); no
  diagram, and don't draw one for show.
- Keep the human-facing `tasks/TASK-NNN.md` short (template `task.md`).

## Test plan (`test-plan.json`): fixed before design approval

Nothing about verification is improvised after implementation. The human approves, at the design gate,
**what is tested, who runs it, what exactly counts as a pass, and what it costs to run**. All of it is in
`test-plan.json`, so changing any of it later invalidates the approval.

### Who runs a test (`runner`)

Machines first. A human tests only what a machine cannot.

| `runner` | When | How the result is recorded |
|---|---|---|
| `command` | anything a script can decide: unit, contract, integration, a Playwright spec | `hr verify` runs `command`; exit code and log are the evidence |
| `agent` | behaviour that needs driving the real product: browser end-to-end, UI states, exploratory probing | `hr-tester` performs `steps` and saves evidence per step; `hr record-agent` checks the report |
| `human` | judgement or hardware a machine cannot supply: real devices, subjective quality, safety sign-off | the human reports in chat; `hr record-manual --quote`. Only after every `command` and `agent` test passes |

- A UI or user-flow change needs a browser-level test (`agent`, or a `command` running a browser script).
  A jsdom unit test is not that.
- `runner: human` requires `human_reason`: why neither a script nor an agent can do it. "It is an E2E
  test" is not a reason. Split a mixed test: the automatable steps become an `agent` test, and only the
  remainder stays `human`.
- Prefer turning an agent test into a script once it has run: a Playwright spec is cheaper to re-run and
  harder to fool than a description. Change the plan (and get re-approval) to do so.

### Pass criteria

- Every test has `pass_criteria`: one observable, binary statement. "Works correctly", "as expected",
  and "steps 2-7 as expected" are not criteria.
- `agent` and `human` tests have `steps`, each `{"do": "...", "expect": "..."}`. `expect` is the result that
  must be observed for that step to pass: the text on screen, the disabled button, the count within a
  range. A step without `expect` is a hard fail.
- For a `command` test, say what the exit code proves: which cases the suite contains, not just "exit 0".
- Take numeric thresholds only from user decisions or design decisions with stated evidence.

### How much to re-run (`regression`, `covers`)

- `regression: {"scope": "targeted" | "full", "rationale": "..."}` at the top of the file. Decide it from
  what the change can break, not from how many places it touches:
  - `targeted` when the change stays inside leaf modules: the tests of those modules and of their direct
    callers, plus one contract test per boundary it crosses.
  - `full` when it changes shared code, a public contract, a data model, or anything with a safety flag.
  The rationale names what was deliberately left out. The human approves the scope with the design.
- Give each test `covers`: the paths whose change can alter its result. After a later commit, the runtime
  keeps a passing result if no changed file falls under `covers`, and marks it stale otherwise. A test
  without `covers` re-runs after every code change. Wrong `covers` hides regressions, so list the code
  under test and what it calls.
- Give each integration test `estimated_seconds`. The rendered table shows the total, so the human sees
  what the plan costs before approving it.
- If the repository's CI runs the full suite on every push, say so in the rationale and keep the local
  plan targeted.

### Other rules

- `level: "task"`: per-task unit, component, or contract tests. `level: "integration"`: feature-level
  integration, end-to-end, regression, and security, safety, performance or fault tests where relevant.
  L2/L3 need at least one required integration test.
- Linting, formatting and type checks are `type: "static"`. They run like any command test but never
  count as evidence for a requirement.
- Link every must requirement to at least one non-static test, through `requirement_ids` or a task's
  `verification`.
- Commands run from the repository root (or the task's worktree root). Confirm during investigation
  that they really exist.
- Concurrency is opt-in per test: mark a test `parallel_safe: true` only if it can share the machine with
  other tests. List what it needs exclusively in `resources`, and use `exclusive: true` for tests that
  must run alone (load tests, hardware rigs).

## Quality gate

1. `hr plan-check` must report zero hard fails. A hard fail is any of: a missing must requirement, a
   missing verification method, a dependency cycle, a risky policy decided without the user, an
   unresolved interface conflict, an open blocking or safety question, (L2/L3) a task linked to no
   requirement, (L2/L3) no integration test, a
   human test without `human_reason`, an agent or human test whose steps lack `expect`, no `regression`
   scope and rationale, a task without `changes_flow`, or (L2/L3) no `impact` in `requirements.json`, an
   impact row without evidence, a `change` row without a task, a `check` row without a real test, or an
   `unrelated` row without a reason ([investigation](investigation.md#impact-other-places-that-use-it)).
   Fix warnings, or record in `design.md` why one stays.
2. Independent review: give `hr-plan-reviewer` only the feature directory path, not your own conclusions.
   It reviews requirement coverage, cohesion, verifiability, dependency soundness, reviewability,
   integrability, and need: whether each task and each new module, layer or dependency has a requirement
   behind it, and why what the repository already has is not enough. A high auxiliary score never outweighs a hard fail. If the plan falls short, re-decompose
   and check again.
3. `hr render`, then `hr doc-check` must pass.
4. With a design gate (L2 and L3 by default): `hr transition awaiting_design_approval`, then see
   [approvals.md](approvals.md). Without one: `hr transition executing`.
