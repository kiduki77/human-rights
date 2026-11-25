from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from runtime.common import GateError, HRError, find_repo_root, fingerprint, now
from runtime.state.store import Feature, Workspace, new_state

HUMAN_ONLY = ("approve", "record-manual", "unblock")
GATE_STATES = {"design": "awaiting_design_approval", "final": "awaiting_final_approval",
               "split": "awaiting_split_approval"}


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
    from runtime.config import preset_values, set_section

    if args.language and args.language not in ("en", "ko"):
        raise HRError("--language takes en or ko")
    try:
        agent_values = preset_values(args.agents) if args.agents else None
    except ValueError as exc:
        raise HRError(str(exc))
    drill = _redpill_values(args.redpill, args.redpill_difficulty, args.redpill_one_in)
    created = ws.init()
    if drill:
        from runtime import redpill

        redpill.set_config(ws, drill, {"by": "hr init", "via": "init"})
    if args.language:
        set_section(ws.config_path, "docs", {"language": args.language})
    if agent_values:
        set_section(ws.config_path, "agents", agent_values)
    print(f"human-rights workspace: {ws.wf}")
    for c in created:
        print(f"  created: {c}")
    print(f"report language: {(ws.config().get('docs') or {}).get('language', 'en')}")
    _print_agents(ws)
    _print_redpill(ws)
    print("Human decisions (approve / flag / record-manual / unblock / redpill) are made in chat; the agent records them with `--quote`.")
    return 0


def _redpill_values(switch: Optional[str], difficulty: Optional[str], one_in: Optional[int],
                    author: Optional[str] = None, max_flags: Optional[int] = None) -> Dict[str, Any]:
    from runtime import redpill

    values: Dict[str, Any] = {}
    if switch:
        if switch not in ("on", "off"):
            raise HRError("--redpill takes on or off")
        values["enabled"] = switch == "on"
    if difficulty:
        if difficulty not in redpill.DIFFICULTY_CHOICES:
            raise HRError("difficulty takes " + ", ".join(redpill.DIFFICULTY_CHOICES))
        values["difficulty"] = difficulty
    if one_in is not None:
        if one_in < 1:
            raise HRError("--one-in must be at least 1")
        values["one_in"] = one_in
    if author:
        if author not in redpill.AUTHORS:
            raise HRError("--author takes " + " or ".join(redpill.AUTHORS))
        values["author"] = author
    if max_flags is not None:
        if max_flags < 1:
            raise HRError("--max-flags must be at least 1")
        values["max_flags"] = max_flags
    return values


def _print_redpill(ws: Workspace) -> None:
    from runtime import redpill

    s = redpill.settings(ws)
    shown = s["difficulty"] if s["difficulty"] != "adaptive" else f"adaptive (now {redpill.level(ws)})"
    print(f"Red pill mode: {'on' if s['enabled'] else 'off'}  |  about 1 in {s['one_in']} approval requests  |  "
          f"difficulty: {shown}  |  gates: {', '.join(s['gates'])}  |  drills written by: {s['author']}  |  "
          f"language: {s['language']}  |  a catch naming more than {s['max_flags']} rows is not counted")


def _print_reviews(r: Dict[str, Any], indent: str = "") -> None:
    per = f" ({r['rows_not_plant_per_approval']} per approval)" if r["approvals"] else ""
    print(f"{indent}approvals {r['approvals']} (drills off for {r['approvals_drills_off']}), "
          f"{r['approvals_naming_rows']} named at least one row  |  rows named that were not the plant: "
          f"{r['rows_not_plant']}{per}")


def _print_off(prog: Dict[str, Any], indent: str = "") -> None:
    from runtime.metrics import fmt_duration
    from runtime.redpill import LOG_FILE

    if prog["off_periods"]:
        print(f"{indent}drills were off for {fmt_duration(prog['off_seconds'])} in {len(prog['off_periods'])} "
              f"period{'' if len(prog['off_periods']) == 1 else 's'}:")
    for p in prog["off_periods"]:
        reason = p["reason"] or ("no reason recorded" if p["via"] != "init" else "set through hr init")
        print(f"{indent}  {p['from']} to {p['to'] or 'now'} ({fmt_duration(p['seconds'])}), by {p['by']}: {reason}")
    if prog["setting_changes"]:
        print(f"{indent}settings changed {prog['setting_changes']} time{'' if prog['setting_changes'] == 1 else 's'} "
              f"(.human-rights/{LOG_FILE} has each change)")


def _print_agents(ws: Workspace) -> None:
    from runtime.config import agent_settings

    preset = (ws.config().get("agents") or {}).get("preset") or "custom"
    print(f"sub-agents (preset: {preset}):")
    for role, a in agent_settings(ws.config()).items():
        extra = f"  [!] {'; '.join(a['problems'])}" if a["problems"] else ""
        print(f"  {a['agent']:<17} model {a['model']:<8} effort {a['effort'] or 'default'}{extra}")


def cmd_agents(ws: Workspace, args) -> int:
    from runtime.config import agent_settings

    ws.require_init()
    if args.json:
        _print_json(agent_settings(ws.config()))
        return 0
    _print_agents(ws)
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
    from runtime.routing import floor
    from runtime.routing.router import apply_route, route

    f = _feature(ws, args)
    st = f.state()
    flags = [x.strip() for x in (args.flags or "").split(",") if x.strip()]
    if args.paths is None:
        declared = list((st.get("routing") or {}).get("declared_paths") or [])
    else:
        declared = [x.strip() for x in args.paths.split(",") if x.strip()]
    tampered = floor.problem(ws, st, history=True)
    if tampered:
        raise GateError(tampered)
    hits = floor.hits(floor.load(ws), floor.touched(ws, st, declared))
    result = route(_read_json_arg(args.axes), flags, ws.config(), hits)
    old_probe = (st.get("routing") or {}).get("probe")
    notes = apply_route(st, result, now())
    st["routing"]["declared_paths"] = declared
    probe = _probe(args, old_probe)
    st["routing"]["probe"] = probe
    st["routing"]["floor_seal"] = (floor.read_seal(ws) or {}).get("rules_sha256")
    st["size"] = _size_record(args.size, args.size_reason)
    f.save_state(st)
    f.emit("classified", mode=st["mode"], flags=result["flags"], effective_scores=result["effective_scores"],
           required_gates=st["required_gates"], note=args.note or "", size=st["size"], floor=result["floor"])
    gates = ", ".join(sorted({f"{g['gate']} ({g['reason']})" for g in st["gate_reasons"]})) or "none"
    print(f"mode: {st['mode']}  |  required gates: {gates}")
    for r in result["reasons"] + notes:
        print(f"  - {r}")
    if probe:
        others = probe["consumers"]
        print(f"  - other places that use {probe['concept'] or 'what this changes'}: "
              + (", ".join(others) if others else "none found") + f" (searched: {', '.join(probe['searched'])})")
    else:
        print("  - no search for other places that use what this changes was recorded (`--concept`, `--searched`, "
              "`--consumers`)")
    _print_size(st)
    return 0


def _size_record(size: Optional[str], reason: Optional[str]) -> Optional[Dict[str, Any]]:
    if not size:
        return None
    if not (reason or "").strip():
        raise HRError("--size needs --size-reason: what makes this one feature, or which separately verifiable "
                      "results it contains")
    return {"decision": size, "reason": reason.strip(), "at": now()}


def _print_size(st: Dict[str, Any]) -> None:
    from runtime.groups import SIZE_MODES

    size = st.get("size")
    if size:
        print(f"size: {size['decision']} - {size['reason']}")
        if size["decision"] == "compound":
            print("  next: `hr transition splitting`, then write .internal/split.json (see the splitting reference)")
    elif st.get("mode") in SIZE_MODES:
        print(f"size: not decided - {st['mode']} needs `--size single|compound --size-reason ...` before moving on")


def cmd_size(ws: Workspace, args) -> int:
    f = _feature(ws, args)
    st = f.state()
    if st["state"] not in ("triaging", "clarifying", "investigating", "planning"):
        raise GateError(f"the size is decided before the design is approved (current: {st['state']})")
    st["size"] = _size_record(args.size, args.reason)
    f.save_state(st)
    f.emit("sized", size=st["size"])
    _print_size(st)
    return 0


def cmd_split_check(ws: Workspace, args) -> int:
    from runtime import groups

    f = _feature(ws, args)
    res = groups.check_split(f)
    f.emit("split_checked", ok=res["ok"], hard_fail=len(res["hard_fail"]), warnings=len(res["warnings"]))
    if args.json:
        _print_json(res)
    else:
        print("split quality gate: " + ("PASS" if res["ok"] else "HARD FAIL"))
        for h in res["hard_fail"]:
            print(f"  x {h}")
        for w in res["warnings"]:
            print(f"  ! {w}")
    return 0 if res["ok"] else 3


def cmd_start(ws: Workspace, args) -> int:
    from runtime import groups
    from runtime.state import machine

    f = _feature(ws, args)
    st = f.state()
    if groups.is_group(st):
        _revalidate(f)
        st = f.state()
        row = groups.next_child(f, st)
        if not row:
            left = groups.unfinished(f, st)
            if not left:
                print(f"{f.id}: every feature is finished. Run the group checks: `hr transition integrating -f {f.id}`")
                return 0
            raise GateError(f"{f.id}: no feature can start now ({', '.join(left)})")
        f = Feature(ws, row["feature_id"])
        st = f.state()
    if st["state"] != "proposed":
        raise GateError(f"{f.id} is not waiting in a group (current: {st['state']})")
    machine.transition(f, "triaging", "started from its group")
    ws.set_active(f.id)
    b = groups.brief(f, f.state())
    if args.json:
        _print_json(b)
        return 0
    print(f"{f.id} started (part of {b['group']})")
    print(f"  result when done: {b['outcome']}")
    print(f"  verified on its own by: {b['verify_alone']}")
    if b["sources"]:
        print(f"  source: {b['source_document'] or '-'} {', '.join(str(s) for s in b['sources'])}")
    if b["code_status"]:
        print(f"  code today: {b['code_status']}")
    if b["built_on"]:
        print("  built on: " + ", ".join(f"{x['key']} ({x['feature_id']})" for x in b["built_on"]))
    for d in b["shared_decisions"]:
        print(f"  group decision {d.get('id', '')}: {d.get('question')} -> {d.get('answer')}")
    print("  Copy the group decisions into requirements.json (decided_by: group) instead of asking again. "
          "Then classify it like any request - including its own size.")
    return 0


def _status_data(f: Feature) -> Dict[str, Any]:
    from runtime import groups, redpill
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
        "kind": st.get("kind", "feature"),
        "parent": st.get("parent"),
        "size": st.get("size"),
        "split_approval": groups.split_status(f, st),
        "children": [{k: r[k] for k in ("key", "feature_id", "state", "mode", "title")}
                     for r in groups.ordered_children(f, st)],
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
    part = f"  |  part of {d['parent']}" if d.get("parent") else ""
    if d.get("kind") == "group":
        done = sum(1 for c in d["children"] if c["state"] == "completed")
        lines = [
            f"{d['feature_id']} — {d['title']}  [group]",
            f"state: {d['state_label']} ({d['state']}){part}",
            f"split approval: {ap(True, d['split_approval'])}  |  features: {done} of {len(d['children'])} done",
        ]
        lines += [f"  {c['feature_id']}  {c['mode'] or '--'}  {c['state']}  {c['title']}" for c in d["children"]]
        lines += [
            f"group checks {d['tests']['required']} {_fmt_counts(d['tests']['by_status'])}",
            f"unresolved failures: {', '.join(d['unresolved_failures']) or 'none'}  |  code: {git_line}",
        ]
    else:
        size = f"  |  size: {d['size']['decision']}" if d.get("size") else ""
        lines = [
            f"{d['feature_id']} — {d['title']}",
            f"state: {d['state_label']} ({d['state']})  |  mode: {d['mode'] or 'unclassified'}{size}{part}",
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
    before = f.id
    st = machine.transition(f, args.to, args.reason or "")
    if f.id != before:
        print(f"{before} is now {f.id}  ({f.dir})")
    print(f"{f.id}: -> {st['state']}")
    _after_child(ws, f, st)
    return 0


def _after_child(ws: Workspace, f: Feature, st: Dict[str, Any]) -> None:
    from runtime import groups

    if not st.get("parent") or st["state"] not in groups.DONE:
        return
    parent = Feature(ws, st["parent"])
    pst = parent.load("state")
    if not pst:
        return
    if ws.active_feature_id() in (f.id, None):
        ws.set_active(parent.id)
    left = groups.unfinished(parent, pst)
    if left:
        print(f"{parent.id}: {len(left)} feature(s) left. Next: `hr start -f {parent.id}`")
    else:
        print(f"{parent.id}: every feature is finished. Run the group checks: `hr transition integrating -f {parent.id}`")


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
        mark = {"passed": "PASS", "failed": "FAIL", "manual_required": "HUMAN",
                "agent_required": "AGENT"}.get(r["status"], r["status"])
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

    from runtime import human

    f = _feature(ws, args)
    test = next((t for t in f.test_plan().get("tests", []) if t["id"] == args.test_id), None)
    if test is None:
        raise HRError(f"no such test: {args.test_id}")
    who = human.resolve(ws, args.by, args.quote)
    cfg = ws.config().get("verification", {})
    if args.result == "passed":
        pending = _machine_tests_pending(f)
        if pending:
            raise GateError("machine tests come first: a human result is recorded only after every script and "
                            "agent test passes on the current code. Still open: " + ", ".join(pending))
    run = runner.record_manual(f, test, args.result == "passed", who["by"], args.note or "", args.evidence, args.env,
                               int(cfg.get("max_same_failure_retries", 3)), human.proof_fields(who))
    print(f"{run['run_id']} {test['id']} = {run['status']} (reviewer: {who['by']}, via {who['via']})")
    return 0


def _machine_tests_pending(f: Feature) -> List[str]:
    from runtime.verification import evidence

    st = f.state()
    lenient = st.get("mode") in ("L0", "L1")
    tests = [t for t in evidence.required_tests(f.test_plan()) if evidence.runner_of(t) != "human"]
    summ = evidence.summarize(f.test_plan(), f.test_results(), fingerprint(f.ws.root), lenient=lenient, tests=tests)
    return [f"{r['test']['id']}={r['status']}" for r in summ["rows"] if not evidence.is_pass(r["status"], lenient)]


def _agent_test(f: Feature, test_id: str) -> Dict[str, Any]:
    from runtime.verification import evidence

    test = next((t for t in f.test_plan().get("tests", []) if t["id"] == test_id), None)
    if test is None:
        raise HRError(f"no such test: {test_id}")
    if evidence.runner_of(test) != "agent":
        raise HRError(f"{test_id} is run by {evidence.runner_of(test)}, not by an agent")
    return test


def cmd_test_brief(ws: Workspace, args) -> int:
    from runtime.config import agent_settings
    from runtime.verification import runner

    f = _feature(ws, args)
    test = _agent_test(f, args.test_id)
    ev_dir = runner.evidence_dir(f, test["id"])
    ev_dir.mkdir(parents=True, exist_ok=True)
    rel = ev_dir.relative_to(ws.root).as_posix()
    steps = "\n".join(f"  {i}. DO: {s.get('do')}\n     PASS ONLY IF: {s.get('expect')}"
                      for i, s in enumerate(test.get("steps") or [], 1))
    prompt = (
        f"You are hr-tester. Run {test['id']} \"{test.get('title', '')}\" for feature {f.id}.\n"
        f"Repository root: {ws.root}\n"
        f"Environment: {test.get('environment') or 'not specified'}\n"
        f"Overall pass criteria (approved by the human, do not reinterpret): {test.get('pass_criteria')}\n\n"
        f"Steps, in order. Each step passes only if its stated result is observed exactly:\n{steps}\n\n"
        f"For every step save one evidence file (screenshot, recording, or captured output) under {rel}/ "
        f"named step-<n>.<ext>, taken at the moment the result is visible.\n"
        f"Then write {rel}/report.json:\n"
        '  {"by": "hr-tester", "steps": [{"status": "passed|failed", "observed": "<what you actually saw>", '
        '"evidence": "<path of the evidence file>"}, ...], "findings": ["<anything wrong you noticed outside the steps>"]}\n'
        "One entry per step, same order. Report what you saw, not what should have happened. If a step cannot be "
        "performed, mark it failed and say why. Do not edit code, do not fix anything, do not run hr."
    )
    out = {"test_id": test["id"], "evidence_dir": rel, "report": f"{rel}/report.json", "prompt": prompt,
           "agent": {"subagent_type": "hr-tester", **agent_settings(ws.config())["tester"]["agent_call"]}}
    if args.json:
        _print_json(out)
    else:
        print(prompt)
    return 0


def cmd_record_agent(ws: Workspace, args) -> int:
    from runtime.verification import runner

    f = _feature(ws, args)
    test = _agent_test(f, args.test_id)
    report_path = Path(args.report) if args.report else runner.evidence_dir(f, test["id"]) / "report.json"
    if not report_path.is_absolute():
        report_path = ws.root / report_path
    if not report_path.is_file():
        raise HRError(f"no report at {report_path}")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HRError(f"report is not valid JSON: {exc}")
    retries = int(ws.config().get("verification", {}).get("max_same_failure_retries", 3))
    run = runner.record_agent(f, test, report, retries)
    for s in run["steps"]:
        print(f"  step {s['n']}: {s['status']}  expect: {s['expect']}  observed: {s['observed']}")
    for x in run["findings"]:
        print(f"  finding: {x}")
    print(f"{run['run_id']} {test['id']} = {run['status']} (evidence: {run['evidence']})")
    if run.get("dirty"):
        print("  ran on uncommitted changes: counts for L0/L1 completion only")
    if run.get("failure"):
        fl = run["failure"]
        print(f"  failure record {fl['id']} ({fl['retry_count']} in a row)"
              + (" - escalated to a human, state is now blocked" if fl["escalated"] else ""))
    return 0 if run["status"] == "agent_passed" else 1


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


def _gate_since(f: Feature, args) -> Optional[str]:
    from runtime import human

    if args.quote is None:
        return None
    st = f.state()["state"]
    return human.entered_at(f, st) if st in GATE_STATES.values() or st == "blocked" else None


def _apply_flags(f: Feature, items: List[str], by: str, note: str, proof: Dict[str, Any]) -> Tuple[List[str], int]:
    from runtime import redpill

    results = redpill.flag_all(f, items, by, note, proof)
    for res in results:
        print(res["message"])
    return [r["item"] for r in results if not r["caught"]], len(results)


def cmd_approve(ws: Workspace, args) -> int:
    from runtime import human, redpill
    from runtime.approvals import gates
    from runtime.state import machine

    f = _feature(ws, args)
    _revalidate(f)
    expected = GATE_STATES[args.gate]
    current = f.state()["state"]
    if current != expected:
        raise GateError(f"{args.gate} approval is only possible in {expected} (current: {current})")
    who = human.resolve(ws, args.by, args.quote, _gate_since(f, args))
    by, proof = who["by"], human.proof_fields(who)
    concerns, named = _apply_flags(f, args.flag or [], by, args.note or "", proof)
    if concerns:
        if args.gate in ("design", "final"):
            redpill.record_decision(f, args.gate, by, named, False)
        raise GateError("not approved: the human pointed out " + ", ".join(concerns) + ". Address each point "
                        "(change the plan and resubmit, or explain why it is fine) and ask for approval again.")
    st = f.state()
    if args.gate == "split":
        from runtime import groups

        rec = groups.approve_split(f, st, by, args.note or "", proof)
        made = groups.sync_children(f, st)
        f.save_state(st)
        print(f"split approval recorded: {by} via {who['via']} | bundle {rec['bundle_hash'][:12]}")
        for fid in made["created"]:
            print(f"  created: {fid} (waiting)")
        for fid in made["cancelled"]:
            print(f"  cancelled: {fid} (removed from the split)")
        machine.transition(f, "delivering", "split approved", actor=f"human:{by}")
        print(f"state -> delivering. Start the first feature: `hr start -f {f.id}`")
        return 0
    if args.gate == "design":
        rec = gates.approve_design(f, st, by, args.scope or "", args.note or "", proof)
        redpill.record_decision(f, "design", by, named, True)
        f.save_state(st)
        print(f"design approval recorded: {by} via {who['via']} | bundle {rec['bundle_hash'][:12]}")
        machine.transition(f, "executing", "design approved", actor=f"human:{by}")
        print("state -> executing")
    else:
        rec = gates.approve_final(f, st, by, args.risks or "", args.note or "", proof)
        redpill.record_decision(f, "final", by, named, True)
        f.save_state(st)
        print(f"final approval recorded: {by} via {who['via']} | commit {rec['commit_sha'][:10]}")
        machine.transition(f, "ready_to_merge", "final approval", actor=f"human:{by}")
        print("state -> ready_to_merge (merging follows repository rules and `hr merge-check`)")
    return 0


def cmd_reject(ws: Workspace, args) -> int:
    from runtime.state import machine

    f = _feature(ws, args)
    st = f.state()
    expected = GATE_STATES[args.gate]
    if st["state"] != expected:
        raise GateError(f"a {args.gate} change request is recorded only in {expected} (current: {st['state']})")
    from runtime import human

    target = args.to or {"design": "clarifying", "split": "splitting"}.get(args.gate, "rework_required")
    who = human.resolve(ws, args.by or "user (chat)", args.quote, _gate_since(f, args), terminal=False)
    proof = human.proof_fields(who)
    f.emit("approval_rejected", gate=args.gate, reason=args.reason, by=args.by or "user (chat)", **proof)
    machine.transition(f, target, f"{args.gate} change requested: {args.reason}")
    print(f"change request recorded | state -> {target}")
    return 0


def cmd_unblock(ws: Workspace, args) -> int:
    from runtime.state import machine

    from runtime import human

    f = _feature(ws, args)
    who = human.resolve(ws, args.by, args.quote, _gate_since(f, args))
    st = machine.unblock(f, who["by"], args.note or "", human.proof_fields(who))
    print(f"unblocked -> {st['state']}")
    return 0


def _csv(text: Optional[str]) -> List[str]:
    return [x.strip() for x in (text or "").split(",") if x.strip()]


def _probe(args, old: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if args.concept is None and args.searched is None and args.consumers is None:
        return old
    searched = _csv(args.searched)
    if not searched:
        raise HRError("--searched is required with --concept or --consumers: the names you looked for")
    return {"concept": (args.concept or "").strip(), "searched": searched, "consumers": _csv(args.consumers)}


def cmd_impact(ws: Workspace, args) -> int:
    from runtime import docs

    f = _feature(ws, args)
    st = f.state()
    if not args.recheck:
        print(docs.impact_block(f))
        return 0
    terms = _csv(args.searched)
    if not terms:
        raise HRError("--recheck needs --searched: the names you looked for in the code as it is now")
    fp = fingerprint(ws.root)
    if fp.get("dirty") and st.get("mode") in ("L2", "L3"):
        raise GateError("commit first: the second search is recorded for one version of the code")
    st["impact_recheck"] = {"at": now(), "commit_sha": fp.get("commit_sha"), "code_tree": fp.get("code_tree"),
                            "searched": terms, "note": args.note or ""}
    f.save_state(st)
    f.emit("impact_rechecked", commit_sha=fp.get("commit_sha"), searched=terms, note=args.note or "")
    print(f"second search recorded at {str(fp.get('commit_sha') or 'no commit')[:10]}: {', '.join(terms)}")
    print("  a place that is not in the impact table goes into requirements.json with a task or a test (a plan change)")
    return 0


def cmd_review_brief(ws: Workspace, args) -> int:
    from runtime import review
    from runtime.config import agent_settings

    f = _feature(ws, args)
    out = review.brief(f)
    out["agent"] = {"subagent_type": review.REVIEWER, **agent_settings(ws.config())["code_reviewer"]["agent_call"]}
    if args.json:
        _print_json(out)
    else:
        print(out["prompt"])
    return 0


def cmd_record_review(ws: Workspace, args) -> int:
    from runtime import review

    f = _feature(ws, args)
    path = Path(args.report) if args.report else review.report_path(f)
    if not path.is_absolute():
        path = ws.root / path
    if not path.is_file():
        raise HRError(f"no report at {path}")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HRError(f"report is not valid JSON: {exc}")
    res = review.record(f, report)
    rev = res["review"]
    print(f"{rev['id']} recorded at {rev['commit_sha'][:10]}: {len(rev['files_read'])} changed file(s) read, "
          f"{len(res['new'])} finding(s)")
    for x in res["new"]:
        print(f"  {x['id']} [{x['kind']}] {review._place(x)}: {x['what']}")
    if res["closed"]:
        print("  closed, because their code changed and was reviewed again: " + ", ".join(res["closed"]))
    waiting = res["open"] + [x["id"] for x in res["new"]]
    if waiting:
        print("  no disposition yet: " + ", ".join(waiting) + ". Remove the code and run the review again, or the "
              "human accepts it with a reason (`hr finding accept <id> --reason ... --quote`)")
    return 0


def cmd_finding(ws: Workspace, args) -> int:
    from runtime import human, review

    f = _feature(ws, args)
    if args.action == "accept":
        if not args.ids:
            raise HRError("name the findings to accept: `hr finding accept FND-001 --reason ...`")
        who = human.resolve(ws, args.by, args.quote, _gate_since(f, args))
        for fid in args.ids:
            x = review.accept(f, fid, args.reason or "", who["by"], human.proof_fields(who))
            print(f"{x['id']} accepted by {who['by']} via {who['via']}: {x['disposition']['reason']}")
        return 0
    data = review.load(f)
    if args.json:
        _print_json(data)
        return 0
    if not data["findings"]:
        print("no findings recorded" if data["reviews"] else "no review of the written code is recorded")
    for x in data["findings"]:
        d = x.get("disposition") or {}
        tail = d.get("reason") or d.get("review") or ""
        print(f"{x['id']} [{d.get('kind') or 'open'}{': ' + tail if tail else ''}] {x['kind']} "
              f"{review._place(x)} | {x['what']}")
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


def cmd_change_size(ws: Workspace, args) -> int:
    from runtime import docs, size

    f = _feature(ws, args)
    if args.json:
        _print_json(size.measure(f))
    else:
        print(docs.size_block(f))
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
    from runtime import groups

    waiting = [Feature(ws, r["feature_id"]) for r in groups.children_of(f) if r["state"] == "proposed"]
    st = machine.transition(f, "cancelled", args.reason or "aborted by user")
    for child in waiting:
        machine.transition(child, "cancelled", f"group {f.id} was cancelled")
        print(f"{child.id}: cancelled (was waiting in {f.id})")
    if ws.active_feature_id() == f.id:
        ws.set_active(None)
    print(f"{f.id}: cancelled. Records ({f.dir}) and the work branch ({st['git'].get('branch') or '-'}) are kept.")
    _after_child(ws, f, st)
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
        from runtime.config import agent_settings

        call = agent_settings(ws.config())["task_worker"]["agent_call"]
        briefs = [{**worktrees.brief(f, st, tid), "agent": {"subagent_type": "hr-task-worker", **call}}
                  for tid in started]
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
        rp = data["redpill"]
        print(f"  red pill: drills {rp['drills']}, caught {rp['caught']}, after a refusal {rp['caught_after_refusal']}, "
              f"scattershot (not counted) {rp['scattershot']}, missed {rp['missed']}, catch rate {rp['catch_rate']}")
        _print_reviews(rp, "    ")
        _print_off(rp, "    ")
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
    rp = d["redpill"]
    print(f"  red pill: drills {rp['drills']}, caught {rp['caught']}, after a refusal {rp['caught_after_refusal']}, "
          f"scattershot (not counted) {rp['scattershot']}, missed {rp['missed']}, catch rate {rp['catch_rate']}")
    _print_reviews(rp, "    ")
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

    from runtime import human

    f = _feature(ws, args)
    who = human.resolve(ws, args.by, args.quote, _gate_since(f, args))
    for res in redpill.flag_all(f, args.items, who["by"], args.note or "", human.proof_fields(who)):
        print(res["message"])
    return 0


def cmd_redpill(ws: Workspace, args) -> int:
    from runtime import redpill

    from runtime import human

    ws.require_init()
    who = None
    reason = (args.reason or "").strip()
    if args.redpill_cmd in ("on", "off"):
        who = human.resolve(ws, args.by or human.default_name(ws), args.quote)
    if args.redpill_cmd == "off" and not reason:
        raise HRError('hr redpill off needs --reason "<why drills are off>": the reason is recorded and shown in '
                      "`hr redpill status` and `hr metrics`")
    if args.redpill_cmd in ("brief", "seed"):
        f = _feature(ws, args)
        if not args.gate:
            raise HRError("--gate design|final is required")
        if args.redpill_cmd == "brief":
            b = redpill.brief(f, args.gate)
            if args.json:
                _print_json(b)
            else:
                print(b["prompt"])
            return 0
        if not args.source:
            raise HRError("--from <file|-> is required")
        res = redpill.seed(f, args.gate, _read_json_arg(args.source if args.source == "-" else "@" + args.source))
        print(f"{res['count']} candidates accepted for the {res['gate']} gate")
        return 0
    if args.redpill_cmd == "on":
        values = {"enabled": True, **_redpill_values(None, args.difficulty, args.one_in, args.author, args.max_flags)}
        if args.gates:
            gates = [g.strip() for g in args.gates.split(",") if g.strip()]
            if not gates or any(g not in ("design", "final") for g in gates):
                raise HRError("--gates takes design, final, or design,final")
            values["gates"] = gates
        if args.language:
            values["language"] = args.language
        redpill.set_config(ws, values, who, reason)
    elif args.redpill_cmd == "off":
        redpill.set_config(ws, {"enabled": False}, who, reason)
    elif args.redpill_cmd == "reveal":
        f = _feature(ws, args)
        who = human.resolve(ws, args.by, args.quote, _gate_since(f, args))
        print(redpill.reveal(f, who["by"], human.proof_fields(who)))
        return 0
    _print_redpill(ws)
    prog = redpill.progress(ws)
    print(f"all features: drills {prog['drills']}, caught {prog['caught']}, caught after a refusal "
          f"{prog['caught_after_refusal']}, missed {prog['missed']}, rubber stamps {prog['rubber_stamps']}, "
          f"caught by naming more than {prog['max_flags']} rows {prog['scattershot']} (not counted), "
          f"catch rate {prog['catch_rate']}")
    _print_reviews(prog, "  ")
    _print_off(prog, "  ")
    for d, row in prog["by_difficulty"].items():
        if row["drills"]:
            print(f"  {d}: caught {row['caught']}, after a refusal {row['caught_after_refusal']}, "
                  f"missed {row['missed']}, catch rate {row['catch_rate']}")
    if prog["missed_categories"]:
        print("  missed most: " + ", ".join(f"{k} x{v}" for k, v in list(prog["missed_categories"].items())[:3]))
    fid = getattr(args, "feature", None) or ws.active_feature_id()
    if fid:
        st = redpill.stats(ws.resolve(fid))
        print(f"{fid}: drills {st['drills']}, caught {st['caught']}, missed {st['missed']}, "
              f"rubber stamps {st['rubber_stamps']}, catch rate {st['catch_rate']}")
        _print_reviews(st, "  ")
    return 0


def cmd_floor(ws: Workspace, args) -> int:
    from runtime import human
    from runtime.routing import floor
    from runtime.routing.router import MODES

    ws.require_init()
    rules = floor.load(ws)
    tampered = floor.problem(ws, history=True)
    if args.action == "accept":
        who = human.resolve(ws, args.by, args.quote)
        floor.seal(ws, rules, who)
        fid = ws.active_feature_id()
        if fid:
            ws.resolve(fid).emit("floor_changed", actor=f"human:{who['by']}", action="accept", rules=rules,
                                 **human.proof_fields(who))
        for pattern in sorted(rules):
            print(f"{rules[pattern]}  {pattern}")
        print(f"floor: accepted as it is now ({len(rules)} rule{'' if len(rules) == 1 else 's'}) "
              f"| decided by {who['by']} via {who['via']}")
        return 0
    if args.action == "list":
        if tampered:
            print(tampered)
        if not rules:
            print("no floor: no path is always gated. The owner adds one with `hr floor add <glob> <level>`.")
            return 0
        fid = ws.active_feature_id()
        by_pattern = {}
        if fid:
            f = ws.resolve(fid)
            st = f.state()
            declared = (st.get("routing") or {}).get("declared_paths") or []
            by_pattern = {h["pattern"]: h["paths"] for h in floor.hits(rules, floor.touched(ws, st, declared))}
        for pattern in sorted(rules):
            print(f"{rules[pattern]}  {pattern}")
            for p in by_pattern.get(pattern, []):
                print(f"    touched by {fid}: {p}")
        return 0
    if not args.pattern:
        raise HRError(f"hr floor {args.action} needs a glob")
    if tampered:
        raise GateError(tampered)
    pattern = floor.check_pattern(args.pattern)
    if args.action == "add":
        if args.level not in MODES:
            raise HRError(f"hr floor add <glob> <level>: the level is one of {', '.join(MODES)}")
        change = {"action": "add", "pattern": pattern, "level": args.level, "previous": rules.get(pattern)}
        rules[pattern] = args.level
    else:
        if pattern not in rules:
            raise HRError(f"{pattern!r} is not in the floor (`hr floor` lists the rules)")
        change = {"action": "remove", "pattern": pattern, "level": None, "previous": rules.pop(pattern)}
    who = human.resolve(ws, args.by, args.quote)
    floor.save(ws, rules)
    floor.seal(ws, rules, who)
    fid = ws.active_feature_id()
    if fid:
        ws.resolve(fid).emit("floor_changed", actor=f"human:{who['by']}", **change, **human.proof_fields(who))
    was = f" (was {change['previous']})" if change["previous"] else ""
    print(f"floor: {change['action']} {pattern}" + (f" {args.level}" if args.action == "add" else "") + was
          + f" | decided by {who['by']} via {who['via']}")
    return 0


def cmd_migrate(ws: Workspace, args) -> int:
    ws.require_init()
    from runtime import groups

    moves = groups.migrate(ws, dry_run=args.dry_run)
    if not moves:
        print("layout is current: groups are under groups/GRP-*, each with its features inside")
        return 0
    print("would move:" if args.dry_run else "moved:")
    for m in moves:
        print(f"  {m}")
    return 0


def _layout_hint(ws: Workspace) -> None:
    from runtime import groups

    if groups.migration_plan(ws):
        print("! this workspace uses the old layout (groups stored as FEAT-* next to their features). "
              "`hr migrate --dry-run` shows the moves, `hr migrate` applies them.")


def cmd_list(ws: Workspace, args) -> int:
    ws.require_init()
    from runtime import groups

    _layout_hint(ws)
    active = ws.active_feature_id()
    for row in groups.tree(ws):
        fid, st = row["feature_id"], row["state"]
        grade = "group" if groups.is_group(st) else (st.get("mode") or "--")
        print(f"{'*' if fid == active else ' '} {'  ' * row['depth']}{fid}  {grade}  {st['state']}  {st['title']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hr", description="human-rights workflow executor")
    p.add_argument("--root", help="repository root (default: git root of the current directory)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name: str, fn, help_: str, feature: bool = True) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help_)
        if feature:
            sp.add_argument("-f", "--feature", help="FEAT-NNN or GRP-NNN (default: active feature)")
        sp.set_defaults(fn=fn)
        return sp

    sp = add("init", cmd_init, "initialize .human-rights/", feature=False)
    sp.add_argument("--language", help="report language for human-facing documents: en or ko")
    sp.add_argument("--agents", help="sub-agent model preset: balanced, quality, economy, inherit")
    sp.add_argument("--redpill", help="red pill review drills: on or off")
    sp.add_argument("--redpill-difficulty", help="easy, normal, hard, or adaptive")
    sp.add_argument("--redpill-one-in", type=int, help="plant a drill in about 1 of N approval requests")
    sp = add("agents", cmd_agents, "model and effort each sub-agent runs with (from config.yaml agents:)", feature=False)
    sp.add_argument("--json", action="store_true")
    sp = add("new", cmd_new, "create a feature (-> triaging)", feature=False)
    sp.add_argument("title")
    sp.add_argument("--slug")
    sp.add_argument("--request")
    sp = add("classify", cmd_classify, "Adaptive Router (re)classification")
    sp.add_argument("--axes", required=True, help="JSON, @file, or - (stdin)")
    sp.add_argument("--flags", help="physical_safety,vehicle_command,auth,secrets,destructive_migration,irreversible_external")
    sp.add_argument("--paths", help="comma-separated files or globs this change is expected to touch (checked against "
                                    "the owner's floor; omitted keeps the paths from the last classification)")
    sp.add_argument("--note")
    sp.add_argument("--concept", help="the thing this change touches, as the user sees it")
    sp.add_argument("--searched", help="comma-separated names you searched for to find other places that use it")
    sp.add_argument("--consumers", help="comma-separated other places that show, compute, store or send it")
    sp.add_argument("--size", choices=("single", "compound"), help="one feature, or several separately verifiable results")
    sp.add_argument("--size-reason")
    sp = add("size", cmd_size, "record the size decision on its own (single feature, or compound -> split)")
    sp.add_argument("size", choices=("single", "compound"))
    sp.add_argument("--reason", required=True)
    sp = add("split-check", cmd_split_check, "split quality hard gate for a group (split.json + group checks)")
    sp.add_argument("--json", action="store_true")
    sp = add("start", cmd_start, "start the next waiting feature of a group (or -f a waiting feature)")
    sp.add_argument("--json", action="store_true")
    sp = add("status", cmd_status, "current status")
    sp.add_argument("--json", action="store_true")
    add("list", cmd_list, "list groups and features", feature=False)
    sp = add("migrate", cmd_migrate, "move an older workspace to the current layout (groups/GRP-*/features/FEAT-*)",
             feature=False)
    sp.add_argument("--dry-run", action="store_true")
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
    sp = add("record-manual", cmd_record_manual, "[human decision: --by, or --quote from chat] record a manual test result")
    sp.add_argument("test_id")
    sp.add_argument("result", choices=("passed", "failed"))
    sp.add_argument("--by")
    sp.add_argument("--quote", help="the human's exact words from their latest chat message")
    sp.add_argument("--note")
    sp.add_argument("--evidence")
    sp.add_argument("--env", default="manual")
    sp = add("test-brief", cmd_test_brief, "work order for hr-tester to run an agent test (steps, pass criteria, evidence)")
    sp.add_argument("test_id")
    sp.add_argument("--json", action="store_true")
    sp = add("record-agent", cmd_record_agent, "record an agent-run test from the tester's report (per-step evidence required)")
    sp.add_argument("test_id")
    sp.add_argument("--report", help="report.json path (default: the test's evidence directory)")
    sp = add("failures", cmd_failures, "list / classify failure records")
    sp.add_argument("--classify", metavar="FAIL-ID")
    sp.add_argument("--cause-type", default="unclassified")
    sp.add_argument("--cause")
    sp.add_argument("--suspect")
    sp.add_argument("--fix-task")
    sp.add_argument("--retest")
    sp.add_argument("--json", action="store_true")
    sp = add("approve", cmd_approve, "[human decision: --by, or --quote from chat] design / final / split approval")
    sp.add_argument("gate", choices=("design", "final", "split"))
    sp.add_argument("--by")
    sp.add_argument("--quote", help="the human's exact words from their latest chat message")
    sp.add_argument("--flag", nargs="+", metavar="ID", help="items the human pointed out in that message")
    sp.add_argument("--scope")
    sp.add_argument("--note")
    sp.add_argument("--risks", help="residual risks accepted with the final approval")
    sp = add("reject", cmd_reject, "record a human change request on an approval item")
    sp.add_argument("gate", choices=("design", "final", "split"))
    sp.add_argument("--reason", required=True)
    sp.add_argument("--to", choices=("clarifying", "planning", "investigating", "rework_required", "splitting"))
    sp.add_argument("--by")
    sp.add_argument("--quote", help="the human's exact words from their latest chat message")
    sp = add("unblock", cmd_unblock, "[human decision: --by, or --quote from chat] release an escalation")
    sp.add_argument("--by")
    sp.add_argument("--quote", help="the human's exact words from their latest chat message")
    sp.add_argument("--note")
    sp = add("impact", cmd_impact, "other places that use what this change touches; --recheck records the search after the code is written")
    sp.add_argument("--recheck", action="store_true")
    sp.add_argument("--searched", help="comma-separated names searched for")
    sp.add_argument("--note")
    sp = add("review-brief", cmd_review_brief, "work order for hr-code-reviewer: review the written code before final approval (L2, L3)")
    sp.add_argument("--json", action="store_true")
    sp = add("record-review", cmd_record_review, "record the code reviewer's report (every finding needs a changed file and lines)")
    sp.add_argument("--report", help="report.json path (default: evidence/code-review/report.json of the feature)")
    sp = add("finding", cmd_finding, "[accept is a human decision: --by, or --quote from chat] findings of the code review and what was decided")
    sp.add_argument("action", nargs="?", choices=("list", "accept"), default="list")
    sp.add_argument("ids", nargs="*", metavar="FND-ID")
    sp.add_argument("--reason", help="accept: why the human keeps this code")
    sp.add_argument("--by")
    sp.add_argument("--quote", help="the human's exact words from their latest chat message")
    sp.add_argument("--json", action="store_true")
    sp = add("scope-change", cmd_scope_change, "change outside the task boundary found -> scope change request")
    sp.add_argument("--task")
    sp.add_argument("--reason", required=True)
    add("render", cmd_render, "refresh hr:* blocks in human docs from evidence")
    sp = add("change-size", cmd_change_size, "size of the change from git diff: files, lines, tests, new dependencies, per task")
    sp.add_argument("--json", action="store_true")
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
    sp.add_argument("docs", nargs="*", help="overview requirements design verification codebase research tasks l0-summary review-report group")
    sp.add_argument("--overwrite", action="store_true")
    sp = add("flag", cmd_flag, "[human decision: --by, or --quote from chat] point at an item in the approval material you would not approve")
    sp.add_argument("items", nargs="+", metavar="ID")
    sp.add_argument("--by")
    sp.add_argument("--quote", help="the human's exact words from their latest chat message")
    sp.add_argument("--note")
    sp = add("redpill", cmd_redpill, "red pill mode: random review-vigilance drills (on/off/reveal are human decisions)")
    sp.add_argument("redpill_cmd", choices=("on", "off", "status", "reveal", "brief", "seed"))
    sp.add_argument("--one-in", type=int, help="plant a drill in about 1 of N approval requests")
    sp.add_argument("--difficulty", help="easy, normal, hard, or adaptive")
    sp.add_argument("--author", help="who writes the drills: agent (tailored to each plan) or builtin")
    sp.add_argument("--max-flags", type=int, help="a catch that names more rows than this is not counted (default 3)")
    sp.add_argument("--reason", help="off: why drills are turned off (required); on: why settings change")
    sp.add_argument("--gate", choices=("design", "final"), help="brief / seed: which approval gate")
    sp.add_argument("--from", dest="source", help="seed: candidates JSON file, or - for stdin")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--gates", help="design, final, or design,final")
    sp.add_argument("--language", help="en or ko (default: docs.language)")
    sp.add_argument("--by")
    sp.add_argument("--quote", help="the human's exact words from their latest chat message")
    sp = add("floor", cmd_floor, "[add/remove/accept are human decisions: --by, or --quote from chat] paths that always need at least a level",
             feature=False)
    sp.add_argument("action", nargs="?", choices=("list", "add", "remove", "accept"), default="list")
    sp.add_argument("pattern", nargs="?", help="glob such as src/auth/**")
    sp.add_argument("level", nargs="?", help="L0, L1, L2 or L3 (add only)")
    sp.add_argument("--by")
    sp.add_argument("--quote", help="the human's exact words from their latest chat message")
    add("merge-check", cmd_merge_check, "can this be merged? (approved code, live GitHub state)")
    sp = add("abort", cmd_abort, "cancel (records and branch are kept)")
    sp.add_argument("--reason")
    return p


READ_ONLY = {"init", "list", "doc-check", "log", "agents"}


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
