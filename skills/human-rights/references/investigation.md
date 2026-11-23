# Codebase investigation and implementation research

## Code investigation (`investigating`)

Never settle a design without investigating. Cover only what is needed, but back every claim with evidence.

- Relevant files, symbols, call paths, state and data flow.
- Reusable modules and existing tests, including the command that runs them. That command goes straight
  into the test plan.
- Change impact, compatibility, concurrency, performance, security and safety constraints.
- Label each finding:
  - **Verified**: confirmed by reading or running code (`src/link/conn.py:40-88`, command output).
  - **Inferred**: guessed from names or structure. If the design relies on it, mark it as a risk.
  - **Unknown**: could not be confirmed. If it drives a design decision, turn it into a question or a test.

Put the results in a table in `details/codebase.md` (template `details-codebase.md`). The design document
gets only a 3-5 line conclusion and a link.

When the investigation is broad in L2/L3, delegate it to the `hr-investigator` sub-agent. Give it the
goal, what you already know, and the questions it must answer. Before promoting a returned claim to
Verified, re-check yourself any claim the design depends on.

If the investigation reveals a wider scope, a contract change, or a hidden dependency, reclassify with
`hr classify`.

### Impact: other places that use it

For L2 and L3, write what the probe started into `requirements.json` as `impact`. The plan check refuses a
plan without it, and `hr render` shows it as a table in `design.md` and `overview.md`, so the human approves
it with the design.

```json
"impact": {
  "concept": "the waypoint's display number",
  "searched": ["waypoint", "sequence", "displayNumber", "order"],
  "consumers": [
    {"id": "IMP-001", "where": "src/ui/MapMarker.tsx", "uses": "draws the number on the pin",
     "relation": "change", "tasks": ["TASK-001"], "evidence": "src/ui/MapMarker.tsx:40-52"},
    {"id": "IMP-002", "where": "src/ui/AltitudeCard.tsx", "uses": "labels each row with the number",
     "relation": "change", "tasks": ["TASK-002"], "evidence": "src/ui/AltitudeCard.tsx:18-31"},
    {"id": "IMP-003", "where": "src/mission/store.ts", "uses": "saves the order",
     "relation": "check", "tests": ["TEST-012"], "evidence": "src/mission/store.ts:60-88"},
    {"id": "IMP-004", "where": "src/link/upload.ts", "uses": "sends the MAVLink sequence",
     "relation": "unrelated", "reason": "uses the protocol sequence, not the display number",
     "evidence": "src/link/upload.ts:22-40"}
  ]
}
```

- `change`: this place is edited. Name the task (`tasks`).
- `check`: this place is not edited but must still work. Name a test that would show it broke (`tests`). A
  static check does not count. If no test exists, add one to the plan.
- `unrelated`: found by the search and not affected. Say why (`reason`). Listing it shows the human that you
  looked and decided, which they can disagree with.
- Every row needs `evidence`. A row you could not confirm is Inferred: say so in `uses`, and treat it as
  `check`.
- A search that found nothing is a valid result: `"consumers": []`, with the terms you searched for.
- When several places must agree ("the map and the altitude card show the same number for the same
  waypoint"), write that rule as a requirement with acceptance criteria, and give it a test that looks at
  both places at once.

## Implementation alternatives (early `planning`)

- The default choice is **the smallest safe change to the existing structure**. Don't favour introducing
  new technology.
- Compare two or more alternatives only when real design alternatives exist. Don't invent straw men. If
  there is only one, write "no alternative: <reason>".
- For each alternative: change scope, risk, maintainability, verifiability, new dependencies.
- For external libraries and standards, check the **version actually in use** and its compatibility (lock
  files, official docs). If you can't check, mark it Unknown.
- State the recommendation together with its rationale and the remaining uncertainty.

Output: the "Alternatives" table in `design.md`; details in `details/research.md`.
