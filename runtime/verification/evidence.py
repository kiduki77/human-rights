from __future__ import annotations

from typing import Any, Dict, List, Optional

PASS = ("passed", "manual_passed")
FAIL = ("failed", "error", "manual_failed")


def runs_for(results: Dict[str, Any], test_id: str) -> List[Dict[str, Any]]:
    return [r for r in results.get("runs", []) if r.get("test_id") == test_id]


def status_at(results: Dict[str, Any], test_id: str, fp: Dict[str, Any]) -> Dict[str, Any]:
    runs = runs_for(results, test_id)
    if not runs:
        return {"status": "not_run", "run": None}
    if not fp.get("git"):
        latest = runs[-1]
        ok = latest.get("status") in PASS
        return {"status": "unbound_passed" if ok else "unbound_failed", "run": latest}
    if fp.get("dirty"):
        same = [r for r in runs if r.get("dirty") and r.get("worktree_hash") == fp.get("worktree_hash")
                and r.get("code_tree") == fp.get("code_tree")]
        suffix = "_uncommitted"
    else:
        same = [r for r in runs if not r.get("dirty") and r.get("code_tree") == fp.get("code_tree")]
        suffix = ""
    if not same:
        return {"status": "stale", "run": runs[-1]}
    latest = same[-1]
    if latest.get("status") in PASS:
        return {"status": "passed" + suffix, "run": latest}
    if latest.get("status") in FAIL:
        return {"status": "failed" + suffix, "run": latest}
    return {"status": latest.get("status", "unknown"), "run": latest}


def is_pass(status: str, lenient: bool) -> bool:
    if status == "passed":
        return True
    return lenient and status in ("passed_uncommitted", "unbound_passed")


def required_tests(plan: Dict[str, Any], level: Optional[str] = None, task_id: Optional[str] = None,
                   graph: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    tests = [t for t in plan.get("tests", []) if t.get("required", True)]
    if level:
        tests = [t for t in tests if t.get("level") == level]
    if task_id:
        ids = set()
        if graph:
            for t in graph.get("tasks", []):
                if t.get("id") == task_id:
                    ids.update(t.get("verification", []))
        tests = [t for t in tests if t["id"] in ids or (t.get("level") == "task" and task_id in t.get("task_ids", []))]
    return tests


def summarize(plan: Dict[str, Any], results: Dict[str, Any], fp: Dict[str, Any],
              level: Optional[str] = None, lenient: bool = False,
              tests: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    rows = []
    for t in (tests if tests is not None else required_tests(plan, level=level)):
        st = status_at(results, t["id"], fp)
        rows.append({"test": t, **st})
    counts: Dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {
        "rows": rows,
        "counts": counts,
        "all_passed": bool(rows) and all(is_pass(r["status"], lenient) for r in rows),
    }
