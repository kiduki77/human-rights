from __future__ import annotations

from typing import Any, Dict, Optional

from runtime.common import HRError, now
from runtime.state.store import Feature

CAUSE_TYPES = {
    "unclassified": "not yet classified",
    "implementation": "implementation defect -> fix the related task",
    "interface": "interface/integration defect -> fix related tasks and contracts",
    "design": "requirements/design defect -> ask, redesign, re-approve",
    "test_env": "test/environment defect -> repair the test or environment, record evidence",
}
NEXT_STATE = {
    "implementation": "rework_required",
    "interface": "rework_required",
    "design": "clarifying",
    "test_env": None,
}


def _open_for(fails: Dict[str, Any], test_id: str) -> Optional[Dict[str, Any]]:
    for f in reversed(fails.get("failures", [])):
        if f["test_id"] == test_id and f["status"] in ("open", "escalated"):
            return f
    return None


def on_failed(feature: Feature, test: Dict[str, Any], run: Dict[str, Any], max_retries: int) -> Dict[str, Any]:
    fails = feature.failures()
    f = _open_for(fails, test["id"])
    observed = f"status={run['status']} exit={run.get('exit_code')}"
    if f is None:
        f = {
            "id": f"FAIL-{len(fails.get('failures', [])) + 1:03d}",
            "test_id": test["id"],
            "requirement_ids": test.get("requirement_ids", []),
            "suspect_tasks": test.get("task_ids", []),
            "observed": observed,
            "expected": test.get("pass_criteria"),
            "evidence": [],
            "run_ids": [],
            "cause_type": "unclassified",
            "confirmed_cause": None,
            "fix_task": None,
            "retest": [test["id"]],
            "retry_count": 0,
            "status": "open",
            "created_at": now(),
        }
        fails.setdefault("failures", []).append(f)
    f["retry_count"] += 1
    f["observed"] = observed
    f["run_ids"].append(run["run_id"])
    ev = run.get("log_ref") or run.get("evidence")
    if ev:
        f["evidence"].append(ev)
    f["updated_at"] = now()
    escalate = f["retry_count"] >= max_retries and f["status"] != "escalated"
    if escalate:
        f["status"] = "escalated"
    feature.save("failures", fails)
    feature.emit("failure_recorded", failure_id=f["id"], test_id=test["id"], retry_count=f["retry_count"],
                 escalated=escalate)
    if escalate:
        from runtime.state import machine

        machine.force_block(feature, f"{f['id']}: {test['id']} failed {f['retry_count']} times in a row - human decision needed")
    return {"id": f["id"], "retry_count": f["retry_count"], "escalated": f["status"] == "escalated"}


def on_passed(feature: Feature, test: Dict[str, Any], run: Dict[str, Any]) -> None:
    if run.get("dirty"):
        return
    fails = feature.failures()
    changed = False
    for f in fails.get("failures", []):
        if f["test_id"] == test["id"] and f["status"] in ("open", "escalated"):
            f["status"] = "resolved"
            f["resolved_by_run"] = run["run_id"]
            f["updated_at"] = now()
            changed = True
            feature.emit("failure_resolved", failure_id=f["id"], run_id=run["run_id"])
    if changed:
        feature.save("failures", fails)


def classify(feature: Feature, failure_id: str, cause_type: str, cause: Optional[str],
             suspect: Optional[str], fix_task: Optional[str], retest: Optional[str]) -> Dict[str, Any]:
    if cause_type not in CAUSE_TYPES:
        raise HRError(f"cause-type must be one of {', '.join(CAUSE_TYPES)}")
    fails = feature.failures()
    for f in fails.get("failures", []):
        if f["id"] == failure_id:
            f["cause_type"] = cause_type
            if cause:
                f["confirmed_cause"] = cause
            if suspect:
                f["suspect_tasks"] = [s.strip() for s in suspect.split(",") if s.strip()]
            if fix_task:
                f["fix_task"] = fix_task
            if retest:
                f["retest"] = [s.strip() for s in retest.split(",") if s.strip()]
            f["updated_at"] = now()
            feature.save("failures", fails)
            feature.emit("failure_classified", failure_id=failure_id, cause_type=cause_type, fix_task=fix_task)
            return {"failure": f, "next_state": NEXT_STATE.get(cause_type), "guidance": CAUSE_TYPES[cause_type]}
    raise HRError(f"no such failure: {failure_id}")


def unresolved(feature: Feature):
    return [f for f in feature.failures().get("failures", []) if f["status"] in ("open", "escalated")]
