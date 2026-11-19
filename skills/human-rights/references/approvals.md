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
| toggles drills ("레드필 켜줘, 5번에 한 번") | `hr redpill on --one-in 5 --quote "<words>"` / `hr redpill off --quote "<words>"` |

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
- A human can still run any of these themselves with `! .human-rights/hr ... --by <name>`. Hosts without a
  prompt hook need that path. See [host-adapters](host-adapters.md).

## Requesting design approval (`awaiting_design_approval`)

1. Pass `hr plan-check`, apply the independent review, run `hr render`, and pass `hr doc-check`.
2. `hr transition awaiting_design_approval`.
3. Show the human (1-2 screens, based on `overview.md`), in this order:
   - the one-line conclusion: what changes and why
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

Precondition: all code is committed, every required test passed **on the current commit**, and no
failures are unresolved (see [integration.md](integration.md)).

1. `hr render`, update `overview.md` into the final-report shape (structure of `review-report.md`),
   `hr doc-check`.
2. `hr transition awaiting_final_approval`.
3. Show: the one-line conclusion; what actually changed; the requirement → test → result → evidence table
   (the rendered block); deviations from the plan; remaining risks and anything not run; and the verified
   commit SHA. Commands:

```
Final approval needed. Verified commit: 3f2a91c0de (8/8 required tests passing)

  approve:         say so in chat, with any residual risk you accept
  point at items:  tell me which row looks wrong
  request changes: tell me what to change
```

4. On a change request: `hr reject final --reason "..." --quote "<words>"`, which moves the feature to
   `rework_required`.
   On approval it moves to `ready_to_merge`.

Final approval is bound to the code tree fingerprint. If the code changes after approval, the runtime
invalidates the approval and moves the feature back to `integrating`. Re-run every required test, then
get re-approval.

## Checking for invalidation

`hr status`, `hr resume` and most other commands re-check approvals when they start. When a line like
"! design approval invalidated" appears, tell the human exactly that and explain what changed.

## Red pill mode: review-vigilance drills

When `redpill.enabled` is on, the runtime rolls a die each time a feature enters `awaiting_design_approval` or
`awaiting_final_approval` (about 1 in `redpill.one_in`, for the gates in `redpill.gates`). On a hit, it plants one
plausible but unacceptable item in the rendered approval tables:

- design gate: a verification row whose method proves nothing (exit code ignored, the component under
  test is mocked, "looks fine locally", grepping a log), or a plan row that should never be approved
  (disable validation, swallow errors, skip a slow test, copy instead of change);
- final gate: a result row with a pass that isn't evidence (verified manually by the agent with no log,
  skipped as flaky, ran on the previous commit, assumed unchanged).

The plant exists only in the rendered `overview.md` / `verification.md` tables. It is never in the plan
JSON or `design.md`, so it can't be executed, and it never affects approval hashes.

If the human approves without spotting it, `hr approve` refuses with a scolding and tells them to review
again. They answer in chat:

- They point at the plant (by ID or description): `hr approve <gate> --quote ... --flag <ID>` catches it,
  removes the row, and records the approval in the same step. Spotting it is the review.
- They point at a real item: it becomes a review concern and the approval is refused until you address it.
  The drill stays armed.
- They give up ("정답 보여줘"): `hr redpill reveal --quote ...` shows the plant and records it as missed.

Your job during a drill:

- Behave exactly as without one. Never read `.internal/redpill.json`, never hint, never remove or explain the
  odd row, and never "fix" it.
- If the human mentions an item in chat ("TEST-014 is nonsense"), record it with `--flag` as in
  [Chat decisions](#chat-decisions). Flag what they pointed at, nothing more.
- `hr status` lists `human review flags`. Treat each one as a real review comment: investigate it, and
  change the plan (with re-approval) or explain why it's fine.
- A change request (`hr reject`) ends the drill. The next submission rolls again.
- `hr metrics` reports drills, catches, misses, and refused rubber-stamp approvals per feature.

Turning it on and off, and the frequency, are the human's decision. They say it in chat or type
`/hrs:redpill on 10`, `/hrs:redpill off`. You run
`hr redpill on --one-in 10 [--gates design,final] [--language en|ko] --quote "<words>"` or
`hr redpill off --quote "<words>"`.
`hr redpill status` shows the settings and results, never whether a drill is active.
