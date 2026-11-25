# `.human-rights/config.yaml`: repository policy

Humans edit this file. The agent never loosens it: it never removes gates, raises retry limits, turns
on auto-merge, widens parallelism, or turns red pill mode off. To change policy, ask the human.

| Key | Default | Meaning |
|---|---|---|
| `routing.design_gate_modes` | `[L2, L3]` | Modes that always require design approval, on top of the gates the router forces |
| `routing.final_gate_modes` | `[L3]` | Modes that always require final approval |
| `routing.l2_design_gate_min_arch` | `2` | L2 requires design approval when the architecture impact is at least this score |
| `github.enabled` | `auto` | `auto`: use GitHub when `gh auth status` succeeds. `false`: never. `true`: required |
| `github.issue_modes` | `[L2, L3]` | Modes that get a feature Issue and task Issues |
| `github.draft_pr_modes` | `[L2, L3]` | Modes that get draft PRs |
| `github.auto_merge` | `false` | Even when `true`, merging needs `hr merge-check` to pass |
| `verification.max_same_failure_retries` | `3` | The same test failing this many times in a row (on committed code) blocks the feature until a human decides |
| `verification.default_timeout_seconds` | `900` | Per-test timeout |
| `verification.max_parallel_tests` | `4` | Max tests at once. Only `parallel_safe: true` tests run concurrently, never two that share a `resources` entry; `exclusive: true` tests always run alone |
| `scheduler.max_parallel_tasks` | `3` | Max tasks implemented at once in separate worktrees (`1` = sequential) |
| `scheduler.worktree_root` | `""` | Where task worktrees live. Empty: a sibling `<repo>.hr-worktrees/` directory, so test runners and linters in the main checkout never pick up the copies |
| `groups.max_active_children` | `1` | How many features of one group may be in progress at once. The human's review is the bottleneck, so the default is one |
| `redpill.enabled` | `false` | Red pill mode: occasionally plant a plausible but unacceptable item in the approval tables and refuse rubber-stamp approvals (see [approvals](approvals.md#red-pill-mode-review-vigilance-drills)). Turn it off with `hr redpill off --reason`, which logs who, when, and why. A hand edit of this key is not detected |
| `redpill.one_in` | `10` | Drill frequency: about 1 in N approval requests |
| `redpill.gates` | `[design, final]` | Which approval gates can be drilled |
| `redpill.difficulty` | `adaptive` | `easy`, `normal`, `hard`, or `adaptive` (starts easy; up after 2 clean catches in a row, down after 2 misses in a row) |
| `redpill.author` | `agent` | `agent`: `hr-redpill-author` writes candidates for each plan, and an approval request waits for them. `builtin`: the runtime's own lists and row alterations, for hosts without sub-agents |
| `redpill.max_flags` | `3` | A catch made by naming more than this many rows in one approval is recorded as a separate outcome. It is left out of the catch rate and does not move the adaptive level. Naming more rows is still allowed |
| `redpill.language` | `""` | Language of the scolding (`en`, `ko`); empty follows `docs.language` |
| `docs.language` | `en` | Language of everything humans read under `.human-rights/`: templates (`templates/<lang>/`), rendered tables, red pill plants. `en` or `ko`. The structural checks are language-agnostic |
| `docs.l0_summary_max_lines` | `15` | Length budget for an L0 `overview.md` |
| `docs.overview_max_lines` | `120` | Length budget for an L2/L3 `overview.md` |
| `docs.focus_max` | `7` | Most lines in the `hr:focus` "read closely" list of `overview.md`. The rest are counted, not listed |
| `docs.prose_check` | `error` | Filler-wording scan in `hr doc-check` (see [writing](writing.md)). `error`: a hit fails the check and blocks approval requests. `warn`: reported only. `off`: no scan |
| `docs.banned_phrases` | `[]` | Extra words or phrases this team does not want in its documents |
| `docs.allowed_phrases` | `[]` | Hits to accept because they are real terms here (a product name, a field label) |

| `agents.preset` | `balanced` | Which preset the values below came from (`hr init --agents <preset>`): `balanced`, `quality`, `economy`, `inherit` |
| `agents.<role>_model` | see below | `sonnet`, `opus`, `haiku`, `fable`, a full model ID, or `inherit` (the session's model). Roles: `investigator`, `plan_reviewer`, `code_reviewer`, `task_worker`, `tester`, `redpill_author` |
| `agents.<role>_effort` | see below | `low`, `medium`, `high`, `xhigh`, `max`, or empty for the model's default |

| Preset | `hr-investigator` | `hr-plan-reviewer` | `hr-code-reviewer` | `hr-task-worker` | `hr-tester` | `hr-redpill-author` |
|---|---|---|---|---|---|---|
| `balanced` (default) | sonnet / medium | opus / high | opus / high | sonnet / high | sonnet / high | sonnet / high |
| `quality` | opus / medium | opus / high | opus / high | opus / high | opus / high | opus / high |
| `economy` | haiku / default | sonnet / high | sonnet / high | sonnet / medium | sonnet / medium | sonnet / medium |
| `inherit` | session model | session model | session model | session model | session model | session model |

A `config.yaml` written before `code_reviewer` existed has no value for it and gets `opus` / `high`. Run
`hr init --agents <preset>` again, or add `code_reviewer_model` and `code_reviewer_effort`, to change it.

The main conversation (the planner and coordinator) always runs on the session's own model; pick it with
`/model`. `hr agents` shows what each sub-agent will run with.

## Size of the change (`size`)

`hr render` fills the `hr:size` block, and `hr change-size` prints it. The runtime counts from `git diff`
between `state.git.base_sha` (the commit the feature started from) and the commit under approval. At L0 and L1
the work may be uncommitted, so the count then runs to the working tree and includes untracked files, and the
block says so. A rename counts as one file deleted and one added. Files under `.human-rights/` are never
counted. Lines of binary files count as zero.

| Key | Default | Meaning |
|---|---|---|
| `size.test_patterns` | see below | Files counted as tests. Their lines go on their own row. A pattern with no `/` matches the file name (`*_test.go`); a pattern with a `/` matches the whole path from the repository root, where `**/` means any directories (`**/tests/**`) |
| `size.manifests` | see below | Files read for new dependencies. A manifest the runtime has no reader for is listed as changed and not read |
| `size.lockfiles` | see below | Lock files. Their lines go on a third row so one generated file does not bury the code, and their new packages are counted |

Defaults, by ecosystem:

| Ecosystem | `test_patterns` | `manifests` | `lockfiles` |
|---|---|---|---|
| Any | `**/tests/**`, `**/test/**`, `**/__tests__/**`, `**/spec/**` | | |
| Python | `test_*.py`, `*_test.py`, `conftest.py` | `pyproject.toml`, `requirements*.txt`, `Pipfile` | `poetry.lock`, `uv.lock`, `Pipfile.lock` |
| JavaScript, TypeScript | `*.test.*`, `*.spec.*` | `package.json` | `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml` |
| Go | `*_test.go` | `go.mod` | `go.sum` |
| Rust | `**/tests/**` | `Cargo.toml` | `Cargo.lock` |
| Java, Kotlin | `*Test.java`, `*Tests.java`, `*Test.kt`, `*Tests.kt` | `pom.xml`, `build.gradle`, `build.gradle.kts` | `gradle.lockfile` |
| .NET | `*Test.cs`, `*Tests.cs`, `**/*.Tests/**`, `**/*.Test/**` | `*.csproj`, `Directory.Packages.props`, `packages.config` | `packages.lock.json` |
| PHP, Ruby | | `composer.json`, `Gemfile` | `composer.lock`, `Gemfile.lock` |

A key you set replaces its whole list. Quote patterns that start with `*` in YAML. `pnpm-lock.yaml` and
`gradle.lockfile` are counted as lock files but not read for packages. Tests written inside the source file
(Rust `#[cfg(test)]`) count as code.

A dependency is new when its name is in a changed manifest at the commit under approval and not at the starting
commit. A changed version is not a new dependency. Reading `pyproject.toml` and `Cargo.toml` needs Python 3.11
or newer (`tomllib`); on older Pythons those two are listed as changed and not read.

Per task (L2 and L3), the numbers come from the task's commits when the runtime has them, and from the task's
`scope.paths` when it does not. The row says which in its last column:

- **The task's commits.** A task verified in a worktree is counted from the commit its worktree branch started at
  to the commit that was verified. A task verified on the integration branch is counted from the nearest earlier
  recorded commit (the feature's starting commit, another task's verified commit, or the merge of a worktree
  task) to its own verified commit.
- **Files under the task's paths.** Used when the task is not verified, its commit is not in the history of the
  current code, or the range cannot be diffed. The runtime takes the files of the whole diff that match
  `scope.paths`. It cannot see stray changes outside the paths, or the lines of an earlier task in the same file.
- **No paths recorded.** The row is empty.

A file that two tasks changed is counted in both rows, so the rows can add up to more than the total. The row
"Not in any task" lists what the whole diff changed outside every task's files.

## Floor

Paths that always need at least a given level are not in `config.yaml`. They are in
`.human-rights/floor.yaml`, a glob-to-level map (`"src/auth/**": L3`). `config.yaml` is the agent's to edit
freely, so a floor kept there could be deleted by the model it binds. The `floor.yaml` file is changed only by
the owner with `hr floor add|remove --quote`, and a hook denies the agent's edits to it. Each change records a
hash of the rules in `.human-rights/floor.seal`, and the runtime refuses to classify or to move a feature on
while the file and the record disagree. After an edit by hand the owner runs `hr floor accept`. Commit both
files. How it
applies: [routing](routing.md#floor-paths-the-owner-always-gates).

The file supports YAML comments if your team wants to annotate its own policy. The runtime ignores them.
