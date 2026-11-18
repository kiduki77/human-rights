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
