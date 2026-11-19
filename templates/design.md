# Design — [FILL: feature name]

## Conclusion
[FILL: the recommended approach in one sentence, plus the key reason]

## Structure and interfaces
[FILL: modules, interfaces and state transitions that change, as behaviour a reviewer can judge. No code expressions here: those belong in the task documents. Link evidence in details/codebase.md]

## Flow
[FILL: draw what changes. Required when the change crosses a module or process boundary or any task changes a flow: a sequence diagram for calls across boundaries, a state diagram for changed states, or a before/after component diagram. Otherwise replace this section's body with one line: "No diagram: single module, no interaction changes."]

```mermaid
sequenceDiagram
  participant A as [FILL: caller]
  participant B as [FILL: callee]
  A->>B: [FILL: what is sent]
```

## Alternatives
| Option | Change scope | Risk | Maintainability | Verifiability | New dependencies |
|---|---|---|---|---|---|
| **A (recommended)** [FILL] | | | | | |
| B [FILL] | | | | | |

If there is only one real option, replace the table with one line: "No alternative: [reason]".

## Tasks
<!-- hr:tasks:start -->
<!-- hr:tasks:end -->

## Remaining uncertainty
[FILL: what is still Unknown and how it could affect the result; 'none' if none]

## Decisions needed before implementation
[FILL: 'none' if none]
