# Human approval: design gate and final gate

An approval exists only when a human runs `hr approve` themselves. "Approved", "looks good" or "go ahead"
in chat is not an approval event. If the agent tries to run `hr approve`, a hook blocks it. These records
are not a security boundary. Real merge control comes from GitHub branch protection.

## Requesting design approval (`awaiting_design_approval`)

1. Pass `hr plan-check`, apply the independent review, run `hr render`, and pass `hr doc-check`.
2. `hr transition awaiting_design_approval`.
3. Show the human (1-2 screens, based on `overview.md`):
   - the one-line conclusion: what changes and why
   - confirmed decisions (especially safety-related ones) and proposed defaults
   - the recommended design, with a one-line comparison to the alternatives
   - the task DAG table and the integration test plan (what has to pass for this to be done), pasted
     verbatim from the rendered tables in `overview.md` (never rebuilt from the JSON)
   - remaining risks and unknowns
   - the decision you need, with the exact commands:

```
Design approval needed. Review: .workflow/features/FEAT-001-multi-drone/overview.md

  approve:         ! .workflow/hr approve design --by <name>
  request changes: tell me in chat what to change (requirements, design, or test plan)
  hold:            do nothing; nothing gets implemented before approval
```

4. On a change request, record it with
   `hr reject design --reason "<summary>" [--to clarifying|planning|investigating]` and go back to that
   stage. On approval, the runtime moves the feature to `executing`. Confirm with `hr status`, then continue.

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

  approve:         ! .workflow/hr approve final --by <name> [--risks "<residual risk you accept>"]
  request changes: tell me in chat
```

4. On a change request: `hr reject final --reason "..."`, which moves the feature to `rework_required`.
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
again. Their options:

```
! .workflow/hr flag <ID> --by <name> [--note "why"]   # the plant: drill passed, row removed, approve again
                                                      # a real item: recorded as a review concern for you
! .workflow/hr redpill reveal --by <name>                 # give up: shows the plant, recorded as missed
```

Your job during a drill:

- Behave exactly as without one. Never read `.internal/redpill.json`, never hint, never remove or explain the
  odd row, and never "fix" it.
- If the human mentions an item in chat ("TEST-014 is nonsense"), give them the `flag` command for that ID.
  Don't run it yourself. It is human-only, and the hook blocks it.
- `hr status` lists `human review flags`. Treat each one as a real review comment: investigate it, and
  change the plan (with re-approval) or explain why it's fine.
- A change request (`hr reject`) ends the drill. The next submission rolls again.
- `hr metrics` reports drills, catches, misses, and refused rubber-stamp approvals per feature.

Turning it on and off, and the frequency, are the human's decision:
`! .workflow/hr redpill on --one-in 10 [--gates design,final] [--language en|ko]`, `! .workflow/hr redpill off`.
`hr redpill status` shows the settings and results, never whether a drill is active.
