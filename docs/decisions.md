# Design decisions

Six questions shaped the design early on. This is how v0.1 settles them. Every one can be revisited.

| # | Question | v0.1 decision | Why |
|---|---|---|---|
| 1 | First host | **Claude Code.** The skill, templates, schemas and runtime are host-independent; see `skills/human-rights/references/host-adapters.md` for other hosts | It has plugins, skills, sub-agents, and PreToolUse hooks, and the hooks are what let us deny agent self-approval |
| 2 | GitHub policy | **Optional for L0/L1**; Issues and draft PRs by default for L2/L3 (`github.issue_modes`, `draft_pr_modes`); `enabled: auto` | Small changes shouldn't need GitHub ceremony; larger ones benefit from a reviewable trail. Unavailable GitHub is reported as "manual action needed", never as success |
| 3 | Trusted approval event | **An explicit CLI command run by the human** (`! .workflow/hr approve ...`), plus GitHub branch protection for merges | The `!` prefix runs outside the agent's tools, so the hook doesn't apply to the human but does apply to the agent. Chat text is never an approval |
| 4 | What `.internal/` commits | **Commit** state, requirements, task graph, test plan, test results, failures, events. **Ignore** `logs/`, `cache/`, locks, and the machine-local `hr` wrappers | Results and approvals must survive sessions and machines. Raw logs are bulky, so each result keeps a log hash and reference |
| 5 | Test environment | Each test declares `environment` and `automation`. Anything with `command: null` is human-only and recorded with `record-manual` | Hardware and SITL checks can't always be automated. Making them explicit stops them from being silently skipped |
| 6 | Mode calibration | **Start from heuristics** (`references/routing.md`), and record every classification as an event for later tuning against review time and defects | Good thresholds can only come from real usage data. The events already carry axes, effective scores, and flags |

## Other choices made during implementation

- **Approvals bind to a code tree fingerprint**: the hash of the HEAD tree with `.workflow/` removed. A raw
  tree SHA would change every time a report is committed. The fingerprint changes exactly when code does.
- **Design approval excludes runtime task fields** (`status`, `verified_evidence`, `notes`), so progress
  updates don't invalidate it. Plan edits do.
- **Uncommitted results count only for L0/L1.** L2/L3 task verification and final approval need clean,
  committed code. Uncommitted runs bind to a worktree hash, so even L0 evidence matches the exact code
  tested.
- **Escalation is a human-only release.** The retry limit (default 3) counts only clean runs, so
  iterating locally on uncommitted code never triggers it.
- **Stdlib-only runtime, Python 3.8+.** There is nothing to install for gates to work; `jsonschema` is an
  optional extra.

## Phase 3 choices

- **Conservative conflict detection.** A task runs in parallel only with a declared footprint. Unknown
  paths, overlapping paths (directory or glob prefixes count), a provide/consume or provide/provide
  contract pair, or a shared resource all serialize it. A wrongly serialized task costs minutes; a
  wrongly parallelized one costs a broken integration.
- **Worktrees outside the repo** (`<repo>.hr-worktrees/` by default). Nested worktrees would be picked
  up by test runners, linters, and file watchers in the main checkout.
- **Dependencies must be merged, not just verified.** A dependent task's worktree starts from the
  integration branch, so its dependencies have to be there first. That also makes dependent merges
  sequential by construction.
- **Worktree evidence never counts for integration.** It is bound to the worktree's code version. The
  merged tree is a new version, and the full plan re-runs on it, so final verification always runs on the exact integrated code.
- **Test concurrency is opt-in** (`parallel_safe: true`). Most suites assume they own ports, temp dirs,
  and databases. A run whose code changed mid-execution is recorded as `error`.
- **Workers never touch state.** `hr-task-worker` only edits and commits inside its worktree. The
  coordinator verifies, records, and merges, so `state.json` keeps a single writer.
- **Lock heartbeat.** The state lock is refreshed every 5 s and treated as stale after 30 s without a
  heartbeat. Before this, a test run longer than 120 s could have its lock taken over.
- **Metrics the runtime can't observe are recorded explicitly** (`hr metrics record`): tokens, review
  minutes, escaped defects, intent mismatches, unnecessary questions. Everything else comes from the event log.
- **Template packs are hash-tracked.** Locally customized templates are never overwritten without `--force`.

## Red pill mode (review-vigilance drills)

- **The plant lives only in rendered review tables** (`overview.md`, `verification.md`). Plan JSON and
  `design.md` never contain it, so it can't be executed or merged, and approval hashes ignore it.
  Generated `hr:*` blocks are now excluded from the `design.md` hash. Before this, re-rendering task
  statuses after approval would have invalidated the design approval.
- **The runtime rolls, not the agent.** The roll uses `random.SystemRandom` once per entry into an
  approval state. A change request ends the drill, and resubmitting rolls again.
- **Catching it is a human action** (`hr flag`, hook-guarded, like approve). Flagging a real item gets
  the same neutral reply and is recorded as a review concern, so the drill can't be probed by guessing.
- **Plants come from a built-in catalog parameterized with the feature's own IDs, requirements, and
  modules.** They are not LLM-generated, so they stay plausible, deterministic in kind, and impossible for
  the agent to tone down.
- **Toggle and frequency are human-only.** `redpill on/off/reveal` are hook-guarded and the agent may not
  edit `config.yaml` to loosen it. `redpill status` never reveals whether a drill is active.
