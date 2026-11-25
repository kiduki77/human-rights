# Human approval: design gate and final gate

Humans decide in chat. "Looks good, go ahead", "TEST-014 이상한데", or "/hrs:approve" are all
decisions, and the agent records them with the runtime. No `!` command is needed. These records are not a
security boundary. Real merge control comes from GitHub branch protection.

## Chat decisions

A `UserPromptSubmit` hook (`hooks/prompt_capture.py`) stores each message the human types in
`.human-rights/.local/prompts.jsonl`. The file is git-ignored, keeps the last 20 messages, and the agent may not
write it. Every human decision goes through `hr` with `--quote "<the human's exact words>"`. The runtime
accepts the quote only if it appears in the human's **latest** message (whitespace and case are ignored).
For a gate or a block, that message must also be newer than the moment the feature reached that point. The
approval record and event keep `via: chat`, the quote, and the message hash.

Read the human's latest message and map it:

| The human says | You run |
|---|---|
| approves, without pointing at anything ("좋아, 진행해", "LGTM") | `hr approve <gate> --quote "<words>" [--risks "<risk they accept>"]` |
| points at items ("TEST-014 검증이 이상해", "the 60 s check proves nothing") | `hr approve <gate> --quote "<words>" --flag <ID> [<ID> ...]`, one ID per item they criticised |
| asks for changes to the plan or the result | apply them: `hr reject <gate> --reason "<summary>" --quote "<words>"`, then re-plan or rework |
| reports a manual test ("TEST-013 해봤는데 통과, 영상 링크 …") | `hr record-manual TEST-013 passed --quote "<words>" [--evidence <url>]` |
| releases a block ("이미지 고쳤어, 다시 해봐") | `hr unblock --quote "<words>" --note "<their decision>"` |
| gives up on a drill ("정답 보여줘") | `hr redpill reveal --quote "<words>"` |
| turns drills on ("레드필 켜줘, 5번에 한 번") | `hr redpill on --one-in 5 --quote "<words>"` |
| turns drills off ("레드필 꺼줘, 오늘 배포해야 해") | `hr redpill off --reason "<their reason, in their words>" --quote "<words>"` |

Rules:

- A description is enough. When the human describes an item instead of naming its ID, match it to the row
  in the rendered tables you showed them and pass that ID. When you can't tell which row they mean, ask.
- `--flag` takes exactly the items the human criticised. Never add one they didn't mention, and never
  leave one out.
- Pointing at items is a real review. `hr approve ... --flag` handles each item. A planted drill item is
  caught and removed. Every other item becomes a review concern, and the approval is refused with
  "not approved: the human pointed out ...". In that case, address each point: change the plan and
  resubmit, or explain why it is fine. Then wait for the human's next message.
- If the message is ambiguous ("음…", "나중에"), don't record anything. Ask.
- `--by` defaults to the repository's `git config user.name`.
- A human can still run any of these themselves with `.human-rights/hr ... --by <name>`, in their own terminal.
  Without `--quote` the runtime refuses the decision unless it runs at a terminal, so a tool call or a script
  cannot carry `--by`. This includes the `!` prefix, which has no terminal either. Hosts without a prompt hook
  need the terminal path. See [host-adapters](host-adapters.md).

## Requesting split approval (`awaiting_split_approval`)

A group asks the human to approve its list of features before any of them starts. Show the rendered group
`overview.md` and say what the human can answer: approve, or name what to drop, merge, add or reorder.
Point out the two things most worth checking, in words: usually an exclusion and a shared decision.

- Approval: `hr approve split --quote "<their words>"`. The runtime creates the features and moves the
  group to `delivering`.
- A change to the list: `hr reject split --reason "..." --quote "<their words>"`, edit `split.json`, ask again.
- The approval is bound to `split.json` and the group's `test-plan.json`. Editing either later invalidates
  it and returns the group to `splitting`.

Red pill drills do not run on this gate. Rules for the split itself: [splitting](splitting.md).

## Requesting design approval (`awaiting_design_approval`)

1. Pass `hr plan-check`, apply the independent review, run `hr render`, and pass `hr doc-check`.
2. `hr transition awaiting_design_approval`.
3. Show the human (1-2 screens, based on `overview.md`), in this order:
   - the one-line conclusion: what changes and why
   - the "read closely" list from the focus block, pasted as rendered: the rows to read slowly, each with
     the reason it is listed. Don't add to it, remove from it, or reword it
   - **anything that differs from what they answered**, first and on its own: the "changed from your
     answer" table from the decisions block. Never fold it into a sentence
   - the remaining decisions and the assumptions made for them, pasted from the decisions block. Say each
     thing in words; a bare ID sends the reader to another file
   - the recommended design, with its diagram (or a link to it in `design.md`) and a one-line comparison
     to the alternatives
   - the task table, and the verification table with **who runs each test, its pass criteria, the
     regression scope, and the estimated run time**, pasted verbatim from the rendered tables in
     `overview.md` (never rebuilt from the JSON). Point out which tests a human is asked to run and why
   - remaining risks and unknowns
   - the decision you need:

```
Design approval needed. Review: .human-rights/features/FEAT-001-multi-drone/overview.md

  approve:         say so in chat (or /hrs:approve)
  point at items:  tell me which row looks wrong, by ID or by describing it
  request changes: tell me what to change (requirements, design, or test plan)
  hold:            do nothing; nothing gets implemented before approval
```

4. Act on the reply as in [Chat decisions](#chat-decisions). On a change request, record it with
   `hr reject design --reason "<summary>" --quote "<words>" [--to clarifying|planning|investigating]` and go
   back to that stage. On approval, the runtime moves the feature to `executing`. Confirm with `hr status`,
   then continue.

Design approval is bound to the hashes of the plan files: `requirements.json`, the plan fields of
`task-graph.json`, `test-plan.json`, and `design.md`. Changing any of them after approval invalidates the
approval and moves the state back to `planning`. If a change is needed, make it, show what changed, and
get re-approval. Never hide decisions outside the plan files to avoid invalidation.

## Requesting final approval (`awaiting_final_approval`)

Precondition: all code is committed, every required test passed **on the current commit**, no failures
are unresolved, and at L2 and L3 the written code was reviewed on that commit (see
[integration.md](integration.md)).

1. `hr render`, update `overview.md` into the final-report shape (structure of `review-report.md`),
   `hr doc-check`.
2. `hr transition awaiting_final_approval`.
3. Show: the one-line conclusion; the "read closely" list from the focus block, as rendered; what actually
   changed; the requirement → test → result → evidence table
   (the rendered block); the review findings table from `verification.md`, pasted as rendered, with a
   question for each row that has no outcome yet (remove it, or keep it and why); deviations from the plan;
   remaining risks and anything not run; and the verified commit SHA. Commands:

```
Final approval needed. Verified commit: 3f2a91c0de (8/8 required tests passing)

  approve:         say so in chat, with any residual risk you accept
  point at items:  tell me which row looks wrong
  review findings: for each one, say "remove it" or "keep it" with the reason
  request changes: tell me what to change
```

4. On a change request: `hr reject final --reason "..." --quote "<words>"`, which moves the feature to
   `rework_required`.
   On "keep it" for a review finding: `hr finding accept FND-002 --reason "..." --quote "<words>"`. On
   "remove it": that is a change request. The runtime refuses the approval while a finding has no outcome.
   On approval it moves to `ready_to_merge`.

Final approval is bound to the code tree fingerprint. If the code changes after approval, the runtime
invalidates the approval and moves the feature back to `integrating`. Re-run every required test, then
get re-approval.

## Checking for invalidation

`hr status`, `hr resume` and most other commands re-check approvals when they start. When a line like
"! design approval invalidated" appears, tell the human exactly that and explain what changed.

## Red pill mode: review-vigilance drills

The human approves well only if they read well. With `redpill.enabled`, the runtime draws at random each
time a feature enters `awaiting_design_approval` or `awaiting_final_approval` (about 1 in `redpill.one_in`,
for the gates in `redpill.gates`). On a hit it plants one item that must not be approved in the rendered
approval tables, or leaves one required row out of them. The goal is practice: the human gets better at spotting flaws, and each drill ends with
an explanation of what was wrong.

### What gets planted

| Difficulty | The plant | Found by |
|---|---|---|
| `easy` | an added row that says outright that a check proves nothing or a safeguard is removed | reading the row |
| `normal` | an added or altered row that sounds routine but does not prove what it claims; an assumption nobody agreed to | thinking the row through |
| `hard` | a real row changed or left out: a pass criterion, the requirement a check claims to cover, who made a decision, a dependency, a result, a required check that is missing | comparing it with the requirements, decisions, design, or the rest of the table |

The plant can be in the task table, the verification table, the manual steps, and at the design gate the
decision and assumption tables. The runtime holds each candidate to its label:

- A hard candidate changes or removes a real row and names in `against` the IDs the reviewer has to compare
  it with. An added row cannot be hard, because its new ID stands out. Work nobody asked for is drilled
  at hard by widening the purpose of a real task instead, and the brief shows that case.
- A row that differs from the real one by a number only is accepted once per submission, never as hard,
  and is used only when nothing else fits. A reviewer who learns to scan for numbers has not learned to
  review.
- The way a plant is wrong (a changed criterion, a removed row, an added assumption, ...) is recorded, and
  the next drills use a different one.

A plant that is a missing row is caught by naming the ID that should be there ("TEST-011 is gone").

`redpill.difficulty: adaptive` (the default) starts at easy, moves up after 2 clean catches in a row and down
after 2 misses in a row, counted across all features. A clean catch is one made before any approval was
refused, naming at most `redpill.max_flags` rows. A catch after a refusal, and a catch made by naming more
than `redpill.max_flags` rows at once, are recorded separately. Neither moves the level or counts in the
catch rate.

The plant exists only in the rendered `overview.md` / `verification.md` tables. It is never in the plan
JSON, `requirements.json` or `design.md`, so it can't be executed, and it never affects approval hashes. When the drill ends,
`hr render` restores the real table.

The "read closely" list in `overview.md` (the `hr:focus` block) is built from the task and decision tables as
they are rendered, after the plant is applied, so it never disagrees with them. A planted high-risk task or
medium-risk assumption is listed like a real one. A decision the plant credits to the user is not listed. A
removed task is not listed. The list reads no drill data, so it looks the same in a drilled and an undrilled
render of the same rows.

### Candidates are written for the feature

With `redpill.author: agent` (the default), the plant is not taken from a fixed list. Before each
approval request, while red pill mode is on:

1. `hr redpill brief --gate design|final --json` prints a prompt and the model to use.
2. Spawn `hr-redpill-author` with that prompt. It reads the feature and the code (at the final gate, the
   diff and the recorded test runs), writes candidates that are wrong for this feature specifically (an
   assumption nobody made, a decision contradicted, a check left out, a test that passes while the
   requirement is broken), at all three difficulties, avoiding the kinds of flaw and the ways of being
   wrong used in recent drills, and submits them with `hr redpill seed`.
3. It replies with a count. **Don't read its transcript, its temporary file, or the pool file**, and don't
   ask it what it wrote. A hook denies reading the drill files.

The runtime refuses the approval transition until candidates exist for the current plan. Do this every
time, whether or not a drill will fire: you don't know, and you must not find out. A plan change discards
the candidates. Without sub-agents, the human can set `redpill.author: builtin`, which uses the runtime's
own lists and row alterations.

### During a drill

If the human approves without spotting it, `hr approve` refuses with a scolding and tells them to review
again. They answer in chat:

- They point at the plant (by ID or description): `hr approve <gate> --quote ... --flag <ID>` catches it,
  restores the table, and records the approval in the same step. Spotting it is the review. `hr` prints why
  it was wrong, the real value of an altered row or the row that was left out, and the IDs to compare it
  with. Relay that explanation as is. When they say a row is missing, flag the ID they named.
- They point at a real item: it becomes a review concern and the approval is refused until you address it.
  The drill stays armed.
- They name more than `redpill.max_flags` rows (default 3) in one message and the plant is one of them: the
  plant is removed and `hr` says the drill is not counted, because naming every row finds any plant. The
  other rows are still review concerns. Pass exactly what the human named. Naming several rows for real
  reasons is allowed, and only the count changes.
- They give up ("정답 보여줘"): `hr redpill reveal --quote ...` shows the plant and the explanation, and
  records it as missed.

Your job:

- Behave exactly as without a drill. Never hint, never remove or explain an odd row, and never "fix" it.
- A row may look wrong to you. Say nothing about it unless the human does. If the human asks you whether a
  row is correct, answer from the plan files, as you would for any row.
- If the human mentions an item in chat ("TEST-014 is nonsense"), record it with `--flag` as in
  [Chat decisions](#chat-decisions). Flag what they pointed at, nothing more.
- `hr status` lists `human review flags`. Treat each one as a real review comment: investigate it, and
  change the plan (with re-approval) or explain why it's fine.
- A change request (`hr reject`) ends the drill. The next submission draws again.

### Settings and results

Turning it on and off, the difficulty, the frequency, and `max_flags` are the human's decision. They choose
them during `/hrs:init`, say it in chat, or type `/hrs:redpill on 5 hard`, `/hrs:redpill off`. You run
`hr redpill on [--one-in N] [--difficulty easy|normal|hard|adaptive] [--gates design,final] [--max-flags N] [--reason "<why>"] --quote "<words>"`
or `hr redpill off --reason "<why>" --quote "<words>"`.

`off` refuses to run without `--reason`. The reason is the human's: when they turn drills off without giving
one, ask them once and pass what they say. Never write a reason for them.

Every `on`, `off` and change of a setting is written to `.human-rights/redpill-log.jsonl` and, when a feature
is active, to its event log as `drill_settings_changed`, with who decided, when, how (chat quote or terminal),
the reason, and what changed from and to. A change of frequency, difficulty, gates or `max_flags` is
recorded the same way, because an easier drill weakens the check as much as turning it off does.

`hr redpill status` shows the settings, the current adaptive level, the catch rate per difficulty, and the
kinds of flaw missed most often. Next to the catch rate it shows:

- drills that ended in a catch naming more than `max_flags` rows, which are not counted;
- approvals, how many of them were decided while drills could not run (drills off, or a gate outside
  `redpill.gates`), and how many named at least one row;
- rows named that were not the plant, in total and per approval. Some of those are real concerns. The number
  says how much the human named, not whether they were right;
- how long drills were off, with the reason and the person for each period, and how many times a setting
  changed.

An approval here means an `hr approve` call at the design or final gate that ended in a decision: approved,
or sent back because rows were named. A refusal of a blind approval during a drill is not one.

`hr redpill status` never shows whether a drill is active. `hr metrics` reports the same numbers per
feature (`--all`: for the workspace).
