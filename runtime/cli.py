from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime.common import GateError, HRError, find_repo_root, fingerprint, now
from runtime.state.store import Feature, Workspace, new_state

HUMAN_ONLY = ("approve", "record-manual", "unblock")


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _read_json_arg(raw: str) -> Any:
    if raw == "-":
        return json.loads(sys.stdin.read())
    if raw.startswith("@"):
        return json.loads(Path(raw[1:]).read_text(encoding="utf-8"))
    return json.loads(raw)


def _feature(ws: Workspace, args) -> Feature:
    return ws.resolve(getattr(args, "feature", None))


def _revalidate(feature: Feature) -> List[str]:
    from runtime.approvals.gates import revalidate

    return revalidate(feature, feature.state())


def _count(items) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for i in items:
        out[i] = out.get(i, 0) + 1
    return out


def _fmt_counts(c: Dict[str, int]) -> str:
    return "(" + ", ".join(f"{k} {v}" for k, v in sorted(c.items())) + ")" if c else ""


def cmd_init(ws: Workspace, args) -> int:
    created = ws.init()
    print(f"human-rights workspace: {ws.wf}")
    for c in created:
        print(f"  created: {c}")
    print("Human-only commands run as `! .workflow/hr <command>` (approve / record-manual / unblock).")
    return 0


def cmd_new(ws: Workspace, args) -> int:
    from runtime.state import machine

    ws.require_init()
    fid = ws.next_feature_id(args.slug or args.title)
    f = Feature(ws, fid)
    for sub in ("tasks", "details", ".internal"):
        (f.dir / sub).mkdir(parents=True, exist_ok=True)
    st = new_state(fid, args.title, args.request or args.title)
    fp = fingerprint(ws.root)
    st["git"]["base_sha"] = fp["commit_sha"]
    f.save_state(st)
    f.emit("feature_created", title=args.title, request=st["request"], base_sha=fp["commit_sha"])
    machine.transition(f, "triaging", "request received")
    ws.set_active(fid)
    print(fid)
    print(f"  {f.dir}")
    return 0


def cmd_classify(ws: Workspace, args) -> int:
    from runtime.routing.router import apply_route, route

    f = _feature(ws, args)
    st = f.state()
    flags = [x.strip() for x in (args.flags or "").split(",") if x.strip()]
    result = route(_read_json_arg(args.axes), flags, ws.config())
    notes = apply_route(st, result, now())
    f.save_state(st)
    f.emit("classified", mode=st["mode"], flags=result["flags"], effective_scores=result["effective_scores"],
           required_gates=st["required_gates"], note=args.note or "")
    gates = ", ".join(sorted({f"{g['gate']} ({g['reason']})" for g in st["gate_reasons"]})) or "none"
    print(f"mode: {st['mode']}  |  required gates: {gates}")
    for r in result["reasons"] + notes:
        print(f"  - {r}")
    return 0


def _status_data(f: Feature) -> Dict[str, Any]:
    from runtime import redpill
    from runtime.approvals.gates import design_status, final_status
    from runtime.state.machine import STATE_LABELS, next_human_decision
    from runtime.verification import evidence, failures

    st = f.state()
    fp = fingerprint(f.ws.root)
    req = f.requirements()
    tasks = f.task_graph().get("tasks", [])
    summ = evidence.summarize(f.test_plan(), f.test_results(), fp, lenient=st.get("mode") in ("L0", "L1"))
    return {
        "feature_id": f.id,
        "title": st["title"],
        "state": st["state"],
        "state_label": STATE_LABELS.get(st["state"], st["state"]),
        "mode": st.get("mode"),
        "required_gates": st["required_gates"],
        "gate_reasons": sorted({g["reason"] for g in st.get("gate_reasons", [])}),
        "design_approval": design_status(f, st),
        "final_approval": final_status(f, st, fp),
        "open_questions": [q for q in req.get("open_questions", []) if q.get("status", "open") == "open"],
        "tasks": {"total": len(tasks), "by_status": _count(t.get("status", "planned") for t in tasks)},
        "tests": {"required": len(summ["rows"]), "by_status": summ["counts"]},
        "worktrees": {k: v.get("status") for k, v in (st.get("parallel") or {}).get("worktrees", {}).items()},
        "unresolved_failures": [x["id"] for x in failures.unresolved(f)],
        "human_flags": [{"item": x["item"], "note": x.get("note", "")} for x in redpill.open_flags(f)],
        "block_reason": st.get("block_reason"),
        "git": fp,
        "next_human_decision": next_human_decision(f, st),
    }


def _format_status(d: Dict[str, Any]) -> str:
    def ap(required: bool, s: Dict[str, Any]) -> str:
        if not required:
            return "not required"
        if s["valid"]:
            return f"approved ({s['approval']['approver']})"
        return "pending"

    g = d["git"]
    git_line = "no git" if not g["git"] else f"{(g['commit_sha'] or '')[:10]}" + (
        f" ({len(g['dirty_paths'])} uncommitted changes)" if g["dirty"] else " (clean)")
    lines = [
        f"{d['feature_id']} — {d['title']}",
        f"state: {d['state_label']} ({d['state']})  |  mode: {d['mode'] or 'unclassified'}",
        f"approvals: design {ap(d['required_gates']['design'], d['design_approval'])} / "
        f"final {ap(d['required_gates']['final'], d['final_approval'])}"
        + (f"  (why: {', '.join(d['gate_reasons'])})" if d["gate_reasons"] else ""),
        f"open questions {len(d['open_questions'])}  |  tasks {d['tasks']['total']} {_fmt_counts(d['tasks']['by_status'])}  |  "
        f"required tests {d['tests']['required']} {_fmt_counts(d['tests']['by_status'])}",
        f"unresolved failures: {', '.join(d['unresolved_failures']) or 'none'}  |  code: {git_line}",
    ]
    active_wt = [k for k, v in d.get("worktrees", {}).items() if v == "active"]
    if d.get("worktrees"):
        lines.append("worktrees: " + ", ".join(f"{k} {v}" for k, v in sorted(d["worktrees"].items()))
                     + (f"  ({len(active_wt)} active)" if active_wt else ""))
    if d.get("human_flags"):
        lines.append("human review flags: " + "; ".join(f"{x['item']}" + (f" ({x['note']})" if x["note"] else "") for x in d["human_flags"]))
    if d["block_reason"]:
        lines.append(f"blocked because: {d['block_reason']}")
    lines.append(f"next human decision: {d['next_human_decision'] or 'none'}")
    return "\n".join(lines)


def cmd_status(ws: Workspace, args) -> int:
    ws.require_init()
    if not args.feature and not ws.active_feature_id():
        feats = ws.list_features()
        print("No active feature." + (f" Features: {', '.join(feats)}" if feats else ""))
        return 0
    f = _feature(ws, args)
    notes = _revalidate(f)
    d = _status_data(f)
    d["revalidation"] = notes
    if args.json:
        _print_json(d)
    else:
        for n in notes:
            print(f"! {n}")
        print(_format_status(d))
    return 0


def cmd_resume(ws: Workspace, args) -> int:
    from runtime.common import current_branch
    from runtime.state.machine import touch_git

    f = _feature(ws, args)
    checks: List[str] = []
    checks += [f"event log: {p}" for p in f.verify_chain()]
    checks += _revalidate(f)
    st = f.state()
    fp = fingerprint(ws.root)
    last = st["git"].get("last_seen_head")
    if last and fp["commit_sha"] and last != fp["commit_sha"]:
        checks.append(f"HEAD moved since last recorded: {last[:10]} -> {fp['commit_sha'][:10]} (check for unrecorded commits)")
    if st["git"].get("branch") and fp["git"]:
        br = current_branch(ws.root)
        if br != st["git"]["branch"]:
            checks.append(f"branch changed: recorded {st['git']['branch']} / current {br}")
    if fp.get("dirty"):
        checks.append("uncommitted changes: " + ", ".join(fp["dirty_paths"][:8]))
    for t in f.task_graph().get("tasks", []):
        ev = t.get("verified_evidence") or {}
        if t.get("status") == "verified" and fp["git"] and ev.get("code_tree") != fp["code_tree"]:
            checks.append(f"{t['id']}: code changed after it was verified (re-verify during integration)")
    for tid, wt in (st.get("parallel") or {}).get("worktrees", {}).items():
        if wt.get("status") != "active":
            continue
        wpath = Path(wt["path"])
        if not wpath.exists():
            checks.append(f"{tid}: worktree {wpath} is missing (discard it with `hr worktree remove {tid} --force`)")
            continue
        wfp = fingerprint(wpath)
        if wfp.get("dirty"):
            checks.append(f"{tid}: worktree has uncommitted changes ({', '.join(wfp['dirty_paths'][:5])})")
        ev = next((t.get("verified_evidence") for t in f.task_graph().get("tasks", []) if t["id"] == tid), None) or {}
        if ev and ev.get("code_tree") != wfp.get("code_tree"):
            checks.append(f"{tid}: worktree code changed after verification (re-verify before merging)")
    if st["github"].get("prs") or st["github"].get("feature_issue"):
        from runtime.adapters.github import gh

        av = gh.availability(f)
        if not av["available"]:
            checks.append("GitHub state not checked: " + av["reason"])
        else:
            for key, v in st["github"].get("prs", {}).items():
                d = gh.pr_live(f, v["number"])
                checks.append(f"PR #{v['number']} ({key}): " + (d.get("error") or
                              f"{d.get('state')}{' draft' if d.get('isDraft') else ''}, "
                              f"CI {d['checks']['failing']} failing / {d['checks']['pending']} pending"))
    touch_git(f, st)
    f.save_state(st)
    f.emit("resumed", checks=len(checks))
    ws.set_active(f.id)
    print(_format_status(_status_data(f)))
    print("\nresume checks:" if checks else "\nresume checks: stored state matches the real state")
    for c in checks:
        print(f"  - {c}")
    return 0


def cmd_transition(ws: Workspace, args) -> int:
    from runtime.state import machine

    f = _feature(ws, args)
    _revalidate(f)
    st = machine.transition(f, args.to, args.reason or "")
    print(f"{f.id}: -> {st['state']}")
    return 0


def cmd_plan_check(ws: Workspace, args) -> int:
    from runtime.verification.plan_check import check_plan

    f = _feature(ws, args)
    st = f.state()
    res = check_plan(f.requirements(), f.task_graph(), f.test_plan(), st.get("mode") or "L3")
    f.emit("plan_checked", ok=res["ok"], hard_fail=len(res["hard_fail"]), warnings=len(res["warnings"]))
    if args.json:
        _print_json(res)
    else:
        print("plan quality gate: " + ("PASS" if res["ok"] else "HARD FAIL"))
        for h in res["hard_fail"]:
            print(f"  x {h}")
        for w in res["warnings"]:
            print(f"  ! {w}")
    return 0 if res["ok"] else 3


def cmd_task(ws: Workspace, args) -> int:
    from runtime.verification import evidence
    from runtime.verification.plan_check import TASK_STATUSES

    f = _feature(ws, args)
    _revalidate(f)
    st = f.state()
    if args.status not in TASK_STATUSES:
        raise HRError(f"status must be one of {', '.join(TASK_STATUSES)}")
    graph = f.task_graph()
    task = next((t for t in graph.get("tasks", []) if t["id"] == args.task_id), None)
    if task is None:
        raise HRError(f"no such task: {args.task_id}")
    if args.status in ("in_progress", "implemented", "verified") and st["state"] not in ("executing", "verifying_tasks", "integrating"):
        raise GateError(f"implementation/verification status changes are only allowed in executing, verifying_tasks or integrating (current: {st['state']})")
    if args.status == "verified":
        from runtime.scheduler.worktrees import code_root

        lenient = st.get("mode") in ("L0", "L1")
        fp = fingerprint(code_root(f, st, task["id"]))
        if not lenient and (not fp["git"] or fp["dirty"]):
            raise GateError("verified needs test evidence on committed code (commit, then re-run `hr verify --task`)")
        tests = evidence.required_tests(f.test_plan(), task_id=task["id"], graph=graph)
        if not tests:
            raise GateError(f"{task['id']}: no required tests are linked to this task")
        summ = evidence.summarize(f.test_plan(), f.test_results(), fp, lenient=lenient, tests=tests)
        bad = [f"{r['test']['id']}={r['status']}" for r in summ["rows"] if not evidence.is_pass(r["status"], lenient)]
        if bad:
            raise GateError(f"{task['id']}: tests not passing on the current code: {', '.join(bad)}")
        task["verified_evidence"] = {
            "run_ids": [r["run"]["run_id"] for r in summ["rows"]],
            "commit_sha": fp["commit_sha"],
            "code_tree": fp["code_tree"],
            "worktree": (st.get("parallel") or {}).get("worktrees", {}).get(task["id"], {}).get("status") == "active",
            "verified_at": now(),
        }
    prev = task.get("status", "planned")
    task["status"] = args.status
    if args.note:
        task.setdefault("notes", []).append({"at": now(), "text": args.note})
    f.save("task_graph", graph)
    f.emit("task_status", task_id=task["id"], **{"from": prev, "to": args.status}, note=args.note or "")
    print(f"{task['id']}: {prev} -> {args.status}")
    return 0


def _next_test_id(plan: Dict[str, Any]) -> str:
    nums = [int(t["id"].split("-")[1]) for t in plan.get("tests", [])
            if t.get("id", "").startswith("TEST-") and t["id"].split("-")[1].isdigit()]
    return f"TEST-{(max(nums) + 1 if nums else 1):03d}"


def cmd_verify(ws: Workspace, args) -> int:
    from runtime.verification import evidence, runner

    f = _feature(ws, args)
    _revalidate(f)
    st = f.state()
    cfg = ws.config().get("verification", {})
    plan = f.test_plan()
    if args.adhoc:
        if st["approvals"].get("design"):
            raise GateError("an approved test plan cannot be changed with --adhoc - edit test-plan.json and get re-approval")
        tid = args.adhoc_id or _next_test_id(plan)
        if not any(t["id"] == tid for t in plan.get("tests", [])):
            plan.setdefault("tests", []).append({
                "id": tid, "title": args.title or args.adhoc, "type": args.type,
                "level": args.level if args.level != "all" else "task",
                "command": args.adhoc, "pass_criteria": "exit code 0", "required": True,
                "requirement_ids": [], "task_ids": [args.task] if args.task else [],
            })
            f.save("test_plan", plan)
        args.test = [tid]
    tests = []
    if args.tasks:
        pass
    elif args.test:
        wanted = set(args.test)
        tests = [t for t in plan.get("tests", []) if t["id"] in wanted]
        missing = wanted - {t["id"] for t in tests}
        if missing:
            raise HRError("tests not in the test plan: " + ", ".join(sorted(missing)))
    else:
        tests = evidence.required_tests(plan, level=None if args.level == "all" else args.level,
                                        task_id=args.task, graph=f.task_graph())
    from runtime.scheduler.worktrees import code_root

    parallel = args.parallel if args.parallel is not None else int(cfg.get("max_parallel_tests", 4))
    timeout = args.timeout or int(cfg.get("default_timeout_seconds", 900))
    retries = int(cfg.get("max_same_failure_retries", 3))
    if args.tasks:
        jobs = []
        for tid in args.tasks:
            root_t = code_root(f, st, tid)
            wt = tid if root_t != ws.root else None
            for t in evidence.required_tests(plan, task_id=tid, graph=f.task_graph()):
                jobs.append({"test": t, "cwd": root_t, "worktree_task": wt})
        if not jobs:
            raise HRError("no tests to run")
        runs = runner.run_jobs(f, jobs, timeout, args.env, retries, parallel)
    else:
        if not tests:
            raise HRError("no tests to run")
        root_t = code_root(f, st, args.task)
        runs = runner.run_tests(f, tests, timeout, args.env, retries, cwd=root_t,
                                worktree_task=args.task if root_t != ws.root else None, max_parallel=parallel)
    failed = 0
    for r in runs:
        mark = {"passed": "PASS", "failed": "FAIL", "manual_required": "MANUAL"}.get(r["status"], r["status"])
        line = f"[{mark}] {r['test_id']}" + (f" (worktree {r['worktree_task']})" if r.get("worktree_task") else "")
        if r.get("concurrency", 1) > 1:
            line += f" [parallel x{r['concurrency']}]"
        if r.get("exit_code") is not None:
            line += f"  exit={r['exit_code']} {r.get('duration_s')}s  log={r.get('log_ref')}"
        if r.get("note"):
            line += f"\n        {r['note']}"
        if r.get("failure"):
            fl = r["failure"]
            line += (f"\n        failure record {fl['id']} ({fl['retry_count']} in a row)"
                     + (" - escalated to a human, state is now blocked" if fl["escalated"] else ""))
        print(line)
        if r["status"] == "failed":
            failed += 1
            for tl in (r.get("output_tail") or "").strip().splitlines()[-15:]:
                print(f"        | {tl}")
    return 1 if failed else 0


def cmd_record_manual(ws: Workspace, args) -> int:
    from runtime.verification import runner

    f = _feature(ws, args)
    test = next((t for t in f.test_plan().get("tests", []) if t["id"] == args.test_id), None)
    if test is None:
        raise HRError(f"no such test: {args.test_id}")
    cfg = ws.config().get("verification", {})
    run = runner.record_manual(f, test, args.result == "passed", args.by, args.note or "", args.evidence, args.env,
                               int(cfg.get("max_same_failure_retries", 3)))
    print(f"{run['run_id']} {test['id']} = {run['status']} (reviewer: {args.by})")
    return 0


def cmd_failures(ws: Workspace, args) -> int:
    from runtime.verification import failures

    f = _feature(ws, args)
    if args.classify:
        res = failures.classify(f, args.classify, args.cause_type, args.cause, args.suspect, args.fix_task, args.retest)
        print(f"{args.classify}: {res['guidance']}")
        if res["next_state"]:
            print(f"  suggested next state: hr transition {res['next_state']}")
        return 0
    rows = f.failures().get("failures", [])
    if args.json:
        _print_json(rows)
        return 0
    if not rows:
        print("no failure records")
    for x in rows:
        print(f"{x['id']} [{x['status']}] {x['test_id']} x{x['retry_count']} | cause {x['cause_type']}"
              f" | suspect {', '.join(x.get('suspect_tasks', [])) or '-'} | fix {x.get('fix_task') or '-'}")
    return 0


def cmd_approve(ws: Workspace, args) -> int:
    from runtime.approvals import gates
    from runtime.state import machine

    f = _feature(ws, args)
    _revalidate(f)
    st = f.state()
    if args.gate == "design":
        rec = gates.approve_design(f, st, args.by, args.scope or "", args.note or "")
        f.save_state(st)
        print(f"design approval recorded: {args.by} | bundle {rec['bundle_hash'][:12]}")
        machine.transition(f, "executing", "design approved", actor=f"human:{args.by}")
        print("state -> executing")
    else:
        rec = gates.approve_final(f, st, args.by, args.risks or "", args.note or "")
        f.save_state(st)
        print(f"final approval recorded: {args.by} | commit {rec['commit_sha'][:10]}")
        machine.transition(f, "ready_to_merge", "final approval", actor=f"human:{args.by}")
        print("state -> ready_to_merge (merging follows repository rules and `hr merge-check`)")
    return 0


def cmd_reject(ws: Workspace, args) -> int:
    from runtime.state import machine

    f = _feature(ws, args)
    st = f.state()
    expected = "awaiting_design_approval" if args.gate == "design" else "awaiting_final_approval"
    if st["state"] != expected:
        raise GateError(f"a {args.gate} change request is recorded only in {expected} (current: {st['state']})")
    target = args.to or ("clarifying" if args.gate == "design" else "rework_required")
    f.emit("approval_rejected", gate=args.gate, reason=args.reason, by=args.by or "user (chat)")
    machine.transition(f, target, f"{args.gate} change requested: {args.reason}")
    print(f"change request recorded | state -> {target}")
    return 0


def cmd_unblock(ws: Workspace, args) -> int:
    from runtime.state import machine

    f = _feature(ws, args)
    st = machine.unblock(f, args.by, args.note or "")
    print(f"unblocked -> {st['state']}")
    return 0


def cmd_scope_change(ws: Workspace, args) -> int:
    from runtime.state import machine

    f = _feature(ws, args)
    f.emit("scope_change_requested", task_id=args.task, reason=args.reason)
    st = machine.transition(f, "clarifying", f"scope change requested ({args.task or '-'}): {args.reason}")
    print(f"scope change recorded | state -> {st['state']} (reclassify with hr classify)")
    return 0


def cmd_render(ws: Workspace, args) -> int:
    from runtime import docs

    f = _feature(ws, args)
    _revalidate(f)
    updated = docs.render(f)
    print("updated: " + (", ".join(updated) if updated else "nothing (no hr:* blocks found)"))
    return 0


def cmd_doc_check(ws: Workspace, args) -> int:
    from runtime import docs

    f = _feature(ws, args)
    res = docs.check_docs(f)
    print("document quality gate: " + ("PASS" if not res["errors"] else "FAIL"))
    for e in res["errors"]:
        print(f"  x {e}")
    for w in res["warnings"]:
        print(f"  ! {w}")
    return 0 if not res["errors"] else 3


def cmd_check(ws: Workspace, args) -> int:
    from runtime import docs, schema_check
    from runtime.verification.plan_check import check_plan

    f = _feature(ws, args)
    problems: List[str] = []
    problems += [f"[events] {p}" for p in f.verify_chain()]
    sch = schema_check.validate(f)
    if sch is None:
        print("schema validation: skipped (pip install jsonschema to enable)")
    else:
        problems += [f"[schema] {p}" for p in sch]
    problems += [f"[approval] {n}" for n in _revalidate(f)]
    st = f.state()
    if st.get("mode") in ("L2", "L3") and f.path("task_graph").exists():
        problems += [f"[plan] {p}" for p in check_plan(f.requirements(), f.task_graph(), f.test_plan(), st["mode"])["hard_fail"]]
    problems += [f"[docs] {p}" for p in docs.check_docs(f)["errors"]]
    print("integrity check: " + ("OK" if not problems else f"{len(problems)} problem(s)"))
    for p in problems:
        print(f"  - {p}")
    return 0 if not problems else 3


def cmd_log(ws: Workspace, args) -> int:
    f = _feature(ws, args)
    skip = ("seq", "event", "feature_id", "timestamp", "hash", "prev_hash", "actor")
    for ev in f.events()[-args.n:]:
        extra = {k: v for k, v in ev.items() if k not in skip}
        print(f"#{ev.get('seq')} {ev.get('timestamp')} {ev.get('event')} [{ev.get('actor')}] {json.dumps(extra, ensure_ascii=False)}")
    return 0


def cmd_gh(ws: Workspace, args) -> int:
    from runtime.adapters.github import gh

    f = _feature(ws, args)
    st = f.state()
    if args.gh_cmd == "status":
        _print_json(gh.availability(f))
        return 0
    if args.gh_cmd == "create-issues":
        items = gh.create_issues(f, st, args.dry_run)
        f.save_state(st)
        for i in items:
            print(f"{'(dry-run) ' if args.dry_run else ''}{i['kind']}: {i['title']}")
        return 0
    if args.gh_cmd == "link":
        gh.link(f, st, args.task, args.issue, args.pr, args.commit)
        f.save_state(st)
        print("link recorded")
        return 0
    if args.gh_cmd == "sync":
        live = gh.sync(f, st)
        f.save_state(st)
        _print_json(live)
        return 0
    raise HRError("unknown gh command")


def cmd_merge_check(ws: Workspace, args) -> int:
    from runtime.adapters.github import gh

    f = _feature(ws, args)
    _revalidate(f)
    st = f.state()
    problems = gh.merge_check(f, st)
    auto = ws.config().get("github", {}).get("auto_merge", False)
    if problems:
        print("merge not allowed:")
        for p in problems:
            print(f"  - {p}")
        return 3
    print("no merge blockers. " + ("auto_merge=true: merge is allowed" if auto
                                  else "auto_merge=false: a human merges, or explicitly tells the agent to"))
    return 0


def cmd_abort(ws: Workspace, args) -> int:
    from runtime.state import machine

    f = _feature(ws, args)
    st = machine.transition(f, "cancelled", args.reason or "aborted by user")
    if ws.active_feature_id() == f.id:
        ws.set_active(None)
    print(f"{f.id}: cancelled. Records ({f.dir}) and the work branch ({st['git'].get('branch') or '-'}) are kept.")
    return 0


def cmd_schedule(ws: Workspace, args) -> int:
    from runtime.scheduler import dag, worktrees

    f = _feature(ws, args)
    _revalidate(f)
    st = f.state()
    cfg = ws.config().get("scheduler", {})
    max_par = args.max or int(cfg.get("max_parallel_tasks", 3))
    plan = dag.plan_batch(f.task_graph(), (st.get("parallel") or {}).get("worktrees", {}), max_par)
    briefs = []
    if args.start:
        if st["state"] != "executing":
            raise GateError(f"tasks are started only in executing (current: {st['state']})")
        if not plan["batch"]:
            raise GateError("nothing can start now: "
                            + json.dumps({"deferred": plan["deferred"], "waiting": plan["waiting"]}, ensure_ascii=False))
        started = []
        try:
            for tid in plan["batch"]:
                worktrees.create(f, st, tid)
                started.append(tid)
        finally:
            if started:
                st.setdefault("parallel", {}).setdefault("batches", []).append({"tasks": started, "at": now()})
                f.save_state(st)
                f.emit("batch_scheduled", tasks=started, deferred=sorted(plan["deferred"]))
        briefs = [worktrees.brief(f, st, tid) for tid in started]
    if args.json:
        _print_json({**plan, "briefs": briefs})
        return 0
    print(f"running: {', '.join(plan['running']) or 'none'}")
    print(f"{'started' if args.start else 'next batch'}: {', '.join(plan['batch']) or 'none'}")
    for tid, why in plan["deferred"].items():
        print(f"  deferred {tid}: {'; '.join(why)}")
    for tid, deps in plan["waiting"].items():
        print(f"  waiting {tid}: needs {', '.join(deps)} verified and merged")
    for b in briefs:
        print(f"\n----- brief for {b['task_id']} -----\n{b['prompt']}")
    return 0


def cmd_worktree(ws: Workspace, args) -> int:
    from runtime.scheduler import worktrees

    f = _feature(ws, args)
    _revalidate(f)
    st = f.state()
    if args.wt_cmd == "list":
        rows = (st.get("parallel") or {}).get("worktrees", {})
        if args.json:
            _print_json(rows)
            return 0
        if not rows:
            print("no worktrees")
        for tid, w in sorted(rows.items()):
            print(f"{tid} [{w['status']}] {w['branch']}  {w['path']}" + (f"  ({w['status_note']})" if w.get("status_note") else ""))
        return 0
    if not args.task_id:
        raise HRError("task id required")
    if args.wt_cmd == "brief":
        b = worktrees.brief(f, st, args.task_id)
        if args.json:
            _print_json(b)
        else:
            print(b["prompt"])
        return 0
    if args.wt_cmd == "create":
        rec = worktrees.create(f, st, args.task_id)
        f.save_state(st)
        print(f"{args.task_id}: worktree {rec['path']} on {rec['branch']}")
        return 0
    if args.wt_cmd == "merge":
        rec = worktrees.merge(f, st, args.task_id)
        f.save_state(st)
        print(f"{args.task_id}: merged {rec['branch']} into {rec['integration_branch']} @ {rec['merged_into'][:10]}")
        if args.remove:
            worktrees.remove(f, st, args.task_id, force=False)
            f.save_state(st)
            print(f"{args.task_id}: worktree removed")
        return 0
    if args.wt_cmd == "remove":
        rec = worktrees.remove(f, st, args.task_id, args.force)
        f.save_state(st)
        print(f"{args.task_id}: worktree {rec['status']}")
        return 0
    raise HRError("unknown worktree command")


def cmd_metrics(ws: Workspace, args) -> int:
    from runtime import metrics

    if args.m_cmd == "record":
        f = _feature(ws, args)
        if args.kind not in metrics.MANUAL_KINDS:
            raise HRError(f"--kind must be one of {', '.join(metrics.MANUAL_KINDS)}")
        f.emit("metric_recorded", kind=args.kind, value=args.value, note=args.note or "", actor=args.by or "agent")
        print(f"recorded {args.kind}={args.value:g}")
        return 0
    fd = metrics.fmt_duration
    if args.all:
        ws.require_init()
        data = metrics.aggregate(ws)
        if args.json:
            _print_json(data)
            return 0
        print(f"features {data['features']} (completed {data['completed']})  |  mean verification coverage "
              f"{data['mean_verification_coverage']}  |  tokens {data['total_tokens']:.0f}  |  test time {fd(data['total_test_seconds'])}")
        for m, v in data["by_mode"].items():
            print(f"  {m}: {v['features']} done, lead {fd(v['mean_lead_time_s'])}, approval wait "
                  f"{fd(v['mean_approval_wait_s'])}, rework {v['mean_rework_rate']}, escaped defects {v['escaped_defects']:.0f}")
        return 0
    f = _feature(ws, args)
    d = metrics.feature_metrics(f)
    if args.json:
        _print_json(d)
        return 0
    print(f"{d['feature_id']} ({d.get('mode')}, {d.get('state')})")
    print(f"  lead time {fd(d['lead_time_s'])}  |  approval wait {fd(d['approval_wait_s'])}  |  "
          f"escalation wait {fd(d['escalation_wait_s'])}  |  human review {d['human_review_minutes']:.0f} min (recorded)")
    print(f"  rework rate {d['rework_rate']}  |  failures {d['failures']}  |  invalidations {d['invalidations']}  |  "
          f"rejections {d['rejections']}  |  scope changes {d['scope_changes']}  |  reclassifications {d['reclassifications']}")
    print(f"  test runs {d['test_runs']} ({d['failed_runs']} failed, {fd(d['test_seconds'])})  |  "
          f"verification coverage {d['verification_coverage']}")
    print(f"  escaped defects {d['escaped_defects']:.0f}  |  intent mismatch {d['intent_mismatch']:.0f}  |  "
          f"unnecessary question rate {d['unnecessary_question_rate']}  |  tokens {d['tokens']:.0f}  |  agent time {fd(d['agent_seconds'])}")
    for b in d["parallel_batches"]:
        print(f"  parallel batch {', '.join(b['tasks'])}: serial {fd(b['serial_s'])} vs wall {fd(b['wall_s'])} (x{b['speedup']})")
    return 0


def cmd_templates(ws: Workspace, args) -> int:
    from runtime import templates_dist as td

    ws.require_init()
    if args.t_cmd == "status":
        for r in td.status(ws, args.source):
            flags = [k for k in ("installed", "customized", "outdated") if r[k]]
            print(f"{r['name']:24} {', '.join(flags) or 'not installed (plugin default in use)'}")
        return 0
    res = td.install(ws, args.source, args.force)
    for k, v in res.items():
        if v:
            print(f"{k}: {', '.join(v)}")
    if res["kept_customized"]:
        print("(customized templates were kept; --force overwrites them)")
    return 0


def cmd_scaffold(ws: Workspace, args) -> int:
    from runtime import templates_dist as td

    f = _feature(ws, args)
    res = td.scaffold(f, args.docs, args.overwrite)
    print("created: " + (", ".join(res["created"]) or "nothing"))
    if res["skipped_existing"]:
        print("kept existing: " + ", ".join(res["skipped_existing"]))
    return 0


def cmd_flag(ws: Workspace, args) -> int:
    from runtime import redpill

    f = _feature(ws, args)
    print(redpill.flag(f, args.item, args.by, args.note or ""))
    return 0


def cmd_redpill(ws: Workspace, args) -> int:
    from runtime import redpill

    ws.require_init()
    if args.redpill_cmd == "on":
        values = {"enabled": True}
        if args.one_in is not None:
            if args.one_in < 1:
                raise HRError("--one-in must be at least 1")
            values["one_in"] = args.one_in
        if args.gates:
            gates = [g.strip() for g in args.gates.split(",") if g.strip()]
            if not gates or any(g not in ("design", "final") for g in gates):
                raise HRError("--gates takes design, final, or design,final")
            values["gates"] = gates
        if args.language:
            values["language"] = args.language
        redpill.set_config(ws, values)
    elif args.redpill_cmd == "off":
        redpill.set_config(ws, {"enabled": False})
    elif args.redpill_cmd == "reveal":
        print(redpill.reveal(_feature(ws, args), args.by))
        return 0
    s = redpill.settings(ws)
    print(f"Red pill mode: {'on' if s['enabled'] else 'off'}  |  about 1 in {s['one_in']} approval requests  |  "
          f"gates: {', '.join(s['gates'])}  |  language: {s['language']}")
    fid = getattr(args, "feature", None) or ws.active_feature_id()
    if fid:
        st = redpill.stats(ws.resolve(fid))
        print(f"{fid}: drills {st['drills']}, caught {st['caught']}, missed {st['missed']}, "
              f"rubber stamps {st['rubber_stamps']}, catch rate {st['catch_rate']}")
    return 0


def cmd_list(ws: Workspace, args) -> int:
    ws.require_init()
    active = ws.active_feature_id()
    for fid in ws.list_features():
        st = Feature(ws, fid).state()
        print(f"{'*' if fid == active else ' '} {fid}  {st.get('mode') or '--'}  {st['state']}  {st['title']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hr", description="human-rights workflow executor")
    p.add_argument("--root", help="repository root (default: git root of the current directory)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name: str, fn, help_: str, feature: bool = True) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help_)
        if feature:
            sp.add_argument("-f", "--feature", help="FEAT-NNN (default: active feature)")
        sp.set_defaults(fn=fn)
        return sp

    add("init", cmd_init, "initialize .workflow/", feature=False)
    sp = add("new", cmd_new, "create a feature (-> triaging)", feature=False)
    sp.add_argument("title")
    sp.add_argument("--slug")
    sp.add_argument("--request")
    sp = add("classify", cmd_classify, "Adaptive Router (re)classification")
    sp.add_argument("--axes", required=True, help="JSON, @file, or - (stdin)")
    sp.add_argument("--flags", help="physical_safety,vehicle_command,auth,secrets,destructive_migration,irreversible_external")
    sp.add_argument("--note")
    sp = add("status", cmd_status, "current status")
    sp.add_argument("--json", action="store_true")
    add("list", cmd_list, "list features", feature=False)
    add("resume", cmd_resume, "reconcile stored state with real git/GitHub state, then resume")
    sp = add("transition", cmd_transition, "state transition (guarded)")
    sp.add_argument("to")
    sp.add_argument("--reason")
    sp = add("plan-check", cmd_plan_check, "plan quality hard gate")
    sp.add_argument("--json", action="store_true")
    sp = add("task", cmd_task, "set task status (verified requires evidence)")
    sp.add_argument("task_id")
    sp.add_argument("status")
    sp.add_argument("--note")
    sp = add("verify", cmd_verify, "run tests and record bound evidence")
    sp.add_argument("--test", nargs="*")
    sp.add_argument("--task", help="one task's tests (in its worktree if it has one)")
    sp.add_argument("--tasks", nargs="+", help="several tasks at once, each in its own worktree")
    sp.add_argument("--parallel", type=int, help="max concurrent tests (default: verification.max_parallel_tests)")
    sp.add_argument("--level", choices=("task", "integration", "all"), default="all")
    sp.add_argument("--adhoc", help="L0/L1: add a command to the test plan and run it")
    sp.add_argument("--adhoc-id")
    sp.add_argument("--title")
    sp.add_argument("--type", default="regression")
    sp.add_argument("--env", default="local")
    sp.add_argument("--timeout", type=int)
    sp = add("record-manual", cmd_record_manual, "[human only] record a manual test result")
    sp.add_argument("test_id")
    sp.add_argument("result", choices=("passed", "failed"))
    sp.add_argument("--by", required=True)
    sp.add_argument("--note")
    sp.add_argument("--evidence")
    sp.add_argument("--env", default="manual")
    sp = add("failures", cmd_failures, "list / classify failure records")
    sp.add_argument("--classify", metavar="FAIL-ID")
    sp.add_argument("--cause-type", default="unclassified")
    sp.add_argument("--cause")
    sp.add_argument("--suspect")
    sp.add_argument("--fix-task")
    sp.add_argument("--retest")
    sp.add_argument("--json", action="store_true")
    sp = add("approve", cmd_approve, "[human only] design / final approval")
    sp.add_argument("gate", choices=("design", "final"))
    sp.add_argument("--by", required=True)
    sp.add_argument("--scope")
    sp.add_argument("--note")
    sp.add_argument("--risks", help="residual risks accepted with the final approval")
    sp = add("reject", cmd_reject, "record a human change request on an approval item")
    sp.add_argument("gate", choices=("design", "final"))
    sp.add_argument("--reason", required=True)
    sp.add_argument("--to", choices=("clarifying", "planning", "investigating", "rework_required"))
    sp.add_argument("--by")
    sp = add("unblock", cmd_unblock, "[human only] release an escalation")
    sp.add_argument("--by", required=True)
    sp.add_argument("--note")
    sp = add("scope-change", cmd_scope_change, "change outside the task boundary found -> scope change request")
    sp.add_argument("--task")
    sp.add_argument("--reason", required=True)
    add("render", cmd_render, "refresh hr:* blocks in human docs from evidence")
    add("doc-check", cmd_doc_check, "document quality gate (structural checks)")
    add("check", cmd_check, "integrity check (event chain, schema, approvals, plan, docs)")
    sp = add("log", cmd_log, "recent events")
    sp.add_argument("-n", type=int, default=20)
    sp = add("gh", cmd_gh, "GitHub integration")
    sp.add_argument("gh_cmd", choices=("status", "create-issues", "link", "sync"))
    sp.add_argument("--dry-run", action="store_true")
    sp.add_argument("--task")
    sp.add_argument("--issue", type=int)
    sp.add_argument("--pr", type=int)
    sp.add_argument("--commit")
    sp = add("schedule", cmd_schedule, "next conflict-free batch of tasks from the DAG (--start creates worktrees)")
    sp.add_argument("--start", action="store_true")
    sp.add_argument("--max", type=int)
    sp.add_argument("--json", action="store_true")
    sp = add("worktree", cmd_worktree, "task worktrees: create / merge / remove / list / brief")
    sp.add_argument("wt_cmd", choices=("create", "merge", "remove", "list", "brief"))
    sp.add_argument("task_id", nargs="?")
    sp.add_argument("--force", action="store_true")
    sp.add_argument("--remove", action="store_true", help="with merge: remove the worktree afterwards")
    sp.add_argument("--json", action="store_true")
    sp = add("metrics", cmd_metrics, "time, rework, coverage and cost metrics (record: host-reported values)")
    sp.add_argument("m_cmd", nargs="?", choices=("show", "record"), default="show")
    sp.add_argument("--all", action="store_true")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--kind")
    sp.add_argument("--value", type=float, default=1)
    sp.add_argument("--note")
    sp.add_argument("--by")
    sp = add("templates", cmd_templates, "install / update / status of the repo's shared templates", feature=False)
    sp.add_argument("t_cmd", choices=("install", "update", "status"))
    sp.add_argument("--from", dest="source", help="template pack directory (default: the plugin's)")
    sp.add_argument("--force", action="store_true")
    sp = add("scaffold", cmd_scaffold, "create feature docs from templates (repo templates first)")
    sp.add_argument("docs", nargs="*", help="overview requirements design verification codebase research tasks l0-summary review-report")
    sp.add_argument("--overwrite", action="store_true")
    sp = add("flag", cmd_flag, "[human only] point at an item in the approval material you would not approve")
    sp.add_argument("item")
    sp.add_argument("--by", required=True)
    sp.add_argument("--note")
    sp = add("redpill", cmd_redpill, "red pill mode: random review-vigilance drills (on/off/reveal are human only)")
    sp.add_argument("redpill_cmd", choices=("on", "off", "status", "reveal"))
    sp.add_argument("--one-in", type=int, help="plant a drill in about 1 of N approval requests")
    sp.add_argument("--gates", help="design, final, or design,final")
    sp.add_argument("--language", help="en or ko (default: docs.language)")
    sp.add_argument("--by")
    add("merge-check", cmd_merge_check, "can this be merged? (approved code, live GitHub state)")
    sp = add("abort", cmd_abort, "cancel (records and branch are kept)")
    sp.add_argument("--reason")
    return p


READ_ONLY = {"init", "list", "doc-check", "log"}


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve() if args.root else find_repo_root(Path.cwd())
    ws = Workspace(root)
    try:
        if ws.initialized:
            ws.ensure_wrappers()
        if args.cmd not in READ_ONLY and ws.initialized:
            with ws.lock():
                return args.fn(ws, args)
        return args.fn(ws, args)
    except GateError as exc:
        print(f"[blocked] {exc}", file=sys.stderr)
        return 3
    except HRError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2
