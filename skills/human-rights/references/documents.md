# Human-facing documents: readability standard

Documents exist so a human can decide quickly. Measure their quality by how long a real human review takes
and how often the reviewer has to ask again, not by how thorough they look.

## First screen of every report

1. A one-sentence conclusion and the current state
2. What changes and why
3. The key design or change, with a diagram when it crosses a boundary
4. Verification results and anything unverified
5. **The decision the human must make**, and the next step

## Writing rules

- Conclusion first. Short paragraphs, meaningful headings, tables for comparisons.
- Never fill the body with raw logs, file lists, or call graphs. Put detailed evidence in `details/` and link it.
- Don't cut real content to make a long document shorter. Split it into a **summary plus detailed references**.
- L0: a 5-10 line change summary (`templates/l0-summary.md`) is enough.
- L3 approval `overview.md`: aim for 1-2 screens, but never drop safety-relevant information.
- Every code path, verification result, and design choice you mention must link to real evidence.
- **Draw what changes.** `design.md` needs a Mermaid diagram when the change crosses a module or process
  boundary or any task has `changes_flow: true`, and each such task document needs its own. Show only the
  participants and messages that change, mark what is new, and keep it under about a dozen arrows. Don't
  add a diagram to a single-component change. `hr doc-check` enforces presence and basic syntax.
- **Words, not bare IDs.** "Check DEC-001 to DEC-005" makes the reader open another file. The
  `<!-- hr:decisions -->` block already lists every decision and assumption; in prose, say the thing.
- **An answer you changed goes first.** If investigation forces a different value from what the user
  answered, record the decision with `overrides_user_answer` and `reason`. The decisions block shows it at
  the top under a warning. Never leave it in a parenthesis.
- **Review material is behaviour.** Keep code expressions out of `overview.md` and `design.md`.
- Never type result, step, or decision tables by hand. Keep the `<!-- hr:status -->`, `<!-- hr:tasks -->`,
  `<!-- hr:results -->`, `<!-- hr:steps -->` and `<!-- hr:decisions -->` blocks from the templates and run
  `hr render`. The results table shows, per test, who runs it, its pass criteria, and its estimated time.
- Write in `docs.language` (config), or in the user's language if they ask. Keep IDs, commands and markers as is.

## Templates

`hr scaffold` creates documents from templates: the repo's `.human-rights/templates/` first, then the plugin's.
`hr scaffold tasks` pre-fills every `tasks/TASK-NNN.md` from `task-graph.json`. A team standardizes its
reports by installing a template pack once (`hr templates install [--from <org-pack-dir>]`) and committing
`.human-rights/templates/`. `hr templates status` shows which files were customized locally and which are
behind the pack. `hr templates update` refreshes only files that weren't customized.

## Where things go

| Document | Audience | Content |
|---|---|---|
| `overview.md` | the approver | goal, state, decisions, next action |
| `requirements.md` | the approver | intent, scope, acceptance criteria, decisions, open items |
| `design.md` | the approver / reviewer | key design, alternatives, task DAG, uncertainty |
| `verification.md` | the approver / QA | test plan, results, residual risk |
| `tasks/TASK-NNN.md` | the reviewer | task purpose, boundary, verification, result |
| `details/*.md` | anyone who needs to dig | code evidence, research, diagrams |

## Document quality gate

1. `hr doc-check` (structural): required `hr:*` blocks present, minimum number of sections, no `[FILL: ...]`
   placeholders, no broken relative links, valid Mermaid openings and balanced brackets, a diagram where one is required, no raw-log dumps,
   and length budgets for L0/L1/overview. The check is language-agnostic.
2. Independent review (`hr-plan-reviewer`) for approval documents: clarity, duplication, actionability,
   and whether the text matches the evidence.
