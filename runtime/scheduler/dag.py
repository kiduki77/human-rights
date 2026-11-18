from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

READY_STATUSES = ("planned", "rework_required")
GLOB_CHARS = "*?[{"


def norm_path(p: str) -> str:
    p = p.replace("\\", "/").strip()
    for i, ch in enumerate(p):
        if ch in GLOB_CHARS:
            p = p[:i]
            break
    while p.startswith("./"):
        p = p[2:]
    return p.rstrip("/")


def paths_overlap(a: str, b: str) -> bool:
    a, b = norm_path(a), norm_path(b)
    if not a or not b:
        return True
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def _contracts(t: Dict[str, Any]) -> Dict[str, Set[str]]:
    c = t.get("contracts") or {}
    return {"provides": set(c.get("provides", [])), "consumes": set(c.get("consumes", []))}


def task_conflicts(a: Dict[str, Any], b: Dict[str, Any]) -> List[str]:
    reasons: List[str] = []
    for t in (a, b):
        if t.get("parallel_safe") is False:
            reasons.append(f"{t['id']} is marked parallel_safe: false")
        if not (t.get("scope") or {}).get("paths"):
            reasons.append(f"{t['id']} declares no scope.paths (unknown footprint)")
    pa = (a.get("scope") or {}).get("paths", [])
    pb = (b.get("scope") or {}).get("paths", [])
    shared = sorted({f"{x}~{y}" if x != y else x for x in pa for y in pb if paths_overlap(x, y)})
    if shared:
        reasons.append("overlapping paths: " + ", ".join(shared))
    ca, cb = _contracts(a), _contracts(b)
    both = ca["provides"] & cb["provides"]
    if both:
        reasons.append("both provide contract " + ", ".join(sorted(both)))
    cross = (ca["provides"] & cb["consumes"]) | (cb["provides"] & ca["consumes"])
    if cross:
        reasons.append("one provides a contract the other consumes: " + ", ".join(sorted(cross)))
    res = set(a.get("resources", [])) & set(b.get("resources", []))
    if res:
        reasons.append("shared resources: " + ", ".join(sorted(res)))
    return reasons


def _ancestors(tasks: Dict[str, Dict[str, Any]], tid: str) -> Set[str]:
    seen: Set[str] = set()
    todo = list(tasks.get(tid, {}).get("depends_on", []))
    while todo:
        d = todo.pop()
        if d in seen or d not in tasks:
            continue
        seen.add(d)
        todo.extend(tasks[d].get("depends_on", []))
    return seen


def dep_done(task: Dict[str, Any], worktrees: Dict[str, Any]) -> bool:
    if task.get("status") == "cancelled":
        return True
    if task.get("status") != "verified":
        return False
    wt = worktrees.get(task["id"])
    return wt is None or wt.get("status") in ("merged", "removed")


def ready_tasks(graph: Dict[str, Any], worktrees: Dict[str, Any]) -> Dict[str, List[str]]:
    from runtime.verification.plan_check import topo_order

    tasks = {t["id"]: t for t in graph.get("tasks", [])}
    ready: List[str] = []
    waiting: Dict[str, List[str]] = {}
    for tid in topo_order(graph):
        t = tasks[tid]
        if t.get("status", "planned") not in READY_STATUSES:
            continue
        if worktrees.get(tid, {}).get("status") == "active":
            continue
        pending = [d for d in t.get("depends_on", []) if d in tasks and not dep_done(tasks[d], worktrees)]
        if pending:
            waiting[tid] = pending
        else:
            ready.append(tid)
    return {"ready": ready, "waiting": waiting}


def plan_batch(graph: Dict[str, Any], worktrees: Dict[str, Any], max_parallel: int,
               running: Optional[List[str]] = None) -> Dict[str, Any]:
    tasks = {t["id"]: t for t in graph.get("tasks", [])}
    running = list(running or [wid for wid, w in worktrees.items() if w.get("status") == "active"])
    rt = ready_tasks(graph, worktrees)
    batch: List[str] = []
    deferred: Dict[str, List[str]] = {}
    slots = max(0, max_parallel - len(running))
    for tid in rt["ready"]:
        if len(batch) >= slots:
            deferred[tid] = [f"max_parallel_tasks={max_parallel} reached"]
            continue
        reasons: List[str] = []
        for other in running + batch:
            if other in _ancestors(tasks, tid) or tid in _ancestors(tasks, other):
                reasons.append(f"depends on {other}")
                continue
            reasons += [f"vs {other}: {r}" for r in task_conflicts(tasks[tid], tasks[other])]
        if reasons:
            deferred[tid] = reasons
        else:
            batch.append(tid)
    return {"batch": batch, "deferred": deferred, "waiting": rt["waiting"], "running": running}


def test_batches(tests: List[Dict[str, Any]], max_parallel: int) -> List[List[Dict[str, Any]]]:
    rounds: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    used: Set[str] = set()

    def flush() -> None:
        nonlocal current, used
        if current:
            rounds.append(current)
        current, used = [], set()

    for t in tests:
        solo = max_parallel <= 1 or t.get("exclusive") or not t.get("parallel_safe")
        res = set(t.get("resources", []))
        if solo:
            flush()
            rounds.append([t])
            continue
        if len(current) >= max_parallel or (res & used):
            flush()
        current.append(t)
        used |= res
    flush()
    return rounds
