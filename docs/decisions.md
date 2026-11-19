# Design decisions

Six questions shaped the design early on. This is how v0.1 settles them. Every one can be revisited.

| # | Question | v0.1 decision | Why |
|---|---|---|---|
| 1 | First host | **Claude Code.** The skill, templates, schemas and runtime are host-independent; see `skills/human-rights/references/host-adapters.md` for other hosts | It has plugins, skills, sub-agents, and PreToolUse hooks, and the hooks are what let us deny agent self-approval |
| 2 | GitHub policy | **Optional for L0/L1**; Issues and draft PRs by default for L2/L3 (`github.issue_modes`, `draft_pr_modes`); `enabled: auto` | Small changes shouldn't need GitHub ceremony; larger ones benefit from a reviewable trail. Unavailable GitHub is reported as "manual action needed", never as success |
| 3 | Trusted approval event | **The human's own chat message**, captured by a `UserPromptSubmit` hook and quoted to `hr ... --quote`, plus GitHub branch protection for merges (v0.4; v0.1-0.3 required `! .human-rights/hr approve ...`) | Typing `!` commands made review feel like paperwork. The hook only ever sees text the human typed, so a quote that matches their latest message, sent after the gate opened, is tied to a real human act. A direct `--by` CLI path stays for hosts without hooks |
| 4 | What `.internal/` commits | **Commit** state, requirements, task graph, test plan, test results, failures, events. **Ignore** `logs/`, `cache/`, locks, and the machine-local `hr` wrappers | Results and approvals must survive sessions and machines. Raw logs are bulky, so each result keeps a log hash and reference |
| 5 | Test environment | Each test declares `environment` and `automation`. Anything with `command: null` is human-only and recorded with `record-manual` | Hardware and SITL checks can't always be automated. Making them explicit stops them from being silently skipped |
| 6 | Mode calibration | **Start from heuristics** (`references/routing.md`), and record every classification as an event for later tuning against review time and defects | Good thresholds can only come from real usage data. The events already carry axes, effective scores, and flags |

## Other choices made during implementation

- **Approvals bind to a code tree fingerprint**: the hash of the HEAD tree with `.human-rights/` removed. A raw
  tree SHA would change every time a report is committed. The fingerprint changes exactly when code does.
- **Design approval excludes runtime task fields** (`status`, `verified_evidence`, `notes`), so progress
  updates don't invalidate it. Plan edits do.
- **Uncommitted results count only for L0/L1.** L2/L3 task verification and final approval need clean,
  committed code. Uncommitted runs bind to a worktree hash, so even L0 evidence matches the exact code
  tested.
- **Escalation is a human-only release.** The retry limit (default 3) counts only clean runs, so
  iterating locally on uncommitted code never triggers it.
- **The workspace is `.human-rights/` (v0.4; `.workflow/` before).** The old name was too generic to tell
  apart from other tools. `hr init` moves an old `.workflow/` only when its `config.yaml` is recognisably
  ours, and code fingerprints exclude both names so the move never invalidates an approval.
- **Sub-agent models are repository policy (v0.4).** `/hrs:init` asks for a preset and writes it to the
  `agents:` section of `config.yaml`. The agent files say `model: inherit`, and the coordinator passes
  each role's model and effort on every Agent call. The per-call value is what the host honours first,
  so a repository can pin or loosen models without editing the plugin.
- **Human-facing text follows `docs.language` (v0.4).** Templates come from `templates/<lang>/`, and
  rendered tables and red pill plants use the same language. A plant in a different language from the
  table around it would give the drill away.
- **Machines test first; humans test what machines cannot (v0.4).** Each test names its runner: a script,
  an agent (`hr-tester`, with a browser), or a human with a stated reason. Earlier versions sent every test
  without a command to a human, which spent human time on checks a browser agent does better.
- **An agent's "pass" needs per-step evidence (v0.4).** The steps and each step's expected result are fixed
  in the approved plan. The tester is a separate agent from the implementer, and the runtime refuses a
  passed step without an evidence file. "The agent looked and it was fine" stays what it always was here:
  not evidence.
- **Results survive unrelated commits (v0.4).** A test may declare `covers` paths. A passing result is kept
  while no later commit touches them, and becomes stale otherwise. Before this, every code change
  re-ran every required test, which made a one-line fix cost the whole suite. The regression scope and
  its rationale are part of the approved plan.
- **L2 gets a design gate by default (v0.4).** Reclassifying after clarification moves many features from
  L3 to L2, and those are exactly the ones where a human reviewing the design still finds problems.
- **Diagrams are required where a change crosses a boundary (v0.4).** The earlier rule ("only when
  genuinely complex") produced none. Tasks declare `changes_flow`, and `hr doc-check` enforces a diagram
  for the design and for each such task, and nowhere else.
- **The size of a request is judged before its grade (v0.5).** A compound request used to become one L3
  feature with one approval covering everything, which no human can review. Now a request with several
  separately verifiable results becomes a group, and the human approves the list of features first. The
  judgment lives in the normal start of work, not in a separate command, because a one-line request and a
  120-page document need the same question asked.
- **Depth comes from repeating the rule, not from fixed levels (v0.5).** A feature created by a split is
  judged for size again when it starts, so a group nests only where the work is actually compound. A part
  that cannot be verified alone stays a task.
- **A group needs a check that crosses its features (v0.5).** Features that pass on their own can fail
  when joined. Without a required cross-feature check the split is rejected.
- **A source document is traced both ways (v0.5).** Features cite pages, non-requirements are listed as
  excluded, unread parts are listed for the human, and what the code already does is not planned again.
  Otherwise the reader cannot tell what was dropped.
- **Filler wording is a gate, not a style note (v0.5).** A word list cannot define good writing, and it
  covers only English and Korean. It is still enforced as an error because advice alone was ignored, and
  the rule and the reviewer carry the part a list cannot. Teams can extend, relax, or turn it off.
- **Red pill plants are written per feature, by an agent the coordinator cannot see (v0.5).** A fixed list
  of flawed rows becomes recognisable after a few drills, and then the human is matching phrases, not
  reviewing. A separate agent reads the feature and writes candidates that are wrong for that feature. It
  submits them to the runtime directly, they are stored unreadable at a glance, and a hook denies reading
  them, so the conversation that asks for approval cannot give a drill away. Candidates are required
  before every approval request while the mode is on, so asking for them reveals nothing.
- **The hardest drills change a real row (v0.5).** An added row is found by counting. A real row whose
  criterion, number, or dependency was changed is found only by comparing it with the requirements and
  decisions, which is the review skill the mode exists to train.
- **Every drill ends with the reason (v0.5).** Catching or giving up shows why the item was unacceptable
  and what the real value is. Difficulty adapts to the human's record. The aim is a better reviewer, not a
  score.
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
- **Pointing at the plant is the review (v0.4).** A chat message that names or describes the planted row
  catches it and approves in the same step. Pointing at a real row is also a review: it is recorded as a
  concern and blocks that approval until the agent addresses it. So engaging with the material is never
  scolded, and only a blind "approved" is.
- **Toggle and frequency are human decisions.** `redpill on/off/reveal` are hook-guarded and the agent may not
  edit `config.yaml` to loosen it. `redpill status` never reveals whether a drill is active.
