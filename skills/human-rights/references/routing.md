# Adaptive Router: classification criteria

Classify after the probe. For each axis give `score` (0-3), `basis` (the evidence, with paths and symbols
where possible), `confirmed` (did you verify it in code or with the user?) and `confidence`
(low/medium/high). **The runtime adds 1 to any unconfirmed low-confidence axis**, so that ambiguity never
makes a change look safer than it is. If you are sure, confirm it and send `confirmed: true`.

## Axes

| Axis (`key`) | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| Intent ambiguity `ambiguity` | behaviour and scope clear | only wording/details open | some behaviour/scope open, a default can be proposed | core operating policy undecided |
| Change scope `scope` | one file/component | several files in one module | several modules | crosses system boundaries (process, service, device) |
| Architecture impact `architecture` | existing pattern as is | small new function/component | new module or shared-interface extension | core interface / data model change |
| Risk `risk` | small, reversible impact | user inconvenience | possible data corruption or security exposure | serious safety, security or integrity risk |
| Verification difficulty `verification` | easy to check automatically | needs a targeted test | needs an integration environment or manual check | depends on hardware/time, hard to observe |
| Dependency complexity `dependency` | independent | one prerequisite | several ordered tasks | cross-dependencies, external teams/systems |

## Mode rules (enforced by the runtime; not a score total)

- **L3**: `risk` >= 3, or `architecture` >= 3, or four or more axes >= 2, or any safety flag.
- **L2**: any of `scope`, `architecture`, `risk`, `dependency`, `ambiguity` >= 2, or any approval flag.
- **L1**: any axis at 1.
- **L0**: every axis 0.

Gates: L2 and L3 require design approval, and L3 also final approval (`routing.design_gate_modes` / `final_gate_modes` in
`config.yaml`). L2 requires design approval when `architecture` >= 2. Flags force gates as below.

## Flags (`--flags`, comma-separated)

| Flag | When | Effect |
|---|---|---|
| `physical_safety` | affects physical safety of people or equipment | L3 + design and final approval (never released) |
| `vehicle_command` | changes vehicle command targeting or flight control | L3 + design and final approval (never released) |
| `auth` | authentication / authorization logic | approval required, at least L2 (L3 if `risk` = 3) |
| `secrets` | creating, storing or transmitting secrets | same |
| `destructive_migration` | data deletion, irreversible schema change | same |
| `irreversible_external` | payments, sending email, external deploys, other irreversible external actions | same |

Add a flag when in doubt. Once a flag gate has triggered, the runtime keeps it across reclassification
(sticky).

## Floor: paths the owner always gates

The axes are your estimate, so an under-scored change would go through ungated. The owner can list paths that
always need at least a given level in `.human-rights/floor.yaml`:

```yaml
"migrations/**": L2
"src/auth/**": L3
```

- The runtime applies the floor after scoring and after the flags. It raises the mode to the highest matching
  level and never lowers it. You cannot skip it or score around it. The raise is recorded: the classify output,
  `state.json` (`routing.floor`) and the `classified` event say which rule fired, on which paths, and the
  level it was raised from.
- A rule matches a path when the glob matches (`*` also crosses `/`), when the path is the rule's directory,
  or when the path is inside it. `**/secrets/*` does not match a top-level `secrets/x`, so the owner lists both.
- The paths checked are the union of: the files you declare with `--paths` (the files you expect to touch,
  known before any edit), every file changed between the commit the feature started from and HEAD, and every
  uncommitted or untracked file. Declared paths cover L0 before the change exists. The real diff covers what
  you did not expect to touch.
- The raise follows the normal gates. A floor of L2 adds the design gate, and L3 adds both.
- Guard: from `executing` onward (`executing`, `verifying_tasks`, `integrating`, `awaiting_final_approval`,
  `ready_to_merge`, `completed`), a transition is refused with `[floor]` when the declared paths or the diff hit
  a rule above the feature's mode. Run `hr classify` again with `--paths` and the floor raises the mode. If that
  adds a design gate after execution started, the next transition is refused until the design is approved:
  go back through `clarifying` or `rework_required -> planning`.
- Only the owner changes the floor. Edit the file yourself, or run `hr floor add|remove`, which is a human
  decision (`--quote`). A hook denies the agent's edits to `floor.yaml`. See [config](config.md#floor).

## Examples

- "Center the login card." The probe shows only `LoginCard.css` is involved and no shared layout, so
  every axis is 0: **L0**. If the card uses a shared `AuthLayout`, `scope` = 1: L1.
- "Add input error hints." The validation logic is located and needs a targeted test, so
  `verification` = 1: **L1**.
- "Add social login." `auth` flag, a new OAuth callback module (`architecture` = 2): **L2, approval required**.
- "Connect several drones to the GCS at once and control each one by selecting it." `vehicle_command`,
  connection model change (`architecture` = 3): **L3**.

## Input format

Write the axes to a file (or pipe them on stdin with `--axes -`):

```json
{
  "ambiguity":    {"score": 3, "basis": "max vehicles and policy for deselected vehicles undecided", "confirmed": false, "confidence": "high"},
  "scope":        {"score": 3, "basis": "src/link, src/command, src/ui", "confirmed": true, "confidence": "high"},
  "architecture": {"score": 3, "basis": "global single connection src/link/conn.py:12 -> per-vehicle sessions", "confirmed": true, "confidence": "high"},
  "risk":         {"score": 3, "basis": "a wrong command target flies the wrong vehicle", "confirmed": true, "confidence": "high"},
  "verification": {"score": 2, "basis": "needs several SITL instances", "confirmed": false, "confidence": "medium"},
  "dependency":   {"score": 2, "basis": "registry -> router -> UI order", "confirmed": true, "confidence": "medium"}
}
```

```bash
.human-rights/hr classify --flags vehicle_command --axes @.human-rights/features/FEAT-001-multi-drone/details/axes.json
```

## Size: one feature or several

For L2 and L3, the classification also records whether the request is one feature:

```bash
.human-rights/hr classify --axes @axes.json --size single --size-reason "one endpoint and its screen"
.human-rights/hr classify --axes @axes.json --size compound --size-reason "sign-up, log-in and reset ship separately"
```

`compound` means two or more results that can each be verified and shipped on their own. The runtime
refuses to leave `triaging` or `clarifying` at L2/L3 without a size, and refuses to plan a compound
request as one feature. L0 and L1 skip the decision. Criteria and the group workflow:
[splitting](splitting.md).

## Reclassification

Run `hr classify` again (with all axes) as soon as you find: a wider scope after exploring, a public
contract change, an unexpected dependency, or a major verification failure.

**Always reclassify when clarifying ends, and decide the size again.** The user's answers usually lower `ambiguity` (a decided policy is
no longer ambiguous: score it by what is *still* open), and they can also change `scope`, `risk`, or
`verification` (for example "only the monitor tab" narrows scope). Update each axis's `basis` to cite the
answers. The runtime refuses to leave `clarifying` until a classification newer than entering it exists.

Moving to a lower mode is allowed, but safety-related approval requirements that already triggered stay.
Tell the user the new classification and why in one line.
