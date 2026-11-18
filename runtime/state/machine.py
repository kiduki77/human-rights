from __future__ import annotations

from typing import Any, Dict, List, Optional

from runtime.common import GateError, HRError, fingerprint, now
from runtime.state.store import Feature

STATES = (
    "created", "triaging", "clarifying", "investigating", "planning", "awaiting_design_approval",
    "executing", "verifying_tasks", "integrating", "awaiting_final_approval", "ready_to_merge",
    "completed", "blocked", "rework_required", "cancelled", "failed",
)
TERMINAL = ("completed", "cancelled", "failed")

TRANSITIONS: Dict[str, tuple] = {
    "created": ("triaging",),
    "triaging": ("clarifying", "investigating", "planning", "executing"),
    "clarifying": ("investigating", "planning", "executing"),
    "investigating": ("clarifying", "planning", "executing"),
    "planning": ("clarifying", "investigating", "awaiting_design_approval", "executing"),
    "awaiting_design_approval": ("clarifying", "planning", "executing"),
    "executing": ("verifying_tasks", "rework_required", "clarifying"),
    "verifying_tasks": ("executing", "integrating", "rework_required", "completed"),
    "integrating": ("awaiting_final_approval", "ready_to_merge", "rework_required", "clarifying", "executing"),
    "awaiting_final_approval": ("ready_to_merge", "rework_required"),
    "ready_to_merge": ("completed", "rework_required"),
    "rework_required": ("executing", "clarifying", "planning", "investigating"),
    "blocked": (),
}
ALWAYS_ALLOWED = ("blocked", "cancelled", "failed")
LENIENT_MODES = ("L0", "L1")

STATE_LABELS = {
    "created": "created", "triaging": "triaging", "clarifying": "clarifying intent",
    "investigating": "investigating code", "planning": "designing & decomposing",
    "awaiting_design_approval": "awaiting design approval", "executing": "implementing",
    "verifying_tasks": "verifying tasks", "integrating": "integration testing",
    "awaiting_final_approval": "awaiting final approval", "ready_to_merge": "ready to merge",
    "completed": "completed", "blocked": "blocked", "rework_required": "rework required",
    "cancelled": "cancelled", "failed": "failed",
}


def _open_blocking_questions(req: Dict[str, Any]) -> List[str]:
    return [
        f"{q.get('id')}: {q.get('text')}"
        for q in req.get("open_questions", [])
        if q.get("status", "open") == "open" and (q.get("blocking") or q.get("safety"))
    ]


def tests_gate(feature: Feature, st: Dict[str, Any], strict: bool) -> List[str]:
    from runtime.verification import evidence

    fp = fingerprint(feature.ws.root)
    plan = feature.test_plan()
    if not evidence.required_tests(plan):
        return ["no required tests are planned (use `hr verify --adhoc` or test-plan.json)"]
    if strict and not fp["git"]:
        return [f"{st['mode']}: verification evidence must be bound to a git commit (git repository/commit required)"]
    if strict and fp["dirty"]:
        return ["uncommitted code changes - commit, then re-run all required tests: " + ", ".join(fp["dirty_paths"][:5])]
    summ = evidence.summarize(plan, feature.test_results(), fp, lenient=not strict)
    return [
        f"{r['test']['id']} = {r['status']}"
        for r in summ["rows"]
        if not evidence.is_pass(r["status"], lenient=not strict)
    ]


def guards(feature: Feature, st: Dict[str, Any], target: str) -> List[str]:
    from runtime.approvals.gates import design_status, final_status
    from runtime.verification import failures
    from runtime.verification.plan_check import check_plan

    cur = st["state"]
    mode = st.get("mode")
    problems: List[str] = []

    if cur in TERMINAL:
        return [f"cannot leave terminal state {cur}"]
    if target in ALWAYS_ALLOWED:
        return []
    if cur == "blocked":
        if target != st.get("state_before_block"):
            return [f"from blocked you can only return to the previous state ({st.get('state_before_block')})"]
        if st.get("block_kind") == "escalation":
            return ["an escalation must be released by a human: `! .workflow/hr unblock --by <name> --note <decision>`"]
        return []
    if target not in TRANSITIONS.get(cur, ()):
        return [f"transition not allowed: {cur} -> {target} (allowed: {', '.join(TRANSITIONS.get(cur, ()) + ALWAYS_ALLOWED)})"]

    if cur == "triaging" and not mode:
        problems.append("classify first (`hr classify`)")

    req = feature.requirements()
    if target == "awaiting_design_approval" or (target == "executing" and mode in ("L2", "L3")):
        pc = check_plan(req, feature.task_graph(), feature.test_plan(), mode or "L3")
        problems += [f"[plan hard-fail] {p}" for p in pc["hard_fail"]]
        if target == "awaiting_design_approval" and not (feature.dir / "design.md").exists():
            problems.append("design.md is missing")

    if target == "executing":
        problems += [f"[unresolved requirement] {q}" for q in _open_blocking_questions(req)]
        if st["required_gates"].get("design") and not design_status(feature, st)["valid"]:
            problems.append("no valid design approval (a human runs `! .workflow/hr approve design --by <name>`)")

    if cur == "verifying_tasks" and target == "integrating":
        pending = [t["id"] for t in feature.task_graph().get("tasks", []) if t.get("status") not in ("verified", "cancelled")]
        if pending:
            problems.append("tasks not verified: " + ", ".join(pending))
        unmerged = [k for k, v in (st.get("parallel") or {}).get("worktrees", {}).items() if v.get("status") == "active"]
        if unmerged:
            problems.append("task worktrees not merged into the integration branch: " + ", ".join(sorted(unmerged))
                            + " (`hr worktree merge <task>`)")

    if target == "completed" and cur == "verifying_tasks":
        if mode not in LENIENT_MODES:
            problems.append(f"{mode}: must go through integration testing (integrating)")
        if st["required_gates"].get("final"):
            problems.append("this feature requires final human approval - go to integrating")
        problems += tests_gate(feature, st, strict=False)

    if target in ("awaiting_final_approval", "ready_to_merge") and cur == "integrating":
        if target == "ready_to_merge" and st["required_gates"].get("final"):
            problems.append("final approval is required - go to awaiting_final_approval")
        problems += [f"[integration] {p}" for p in tests_gate(feature, st, strict=mode not in LENIENT_MODES)]
        crit = [f["id"] for f in failures.unresolved(feature)]
        if crit:
            problems.append("unresolved failures: " + ", ".join(crit))

    if target == "ready_to_merge" and cur == "awaiting_final_approval":
        if not final_status(feature, st)["valid"]:
            problems.append("no valid final approval (a human runs `! .workflow/hr approve final --by <name>`)")

    if target == "completed" and cur == "ready_to_merge":
        if st["required_gates"].get("final"):
            fs = final_status(feature, st)
            if not fs["valid"]:
                problems.append(f"current code differs from approved code - re-verify / re-approve ({fs['reason']})")
        problems += tests_gate(feature, st, strict=mode not in LENIENT_MODES)

    return problems


def transition(feature: Feature, target: str, reason: str = "", actor: str = "agent") -> Dict[str, Any]:
    if target not in STATES:
        raise HRError(f"unknown state: {target}")
    st = feature.state()
    problems = guards(feature, st, target)
    if problems:
        raise GateError(f"{st['state']} -> {target} blocked:\n  - " + "\n  - ".join(problems))
    prev = st["state"]
    if target == "blocked":
        st["state_before_block"] = prev
        st["block_reason"] = reason or "no reason given"
        st["block_kind"] = "manual"
    elif prev == "blocked":
        st["state_before_block"] = None
        st["block_reason"] = None
        st["block_kind"] = None
    st["state"] = target
    feature.save_state(st)
    feature.emit("state_changed", **{"from": prev, "to": target, "reason": reason, "actor": actor})
    _redpill_hooks(feature, prev, target)
    return st


def _redpill_hooks(feature: Feature, prev: str, target: str) -> None:
    from runtime import docs, redpill

    if prev in redpill.GATE_FOR_STATE:
        outcome = "changes_requested" if target in ("clarifying", "planning", "investigating", "rework_required") else "withdrawn"
        redpill.on_leave_state(feature, prev, outcome)
    if target in redpill.GATE_FOR_STATE:
        redpill.on_enter_state(feature, target)
        docs.render(feature)


def force_block(feature: Feature, reason: str) -> None:
    st = feature.state()
    if st["state"] in TERMINAL or st["state"] == "blocked":
        return
    prev = st["state"]
    st.update(state="blocked", state_before_block=prev, block_reason=reason, block_kind="escalation")
    feature.save_state(st)
    feature.emit("state_changed", **{"from": prev, "to": "blocked", "reason": reason, "escalation": True})


def unblock(feature: Feature, by: str, note: str) -> Dict[str, Any]:
    if not by:
        raise HRError("--by is required")
    st = feature.state()
    if st["state"] != "blocked":
        raise HRError("feature is not blocked")
    prev = st["state_before_block"]
    st.update(state=prev, state_before_block=None, block_reason=None, block_kind=None)
    feature.save_state(st)
    feature.emit("unblocked", to=prev, note=note, actor=f"human:{by}")
    return st


def next_human_decision(feature: Feature, st: Dict[str, Any]) -> Optional[str]:
    s = st["state"]
    if s == "awaiting_design_approval":
        return "review the design, then approve: `! .workflow/hr approve design --by <name>` (or request changes in chat)"
    if s == "awaiting_final_approval":
        return "review the result, then approve: `! .workflow/hr approve final --by <name> [--risks \"...\"]` (or request changes in chat)"
    if s == "blocked":
        if st.get("block_kind") == "escalation":
            return f"escalation: {st.get('block_reason')} - decide, then `! .workflow/hr unblock --by <name> --note \"...\"`"
        return f"resolve blocker: {st.get('block_reason')}"
    if s == "clarifying":
        qs = _open_blocking_questions(feature.requirements())
        if qs:
            return "answer open questions: " + "; ".join(qs[:5])
    if s == "ready_to_merge":
        return "merge (auto-merge is off by default): pass `hr merge-check`, then merge the PR"
    return None


def touch_git(feature: Feature, st: Dict[str, Any]) -> None:
    from runtime.common import current_branch, head_sha

    root = feature.ws.root
    st["git"]["last_seen_head"] = head_sha(root)
    st["git"]["branch"] = current_branch(root)
    st["git"]["last_seen_at"] = now()
