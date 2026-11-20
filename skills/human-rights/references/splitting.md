# Size and splitting: one feature, or a group of features

A request can be bigger than one feature. "Add login" contains sign-up, log-in, password reset and more. A
120-page specification contains a handful of changes and a lot of background. Planning either as a single
feature produces one approval too large for a human to review. So the first judgment on a request is its
size, and a compound request becomes a **group**: a parent that holds the list of features, the decisions
they share, and the checks of them working together. Each feature then runs the normal workflow.

## The size judgment

A request is **compound** when it contains two or more results that can each be verified on their own and
shipped on their own. It is **single** when its parts only make sense together.

| Signal | Reading |
|---|---|
| A user could use part A while part B does not exist yet | compound |
| The parts have different acceptance criteria and different test scenarios | compound |
| The design approval would cover more than a reviewer can read in one sitting | compound |
| A part cannot be tested without the others | that part is a task, not a feature |
| It is one change that happens to touch many files | single |

When to decide:

- **L0 and L1: skip it.** A typo fix is not asked whether it is one feature.
- **L2 and L3: decide with the classification.** Pass `--size single|compound --size-reason "..."` to
  `hr classify`. The runtime refuses to leave `triaging` or `clarifying` without it.
- **Decide again after clarifying.** The reclassification needs the size too, because answers and code
  findings change it. A feature that grew goes to `splitting` from `clarifying`, `investigating` or `planning`.
- **Obviously compound requests** (a specification document, "build the admin area") don't need axis scores
  first: `hr size compound --reason "..."`, then `hr transition splitting`.

A compound request cannot go on to `planning`. `hr transition splitting` turns the feature into a group:
`FEAT-NNN-slug` becomes `GRP-NNN-slug` and its directory moves to `.human-rights/groups/`. `hr` prints the
new id and path. Use them from then on (the old id still resolves).

## Writing the split

In `splitting`, write `.internal/split.json` and the group's `.internal/test-plan.json`, then
`hr scaffold` (it creates the group `overview.md`) and fill in the prose.

```json
{
  "summary": "Account access for the web app",
  "source": {"kind": "request"},
  "children": [
    {"key": "signup", "title": "Sign up",
     "outcome": "A visitor can create an account with email and password",
     "verify_alone": "API test: POST /signup creates a user and rejects a duplicate email",
     "depends_on": [], "expected_mode": "L2"},
    {"key": "login", "title": "Log in",
     "outcome": "A registered user can log in and stay logged in",
     "verify_alone": "API test: POST /login returns a session; a wrong password is rejected",
     "depends_on": ["signup"], "expected_mode": "L2"}
  ],
  "shared_decisions": [
    {"id": "GDEC-001", "question": "How is a session kept?", "answer": "Server-side session cookie",
     "decided_by": "user"}
  ],
  "excluded": [
    {"item": "Social login", "reason": "Not requested for this release"}
  ]
}
```

Rules, enforced by `hr split-check`:

- **At least two features**, each with a `key`, a `title`, an `outcome` (what someone can use when this
  feature alone is done) and `verify_alone` (how it is verified without the others). A part with no
  `verify_alone` belongs inside another feature as a task.
- **`depends_on`** names the features that must be completed first. No cycles.
- **`shared_decisions`** holds what applies to more than one feature: the session model, the storage
  format, a naming rule. Ask the human these once, here. A changed answer uses `overrides_user_answer` and
  `reason`, as in `requirements.json`. The key must be present even when the list is empty.
- **`excluded`** lists what the request mentions but this group will not build, each with a reason. The key
  must be present. It is how the human sees what was dropped.
- **The group test plan** needs at least one required test, and at least one required test must name two
  or more features in `children`. Features that each pass can still fail when joined, and this is the only
  place that is caught. Tests follow the same rules as any plan: a runner, steps with `do` and `expect`
  for agent and human tests, a `human_reason` for human tests.
- **Size the features for review.** One feature should be approvable in one sitting. Fold a part expected
  to be L0 or L1 into a neighbour. If the list passes about a dozen, group related features: a child may
  itself turn out compound and split again when it starts.

### When the request is a document

Set `"source": {"kind": "document", "path": "<file>", "unread": [...]}` and follow three more rules:

1. **Trace both ways.** Every feature lists its `sources` (pages or sections). Everything in the document
   that is not a requirement (background, test results, comparisons, references) goes into `excluded` with
   its pages and the reason, so no part of the document is silently dropped.
2. **Compare with the code first.** Use `hr-investigator` to set each feature's `code_status`: `missing`,
   `partial`, `conflict`, or `exists`. Something that already `exists` is not a feature: move it to
   `excluded` with the evidence.
3. **Say what you could not read.** A formula or a diagram that is an image is not in the extracted
   text. List each such part in `source.unread` with the reason. The overview shows them under a warning
   for the human to check. Never fill the gap by guessing.

Numbers the document fixes (thresholds, ranges, defaults) become shared decisions or go to the feature that
uses them, and its measured results become pass criteria. That replaces clarifying questions the document
already answers.

## Approval

1. `hr split-check` with zero hard fails, `hr doc-check`, and `hr-plan-reviewer` on the group directory.
2. `hr transition awaiting_split_approval`, `hr render`, then show the group `overview.md`: the feature
   table and order, the shared decisions, what is left out, the unread parts, and the group checks.
3. The human answers in chat. Approval: `hr approve split --quote "<their words>"`. A request to drop,
   merge, add or reorder: `hr reject split --reason "..." --quote "<their words>"`, change `split.json`, ask
   again. The scope of the work is the human's decision.

Approval creates one feature per entry, in state `proposed`, inside the group's own `features/`
directory, and the group moves to `delivering`. The group overview links to each feature's `overview.md`
once that file exists.

## Delivering

- `hr start -f <group>` starts the next feature whose dependencies are completed and prints its brief: the
  outcome, how it is verified alone, its sources, and the shared decisions.
- Copy the shared decisions into the feature's `requirements.json` with `decided_by: "group"`. Don't ask
  them again.
- The feature then runs the normal workflow from §3: probe, classify (including its own size), and its own
  approvals. Its tests must include what `verify_alone` promised. A feature judged compound becomes a group
  inside its parent (`groups/<GRP-id>/groups/<GRP-id>/`).
- One feature at a time by default (`groups.max_active_children`). The human's review is the bottleneck,
  so opening several only queues approvals.
- When a feature completes, `hr` says what is next. `hr list` shows the tree.
- If the list has to change (a new feature, a dropped one, a different order), edit `split.json`. The
  runtime invalidates the split approval and moves the group back to `splitting`; ask for approval again.
  Waiting features that were removed are cancelled; a started one must be aborted explicitly first.

## Finishing the group

When every feature is completed or cancelled: `hr transition integrating -f <group>`, run the group checks
(`hr verify -f <group>`, agent tests through `hr-tester`, then human tests), and
`hr transition completed -f <group>`. The results must be valid for the current commit, as for any
feature. A failing group check means a defect between features: record what broke, add a fix feature to
`split.json`, and get the changed list approved.
