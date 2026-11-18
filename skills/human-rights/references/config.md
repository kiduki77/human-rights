# `.workflow/config.yaml`: repository policy

Humans edit this file. The agent never loosens it: it never removes gates, raises retry limits, turns
on auto-merge, widens parallelism, or turns red pill mode off. To change policy, ask the human.

| Key | Default | Meaning |
|---|---|---|
| `routing.design_gate_modes` | `[L3]` | Modes that always require design approval, on top of the gates the router forces |
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
| `redpill.enabled` | `false` | Red pill mode: occasionally plant a plausible but unacceptable item in the approval tables and refuse rubber-stamp approvals (see [approvals](approvals.md#red-pill-mode-review-vigilance-drills)) |
| `redpill.one_in` | `10` | Drill frequency: about 1 in N approval requests |
| `redpill.gates` | `[design, final]` | Which approval gates can be drilled |
| `redpill.language` | `""` | Language of the scolding (`en`, `ko`); empty follows `docs.language` |
| `docs.language` | `en` | Language of the human-facing reports (the templates are English; the structural checks are language-agnostic) |
| `docs.l0_summary_max_lines` | `15` | Length budget for an L0 `overview.md` |
| `docs.overview_max_lines` | `120` | Length budget for an L2/L3 `overview.md` |

The file supports YAML comments if your team wants to annotate its own policy. The runtime ignores them.
