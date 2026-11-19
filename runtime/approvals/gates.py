from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from runtime.common import GateError, HRError, canonical, fingerprint, now, sha256_bytes
from runtime.state.store import Feature

TASK_RUNTIME_FIELDS = ("status", "verified_evidence", "notes", "github")


def _plan_view(graph: Dict[str, Any]) -> Dict[str, Any]:
    tasks = []
    for t in graph.get("tasks", []):
        tasks.append({k: v for k, v in t.items() if k not in TASK_RUNTIME_FIELDS})
    return {"tasks": sorted(tasks, key=lambda t: t.get("id", ""))}


GENERATED_BLOCK_RE = re.compile(r"<!-- hr:([a-z]+):start -->.*?<!-- hr:\1:end -->", re.S)


def _authored_text_hash(path) -> Optional[str]:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return sha256_bytes(GENERATED_BLOCK_RE.sub(lambda m: f"<!-- hr:{m.group(1)} -->", text).encode("utf-8"))


def design_artifacts(feature: Feature) -> Dict[str, Optional[str]]:
    return {
        "requirements.json": sha256_bytes(canonical(feature.requirements())),
        "task-graph.json(plan)": sha256_bytes(canonical(_plan_view(feature.task_graph()))),
        "test-plan.json": sha256_bytes(canonical(feature.test_plan())),
        "design.md": _authored_text_hash(feature.dir / "design.md"),
    }


def bundle_hash(artifacts: Dict[str, Optional[str]]) -> str:
    return sha256_bytes(canonical(artifacts))


def design_status(feature: Feature, st: Dict[str, Any]) -> Dict[str, Any]:
    ap = st["approvals"].get("design")
    if not ap:
        return {"valid": False, "changed": [], "approval": None}
    cur = design_artifacts(feature)
    changed = [k for k, v in cur.items() if ap["artifacts"].get(k) != v]
    return {"valid": not changed, "changed": changed, "approval": ap}


def final_status(feature: Feature, st: Dict[str, Any], fp: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ap = st["approvals"].get("final")
    if not ap:
        return {"valid": False, "reason": None, "approval": None}
    fp = fp or fingerprint(feature.ws.root)
    if fp.get("code_tree") != ap.get("code_tree"):
        return {"valid": False, "reason": f"code changed (approved {ap.get('commit_sha', '')[:10]} != current {str(fp.get('commit_sha'))[:10]})", "approval": ap}
    if st["required_gates"].get("design") and not design_status(feature, st)["valid"]:
        return {"valid": False, "reason": "design approval invalid", "approval": ap}
    return {"valid": True, "reason": None, "approval": ap}


POST_DESIGN = ("executing", "verifying_tasks", "integrating", "awaiting_final_approval", "ready_to_merge")


def revalidate(feature: Feature, st: Dict[str, Any]) -> List[str]:
    notes: List[str] = []
    if st.get("kind") == "group":
        from runtime import groups

        ss = groups.split_status(feature, st)
        if ss["approval"] and not ss["valid"]:
            _invalidate(feature, st, "split", "changed after approval: " + ", ".join(ss["changed"]))
            notes.append("split approval invalidated: " + ", ".join(ss["changed"]))
            if st["state"] in ("delivering", "integrating"):
                _force(feature, st, "splitting", "split approval invalidated - review and re-approval required")
                notes.append("state -> splitting")
            feature.save_state(st)
        return notes
    ds = design_status(feature, st)
    if ds["approval"] and not ds["valid"]:
        _invalidate(feature, st, "design", "changed after approval: " + ", ".join(ds["changed"]))
        notes.append("design approval invalidated: " + ", ".join(ds["changed"]))
        if st["approvals"].get("final"):
            _invalidate(feature, st, "final", "cascaded from design approval invalidation")
            notes.append("final approval invalidated (cascade)")
        if st["required_gates"].get("design") and st["state"] in POST_DESIGN:
            _force(feature, st, "planning", "design approval invalidated - review and re-approval required")
            notes.append("state -> planning")
    fs = final_status(feature, st)
    if fs["approval"] and not fs["valid"]:
        _invalidate(feature, st, "final", fs["reason"])
        notes.append("final approval invalidated: " + str(fs["reason"]))
        if st["state"] == "ready_to_merge":
            _force(feature, st, "integrating", "current code differs from approved code - re-verification required")
            notes.append("state -> integrating")
    if notes:
        feature.save_state(st)
    return notes


def _invalidate(feature: Feature, st: Dict[str, Any], gate: str, reason: str) -> None:
    ap = st["approvals"].get(gate)
    if not ap:
        return
    st.setdefault("invalidated_approvals", []).append({**ap, "invalidated_at": now(), "invalidated_reason": reason})
    st["approvals"][gate] = None
    feature.emit("approval_invalidated", gate=gate, reason=reason)


def _force(feature: Feature, st: Dict[str, Any], target: str, reason: str) -> None:
    prev = st["state"]
    st["state"] = target
    feature.emit("state_changed", **{"from": prev, "to": target, "reason": reason, "forced": True})


def approve_design(feature: Feature, st: Dict[str, Any], by: str, scope: str, note: str,
                   proof: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from runtime.verification.plan_check import check_plan

    if not by:
        raise HRError("--by (approver) is required")
    if st["state"] != "awaiting_design_approval":
        raise GateError(f"design approval is only possible in awaiting_design_approval (current: {st['state']})")
    pc = check_plan(feature.requirements(), feature.task_graph(), feature.test_plan(), st["mode"])
    if not pc["ok"]:
        raise GateError("cannot approve while plan hard-fails remain:\n  - " + "\n  - ".join(pc["hard_fail"]))
    arts = design_artifacts(feature)
    if arts["design.md"] is None and st["mode"] in ("L2", "L3"):
        raise GateError("design.md is missing")
    from runtime import redpill

    redpill.check_before_approval(feature, "design")
    fp = fingerprint(feature.ws.root)
    record = {
        "gate": "design",
        "approver": by,
        "approved_at": now(),
        "via": "cli",
        **(proof or {}),
        "scope": scope or "entire design",
        "note": note,
        "requirements_revision": feature.requirements().get("revision"),
        "artifacts": arts,
        "bundle_hash": bundle_hash(arts),
        "base_commit_sha": fp.get("commit_sha"),
    }
    ev = feature.emit("approval_granted", gate="design", approver=by, bundle_hash=record["bundle_hash"],
                      actor=f"human:{by}", **(proof or {}))
    record["event_hash"] = ev["hash"]
    st["approvals"]["design"] = record
    return record


def approve_final(feature: Feature, st: Dict[str, Any], by: str, risks: str, note: str,
                  proof: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from runtime.verification import evidence, failures

    if not by:
        raise HRError("--by (approver) is required")
    if st["state"] != "awaiting_final_approval":
        raise GateError(f"final approval is only possible in awaiting_final_approval (current: {st['state']})")
    fp = fingerprint(feature.ws.root)
    if not fp["git"]:
        raise GateError("final approval must be bound to a git commit (no git repository / commit)")
    if fp["dirty"]:
        raise GateError("uncommitted code changes: " + ", ".join(fp["dirty_paths"]))
    if st["required_gates"].get("design") and not design_status(feature, st)["valid"]:
        raise GateError("no valid design approval")
    summ = evidence.summarize(feature.test_plan(), feature.test_results(), fp)
    if not summ["all_passed"]:
        bad = [f"{r['test']['id']}={r['status']}" for r in summ["rows"] if r["status"] != "passed"]
        raise GateError("not all required tests pass on the current code: " + ", ".join(bad))
    from runtime import redpill

    redpill.check_before_approval(feature, "final")
    record = {
        "gate": "final",
        "approver": by,
        "approved_at": now(),
        "via": "cli",
        **(proof or {}),
        "commit_sha": fp["commit_sha"],
        "code_tree": fp["code_tree"],
        "tests": {"passed": len(summ["rows"]), "run_ids": [r["run"]["run_id"] for r in summ["rows"]]},
        "unresolved_failures": [f["id"] for f in failures.unresolved(feature)],
        "unresolved_risks": risks or "",
        "note": note,
    }
    ev = feature.emit("approval_granted", gate="final", approver=by, commit_sha=fp["commit_sha"],
                      code_tree=fp["code_tree"], actor=f"human:{by}", **(proof or {}))
    record["event_hash"] = ev["hash"]
    st["approvals"]["final"] = record
    return record
