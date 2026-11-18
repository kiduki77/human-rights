from __future__ import annotations

from typing import Any, Dict, List

from runtime.common import HRError

AXES = ("ambiguity", "scope", "architecture", "risk", "verification", "dependency")
AXIS_LABELS = {
    "ambiguity": "intent ambiguity",
    "scope": "change scope",
    "architecture": "architecture impact",
    "risk": "risk",
    "verification": "verification difficulty",
    "dependency": "dependency complexity",
}
MODES = ("L0", "L1", "L2", "L3")

SAFETY_FLAGS = {
    "physical_safety": "physical safety impact",
    "vehicle_command": "vehicle command targeting / flight control change",
}
APPROVAL_FLAGS = {
    "auth": "authentication / authorization change",
    "secrets": "secret handling",
    "destructive_migration": "destructive data migration",
    "irreversible_external": "irreversible external action",
}
ALL_FLAGS = {**SAFETY_FLAGS, **APPROVAL_FLAGS}


def _effective(axis: Dict[str, Any]) -> int:
    score = int(axis["score"])
    if not axis.get("confirmed") and axis.get("confidence", "low") == "low":
        score = min(3, score + 1)
    return score


def validate_axes(axes: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    missing = [a for a in AXES if a not in axes]
    if missing:
        raise HRError(f"missing axes: {', '.join(missing)}")
    out = {}
    for name in AXES:
        ax = axes[name]
        if isinstance(ax, int):
            ax = {"score": ax}
        if not isinstance(ax, dict) or "score" not in ax:
            raise HRError(f"axis {name}: must be {{score, basis, confirmed, confidence}}")
        if int(ax["score"]) not in (0, 1, 2, 3):
            raise HRError(f"axis {name}: score must be 0..3")
        if not ax.get("basis"):
            raise HRError(f"axis {name}: basis (evidence for the estimate) is required")
        conf = ax.get("confidence", "low")
        if conf not in ("low", "medium", "high"):
            raise HRError(f"axis {name}: confidence must be low|medium|high")
        out[name] = {
            "score": int(ax["score"]),
            "basis": str(ax["basis"]),
            "confirmed": bool(ax.get("confirmed", False)),
            "confidence": conf,
        }
    return out


def route(axes: Dict[str, Any], flags: List[str], config: Dict[str, Any]) -> Dict[str, Any]:
    axes = validate_axes(axes)
    unknown = [f for f in flags if f not in ALL_FLAGS]
    if unknown:
        raise HRError(f"unknown flags: {', '.join(unknown)} (allowed: {', '.join(ALL_FLAGS)})")

    eff = {k: _effective(v) for k, v in axes.items()}
    reasons: List[str] = []
    high = [k for k, v in eff.items() if v >= 2]

    if eff["risk"] >= 3 or eff["architecture"] >= 3 or len(high) >= 4:
        mode = "L3"
        reasons.append(f"high-risk / core-structure axes: {', '.join(AXIS_LABELS[k] for k in high) or '-'}")
    elif any(eff[k] >= 2 for k in ("scope", "architecture", "risk", "dependency", "ambiguity")):
        mode = "L2"
        reasons.append(f"axes >= 2: {', '.join(AXIS_LABELS[k] for k in high)}")
    elif any(v >= 1 for v in eff.values()):
        mode = "L1"
        reasons.append("some axes at 1: short plan + targeted verification")
    else:
        mode = "L0"
        reasons.append("all axes 0: direct change")

    gates: List[Dict[str, Any]] = []
    safety = [f for f in flags if f in SAFETY_FLAGS]
    approval = [f for f in flags if f in APPROVAL_FLAGS]
    if safety:
        mode = "L3"
        for f in safety:
            gates.append({"gate": "design", "reason": SAFETY_FLAGS[f], "sticky": True, "flag": f})
            gates.append({"gate": "final", "reason": SAFETY_FLAGS[f], "sticky": True, "flag": f})
    if approval:
        if MODES.index(mode) < MODES.index("L2"):
            mode = "L2"
        if eff["risk"] >= 3:
            mode = "L3"
        for f in approval:
            gates.append({"gate": "design", "reason": APPROVAL_FLAGS[f], "sticky": True, "flag": f})
            gates.append({"gate": "final", "reason": APPROVAL_FLAGS[f], "sticky": True, "flag": f})

    rc = config.get("routing", {})
    if mode in (rc.get("design_gate_modes") or []):
        gates.append({"gate": "design", "reason": f"{mode} policy", "sticky": False})
    if mode in (rc.get("final_gate_modes") or []):
        gates.append({"gate": "final", "reason": f"{mode} policy", "sticky": False})
    if mode == "L2" and eff["architecture"] >= int(rc.get("l2_design_gate_min_arch", 2)):
        gates.append({"gate": "design", "reason": "L2 architecture change", "sticky": False})

    return {
        "mode": mode,
        "axes": axes,
        "effective_scores": eff,
        "flags": sorted(set(flags)),
        "gates": gates,
        "reasons": reasons,
    }


def apply_route(state: Dict[str, Any], result: Dict[str, Any], ts: str) -> List[str]:
    notes = []
    prev_mode = state.get("mode")
    kept_sticky = [g for g in state.get("gate_reasons", []) if g.get("sticky")]
    merged = kept_sticky + [g for g in result["gates"] if g not in kept_sticky]
    state["gate_reasons"] = merged
    state["required_gates"] = {
        "design": any(g["gate"] == "design" for g in merged),
        "final": any(g["gate"] == "final" for g in merged),
    }
    mode = result["mode"]
    if kept_sticky and any(g.get("flag") in SAFETY_FLAGS for g in kept_sticky) and mode != "L3":
        notes.append("A safety flag was already triggered; staying at L3 (never auto-released).")
        mode = "L3"
    state["mode"] = mode
    state["routing"] = {k: result[k] for k in ("axes", "effective_scores", "flags", "reasons")}
    state["routing"]["classified_at"] = ts
    if prev_mode != mode:
        state.setdefault("mode_history", []).append({"from": prev_mode, "to": mode, "at": ts})
        if prev_mode:
            notes.append(f"reclassified: {prev_mode} -> {mode}")
    return notes
