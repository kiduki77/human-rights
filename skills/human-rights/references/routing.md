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

Gates: L3 always requires design and final approval (`routing.design_gate_modes` / `final_gate_modes` in
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
.workflow/hr classify --flags vehicle_command --axes @.workflow/features/FEAT-001-multi-drone/details/axes.json
```

## Reclassification

Run `hr classify` again (with all axes) as soon as you find: a wider scope after exploring, a public
contract change, an unexpected dependency, or a major verification failure.

Moving to a lower mode is allowed, but safety-related approval requirements that already triggered stay.
Tell the user the new classification and why in one line.
