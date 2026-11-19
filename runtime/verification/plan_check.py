from __future__ import annotations

from typing import Any, Dict, List, Set

TASK_STATUSES = ("planned", "in_progress", "implemented", "verified", "rework_required", "blocked", "cancelled")
TEST_TYPES = ("unit", "component", "contract", "integration", "e2e", "regression", "security", "safety", "performance",
              "manual", "static")
REGRESSION_SCOPES = ("targeted", "full")


def _find_cycle(tasks: Dict[str, Dict[str, Any]]) -> List[str]:
    WHITE, GREY, BLACK = 0, 1, 2
    color = {t: WHITE for t in tasks}
    stack: List[str] = []

    def visit(n: str) -> List[str]:
        color[n] = GREY
        stack.append(n)
        for d in tasks[n].get("depends_on", []):
            if d not in tasks:
                continue
            if color[d] == GREY:
                return stack[stack.index(d):] + [d]
            if color[d] == WHITE:
                cyc = visit(d)
                if cyc:
                    return cyc
        stack.pop()
        color[n] = BLACK
        return []

    for t in tasks:
        if color[t] == WHITE:
            cyc = visit(t)
            if cyc:
                return cyc
    return []


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


def check_plan(req: Dict[str, Any], graph: Dict[str, Any], plan: Dict[str, Any], mode: str) -> Dict[str, Any]:
    hard: List[str] = []
    warn: List[str] = []

    reqs = req.get("requirements", [])
    tasks_list = graph.get("tasks", [])
    tests_list = plan.get("tests", [])
    tasks = {t.get("id"): t for t in tasks_list}
    tests = {t.get("id"): t for t in tests_list}

    if not reqs:
        hard.append("no requirements (requirements.json)")
    if not tasks_list:
        hard.append("no tasks (task-graph.json)")
    if not tests_list:
        hard.append("no test plan (test-plan.json)")
    if len(tasks) != len(tasks_list):
        hard.append("duplicate task ids")
    if len(tests) != len(tests_list):
        hard.append("duplicate test ids")

    for q in req.get("open_questions", []):
        if q.get("status", "open") == "open" and (q.get("blocking") or q.get("safety")):
            kind = "safety-related " if q.get("safety") else ""
            hard.append(f"unresolved {kind}blocking question {q.get('id')}: {q.get('text')}")
    for d in req.get("decisions", []):
        if d.get("safety") and d.get("decided_by") != "user":
            hard.append(f"risky policy {d.get('id')} decided without the user (decided_by={d.get('decided_by')})")

    from runtime.verification.evidence import runner_of

    strict = mode in ("L2", "L3")
    for tid, t in tests.items():
        runner = runner_of(t)
        steps = t.get("steps") or []
        if runner == "command" and not t.get("command"):
            hard.append(f"{tid}: runner is command but there is no command")
        if runner != "command":
            if not steps:
                hard.append(f"{tid}: a test run by {'an agent' if runner == 'agent' else 'a human'} needs `steps`, "
                            "each with what to do and the observable result that counts as a pass")
            for i, s in enumerate(steps, 1):
                if not isinstance(s, dict) or not str(s.get("do") or "").strip() or not str(s.get("expect") or "").strip():
                    hard.append(f"{tid}: step {i} needs both `do` and `expect` (the pass criterion for that step)")
        if runner == "human" and not str(t.get("human_reason") or "").strip():
            hard.append(f"{tid}: run by a human without `human_reason` - say why a script or an agent cannot do it, "
                        "or make it an agent test")
        if not t.get("pass_criteria"):
            hard.append(f"{tid}: missing pass_criteria")
        if strict and t.get("level") == "integration" and t.get("required", True) and not t.get("estimated_seconds"):
            warn.append(f"{tid}: no estimated_seconds - the reviewer cannot see what this plan costs to run")
        if t.get("type") not in TEST_TYPES:
            warn.append(f"{tid}: unknown type {t.get('type')!r}")
        if t.get("level") not in ("task", "integration"):
            hard.append(f"{tid}: level must be task|integration")
        for x in t.get("task_ids", []):
            if x not in tasks:
                hard.append(f"{tid}: references unknown task {x}")

    req_ids = {r.get("id") for r in reqs}
    for tid, t in tasks.items():
        if not t.get("purpose"):
            hard.append(f"{tid}: missing purpose")
        if not t.get("acceptance_criteria"):
            hard.append(f"{tid}: missing acceptance criteria")
        ver = t.get("verification", [])
        if not ver:
            hard.append(f"{tid}: no verification method")
        for v in ver:
            if v not in tests:
                hard.append(f"{tid}: references unknown test {v}")
        for d in t.get("depends_on", []):
            if d not in tasks:
                hard.append(f"{tid}: unknown dependency {d}")
        for r in t.get("requirement_ids", []):
            if r not in req_ids:
                hard.append(f"{tid}: references unknown requirement {r}")
        if not t.get("requirement_ids"):
            warn.append(f"{tid}: not linked to any requirement (check its user value / system responsibility)")
        if t.get("status", "planned") not in TASK_STATUSES:
            hard.append(f"{tid}: unknown status {t.get('status')!r}")
        if strict and not isinstance(t.get("changes_flow"), bool):
            hard.append(f"{tid}: set `changes_flow` to true or false (true: the task changes an interface or how "
                        "components interact, and its document needs a diagram)")
        if t.get("risk") == "high" and t.get("human_review") != "required":
            warn.append(f"{tid}: high-risk task but human_review is not required")

    cycle = _find_cycle(tasks)
    if cycle:
        hard.append("dependency cycle: " + " -> ".join(cycle))

    coverage = {}
    for r in reqs:
        rid = r.get("id")
        r_tasks = [tid for tid, t in tasks.items() if rid in t.get("requirement_ids", [])]
        r_tests = sorted(
            tid for tid in ({tid for tid, t in tests.items() if rid in t.get("requirement_ids", [])}
                            | {v for x in r_tasks for v in tasks[x].get("verification", [])})
            if tests.get(tid, {}).get("type") != "static"
        )
        coverage[rid] = {"tasks": r_tasks, "tests": r_tests}
        if r.get("priority", "must") == "must":
            if not r_tasks:
                hard.append(f"must-requirement {rid} is not covered by any task")
            if not r_tests:
                hard.append(f"must-requirement {rid} has no verification")
            if not r.get("acceptance"):
                hard.append(f"must-requirement {rid} has no acceptance criteria")

    if mode in ("L2", "L3"):
        integ = [t for t in tests_list if t.get("level") == "integration" and t.get("required", True)]
        if not integ:
            hard.append(f"{mode}: no required feature-level integration test is planned")
        if mode == "L3" and not any(t.get("type") == "regression" for t in tests_list):
            warn.append("L3: no regression test is planned")
        reg = plan.get("regression") or {}
        if reg.get("scope") not in REGRESSION_SCOPES or not str(reg.get("rationale") or "").strip():
            hard.append("test-plan.json needs `regression: {scope: targeted|full, rationale}` - which existing tests "
                        "re-run, and why that is enough for what this change can break")
        elif reg["scope"] == "targeted":
            for t in tests_list:
                if t.get("type") == "regression" and not t.get("covers"):
                    warn.append(f"{t.get('id')}: regression scope is targeted but this test has no `covers` paths, "
                                "so it re-runs after every code change")

    providers: Dict[str, List[str]] = {}
    for tid, t in tasks.items():
        for c in (t.get("contracts") or {}).get("provides", []):
            providers.setdefault(c, []).append(tid)
    for c, ps in providers.items():
        if len(ps) > 1:
            hard.append(f"unresolved interface conflict: contract {c!r} provided by several tasks ({', '.join(ps)})")
    for tid, t in tasks.items():
        anc = _ancestors(tasks, tid)
        for c in (t.get("contracts") or {}).get("consumes", []):
            for p in providers.get(c, []):
                if p != tid and p not in anc:
                    hard.append(f"{tid}: consumes contract {c!r} but does not depend on its provider {p}")
    ids = sorted(tasks)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if a in _ancestors(tasks, b) or b in _ancestors(tasks, a):
                continue
            pa = set((tasks[a].get("scope") or {}).get("paths", []))
            pb = set((tasks[b].get("scope") or {}).get("paths", []))
            shared = pa & pb
            if shared:
                warn.append(f"{a}/{b}: change the same paths without a dependency ({', '.join(sorted(shared))}) - do not run in parallel")

    return {"ok": not hard, "hard_fail": hard, "warnings": warn, "coverage": coverage}


def topo_order(graph: Dict[str, Any]) -> List[str]:
    tasks = {t["id"]: t for t in graph.get("tasks", [])}
    order: List[str] = []
    done: Set[str] = set()

    def visit(n: str) -> None:
        if n in done or n not in tasks:
            return
        done.add(n)
        for d in tasks[n].get("depends_on", []):
            visit(d)
        order.append(n)

    for t in sorted(tasks):
        visit(t)
    return order
