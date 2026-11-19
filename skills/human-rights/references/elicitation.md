# Intent elicitation

Goal: resolve, by asking, only the undecided user decisions that change what gets built. Before asking,
check what the code can already tell you.

## Procedure

1. From the request, extract the **goal, observable behaviour, boundary conditions, and forbidden behaviour**.
2. Check the facts in the existing code. Don't ask about conventions it already settles (libraries,
   error handling, naming); present them as **proposed defaults** instead.
3. For each candidate question, ask: "Does the answer change the architecture, an API contract, a safety
   policy, or the acceptance criteria?" If not, drop it or turn it into a default.
4. Ask **3-5 key questions** at a time. Give each one options, a recommended default, and one line on what
   the choice changes. If the host has a question UI (for example `AskUserQuestion` in Claude Code), use it.
5. Record each answer in `requirements.json` `decisions` (`decided_by: "user"`) and set the question to
   `status: "answered"`. Ask follow-ups only about issues the answers raised.
6. End every round with three groups: `confirmed decisions / proposed defaults / still open`.

## Example question round

```
These 3 decisions change the design. Everything else proceeds with defaults.

1. Max simultaneous vehicles: 2 / 4 (recommended: the current UI is a 4-pane layout) / unlimited
   -> changes the connection registry size and the UI layout.
2. A vehicle that gets deselected: keeps its mission (recommended) / switches to LOITER
   -> safety policy. I won't implement without an answer.
3. Switching target while a command is in flight: after the ACK (recommended) / immediately
   -> changes the command router's state transitions.

Proposed defaults: keep the existing MAVLink library; show a toast when a 5th vehicle tries to connect.
```

## Rules for `requirements.json`

- Mark safety-related decisions `safety: true`. **A `safety: true` decision must have `decided_by: "user"`**;
  otherwise plan-check hard-fails.
- An unanswered question that affects the design is `blocking: true`; a safety-related one is
  `safety: true`. While any remain open, the runtime refuses to enter implementation.
- Give every `must` requirement verifiable acceptance criteria (`acceptance`). "Works well" is not a
  criterion. Take quantitative thresholds (counts, latency, time) only from the user's answers or from a
  design decision with stated evidence.
- Bump `revision` on every change. Changing it after design approval invalidates the approval; that is
  intended.
- `requirements.md` is the readable form of this JSON. Note the same revision in it.

## Requirements readiness gate

Move on to `investigating` / `planning` only when all of these hold:

- [ ] You can state the problem being solved, who it is for, and what is in and out of scope.
- [ ] The normal, failure and edge-case behaviours that matter for this feature are defined.
- [ ] Questions and conflicts with major design impact are resolved.
- [ ] Every must requirement has verifiable acceptance criteria.
- [ ] Remaining assumptions are low-risk, recorded in `assumptions`, and visible to the user.
- [ ] Core safety-related policies are settled by user decision. Otherwise, **do not implement**.

Don't end elicitation because of a question count or your own confidence score.

When the gate passes, re-score the axes with the answers (`ambiguity` by what is still open, plus any axis
the answers narrowed or widened) and run `hr classify` before `hr transition`. Tell the user the new mode and
gates in one line. A drop from L3 to L2 can remove the design and final gates unless a flag or
`routing.*_gate_modes` keeps them.
