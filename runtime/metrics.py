from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from runtime import redpill
from runtime.common import fingerprint
from runtime.state.store import Feature, Workspace

MANUAL_KINDS = {
    "tokens": "agent tokens used (host-reported)",
    "agent_seconds": "agent wall-clock seconds (host-reported)",
    "review_minutes": "human minutes spent reviewing design/code/verification",
    "escaped_defect": "defect found after final approval",
    "intent_mismatch": "user judged the result different from what they meant",
    "unnecessary_question": "a question whose answer changed neither design nor result",
    "question_asked": "a question asked during elicitation (denominator for unnecessary questions)",
}
WAIT_STATES = ("awaiting_design_approval", "awaiting_final_approval")


def _ts(s: str) -> datetime.datetime:
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)


def feature_metrics(feature: Feature) -> Dict[str, Any]:
    from runtime.verification import evidence
    from runtime.verification.plan_check import check_plan

    evs = [e for e in feature.events() if e.get("timestamp")]
    st = feature.state()
    if not evs:
        return {"feature_id": feature.id}
    start = _ts(evs[0]["timestamp"])
    end: Optional[datetime.datetime] = None
    in_state: Dict[str, float] = {}
    cur, since = "created", start
    blocked_escalation = 0.0
    escalated = False
    counts = {k: 0 for k in ("rework", "failures", "invalidations", "rejections", "scope_changes",
                             "reclassifications", "test_runs", "failed_runs")}
    test_seconds = 0.0
    tasks_reworked = set()
    manual: Dict[str, float] = {k: 0 for k in MANUAL_KINDS}
    wt_created: Dict[str, datetime.datetime] = {}
    wt_merged: Dict[str, datetime.datetime] = {}
    batches: List[List[str]] = []
    classified = 0
    for e in evs:
        t, kind = _ts(e["timestamp"]), e["event"]
        if kind == "state_changed":
            dur = (t - since).total_seconds()
            in_state[cur] = in_state.get(cur, 0) + dur
            if cur == "blocked" and escalated:
                blocked_escalation += dur
            cur, since = e.get("to"), t
            escalated = bool(e.get("escalation"))
            if cur == "rework_required":
                counts["rework"] += 1
            if cur in ("completed", "cancelled", "failed"):
                end = t
        elif kind == "task_status" and e.get("to") == "rework_required":
            tasks_reworked.add(e.get("task_id"))
        elif kind == "failure_recorded" and e.get("retry_count") == 1:
            counts["failures"] += 1
        elif kind == "approval_invalidated":
            counts["invalidations"] += 1
        elif kind == "approval_rejected":
            counts["rejections"] += 1
        elif kind == "scope_change_requested":
            counts["scope_changes"] += 1
        elif kind == "classified":
            classified += 1
        elif kind == "test_finished" and str(e.get("actor", "")).startswith("runner"):
            counts["test_runs"] += 1
            test_seconds += float(e.get("duration_s") or 0)
            if e.get("status") in ("failed", "error"):
                counts["failed_runs"] += 1
        elif kind == "metric_recorded":
            manual[e["kind"]] = manual.get(e["kind"], 0) + float(e.get("value") or 0)
        elif kind == "worktree_created":
            wt_created[e["task_id"]] = t
        elif kind == "worktree_merged":
            wt_merged[e["task_id"]] = t
        elif kind == "batch_scheduled":
            batches.append(list(e.get("tasks", [])))
    if end is None:
        in_state[cur] = in_state.get(cur, 0) + (_now() - since).total_seconds()
    counts["reclassifications"] = max(0, classified - 1)
    lead = ((end or _now()) - start).total_seconds()

    tasks = feature.task_graph().get("tasks", [])
    fp = fingerprint(feature.ws.root)
    pc = check_plan(feature.requirements(), feature.task_graph(), feature.test_plan(), st.get("mode") or "L3")
    lenient = st.get("mode") in ("L0", "L1")
    results = feature.test_results()
    tests_by_id = {t["id"]: t for t in feature.test_plan().get("tests", [])}
    must = [r for r in feature.requirements().get("requirements", []) if r.get("priority", "must") == "must"]
    covered = 0
    for r in must:
        tids = pc["coverage"].get(r["id"], {}).get("tests", [])
        if tids and all(evidence.is_pass(evidence.status_at(results, tid, fp, tests_by_id.get(tid))["status"], lenient) for tid in tids):
            covered += 1

    par = []
    for b in batches:
        done = [x for x in b if x in wt_created and x in wt_merged]
        if len(done) < 2:
            continue
        serial = sum((wt_merged[x] - wt_created[x]).total_seconds() for x in done)
        wall = (max(wt_merged[x] for x in done) - min(wt_created[x] for x in done)).total_seconds()
        par.append({"tasks": done, "serial_s": serial, "wall_s": wall,
                    "speedup": round(serial / wall, 2) if wall > 0 else None})

    asked = manual.get("question_asked") or len(feature.requirements().get("open_questions", []))
    return {
        "feature_id": feature.id,
        "title": st.get("title"),
        "mode": st.get("mode"),
        "state": st.get("state"),
        "completed": end is not None and st.get("state") == "completed",
        "lead_time_s": lead,
        "time_in_state_s": in_state,
        "approval_wait_s": sum(in_state.get(s, 0) for s in WAIT_STATES),
        "escalation_wait_s": blocked_escalation,
        "human_review_minutes": manual.get("review_minutes", 0),
        "tasks": len(tasks),
        "rework_rate": round(len([x for x in tasks_reworked if x]) / len(tasks), 3) if tasks else None,
        **counts,
        "test_seconds": round(test_seconds, 2),
        "verification_coverage": round(covered / len(must), 3) if must else None,
        "escaped_defects": manual.get("escaped_defect", 0),
        "intent_mismatch": manual.get("intent_mismatch", 0),
        "unnecessary_question_rate": round(manual.get("unnecessary_question", 0) / asked, 3) if asked else None,
        "tokens": manual.get("tokens", 0),
        "agent_seconds": manual.get("agent_seconds", 0),
        "parallel_batches": par,
        "redpill": redpill.stats(feature),
    }


def aggregate(ws: Workspace) -> Dict[str, Any]:
    rows = [feature_metrics(Feature(ws, fid)) for fid in ws.list_features()]
    rows = [r for r in rows if "lead_time_s" in r]
    done = [r for r in rows if r["completed"]]

    def mean(key: str, src: List[Dict[str, Any]]) -> Optional[float]:
        vals = [r[key] for r in src if r.get(key) is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    by_mode: Dict[str, Dict[str, Any]] = {}
    for m in ("L0", "L1", "L2", "L3"):
        src = [r for r in done if r["mode"] == m]
        if src:
            by_mode[m] = {"features": len(src), "mean_lead_time_s": mean("lead_time_s", src),
                          "mean_approval_wait_s": mean("approval_wait_s", src),
                          "mean_rework_rate": mean("rework_rate", src),
                          "escaped_defects": sum(r["escaped_defects"] for r in src)}
    return {
        "features": len(rows),
        "completed": len(done),
        "by_mode": by_mode,
        "mean_verification_coverage": mean("verification_coverage", rows),
        "total_tokens": sum(r["tokens"] for r in rows),
        "total_test_seconds": round(sum(r["test_seconds"] for r in rows), 2),
        "rows": rows,
    }


def fmt_duration(s: Optional[float]) -> str:
    if s is None:
        return "-"
    s = int(s)
    if s < 120:
        return f"{s}s"
    if s < 7200:
        return f"{s // 60}m"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"
