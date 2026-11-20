from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from runtime.common import GateError, HRError, canonical, now, sha256_bytes
from runtime.state.store import (CONTAINERS, FEATURE_PREFIX, GROUP_PREFIX, Feature, id_order, id_prefix, new_state,
                                 with_prefix)

KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SIZES = ("single", "compound")
CODE_STATUSES = ("missing", "partial", "exists", "conflict")
DONE = ("completed", "cancelled", "failed")
SIZE_MODES = ("L2", "L3")
MAX_CHILDREN_HINT = 12


def is_group(st: Dict[str, Any]) -> bool:
    return st.get("kind") == "group"


def prefix_for(st: Dict[str, Any]) -> str:
    return GROUP_PREFIX if is_group(st) else FEATURE_PREFIX


def place(feature: Feature, st: Dict[str, Any]) -> bool:
    want = prefix_for(st)
    if id_prefix(feature.id) == want:
        return False
    new_id = with_prefix(feature.id, want)
    feature.relocate(new_id, feature.dir.parent.parent / CONTAINERS[want] / new_id)
    return True


def migration_plan(ws: Any) -> List[Dict[str, Any]]:
    dirs = ws.locations()
    states = {fid: Feature(ws, fid, d).load("state") or {} for fid, d in dirs.items()}
    parent_of: Dict[str, str] = {}
    for fid, st in states.items():
        if is_group(st):
            for link in st.get("children") or []:
                if link.get("feature_id") in states:
                    parent_of[link["feature_id"]] = fid
    targets: Dict[str, Any] = {}

    def target(fid: str, seen: tuple = ()) -> Any:
        if fid in targets:
            return targets[fid]
        want = prefix_for(states[fid])
        new_id = with_prefix(fid, want)
        pid = parent_of.get(fid)
        if pid and pid not in seen:
            holder = target(pid, seen + (fid,))["dir"]
        else:
            holder = dirs[fid].parent.parent
        targets[fid] = {"id": new_id, "dir": holder / CONTAINERS[want] / new_id}
        return targets[fid]

    def depth(fid: str) -> int:
        n, cur, seen = 0, fid, set()
        while cur in parent_of and cur not in seen:
            seen.add(cur)
            cur = parent_of[cur]
            n += 1
        return n

    plan = []
    for fid in sorted(dirs, key=lambda f: (depth(f), id_order(f))):
        tgt = target(fid)
        if tgt["id"] != fid or tgt["dir"] != dirs[fid]:
            plan.append({"feature_id": fid, "new_id": tgt["id"], "from": dirs[fid], "to": tgt["dir"]})
    return plan


def migrate(ws: Any, dry_run: bool = False) -> List[str]:
    out = []
    for step in migration_plan(ws):
        feature = Feature(ws, step["feature_id"])
        out.append(f"{step['from'].relative_to(ws.wf).as_posix()} -> {step['to'].relative_to(ws.wf).as_posix()}")
        if not dry_run and (feature.dir != step["to"] or feature.id != step["new_id"]):
            feature.relocate(step["new_id"], step["to"])
    return out


def split_of(feature: Feature) -> Dict[str, Any]:
    return feature.load("split", {}) or {}


def children_of(feature: Feature, st: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    st = st or feature.state()
    spec = {c.get("key"): c for c in split_of(feature).get("children", [])}
    rows = []
    for link in st.get("children") or []:
        child = Feature(feature.ws, link["feature_id"])
        cst = child.load("state") or {}
        rows.append({"key": link["key"], "feature_id": link["feature_id"], "state": cst.get("state", "missing"),
                     "mode": cst.get("mode"), "kind": cst.get("kind", "feature"), "title": cst.get("title", ""),
                     "spec": spec.get(link["key"], {})})
    return rows


def _cycle(children: Dict[str, Dict[str, Any]]) -> List[str]:
    from runtime.verification.plan_check import _find_cycle

    return _find_cycle(children)


def check_split(feature: Feature) -> Dict[str, Any]:
    from runtime.verification import evidence
    from runtime.verification.plan_check import test_problems

    split = split_of(feature)
    st = feature.state()
    hard: List[str] = []
    warn: List[str] = []
    kids = split.get("children")
    if not isinstance(kids, list) or len(kids) < 2:
        hard.append("split.json needs at least two `children` - with one, this is a single feature (`hr classify --size single`)")
        kids = kids if isinstance(kids, list) else []
    by_key: Dict[str, Dict[str, Any]] = {}
    for i, c in enumerate(kids, 1):
        key = str(c.get("key") or "")
        label = key or f"child #{i}"
        if not KEY_RE.match(key):
            hard.append(f"{label}: `key` must be a short slug (a-z, 0-9, -)")
            continue
        if key in by_key:
            hard.append(f"{key}: duplicate key")
        by_key[key] = c
        for field, why in (("title", "a name the human recognises"),
                           ("outcome", "the result someone can use once this feature alone is done"),
                           ("verify_alone", "how this feature is verified on its own - without it, it is a task, "
                                            "not a feature")):
            if not str(c.get(field) or "").strip():
                hard.append(f"{key}: missing `{field}` ({why})")
        if c.get("code_status") is not None and c["code_status"] not in CODE_STATUSES:
            hard.append(f"{key}: code_status must be one of {', '.join(CODE_STATUSES)}")
        if c.get("code_status") == "exists":
            hard.append(f"{key}: the code already does this - move it to `excluded` with the evidence instead of "
                        "making it a feature")
        if c.get("expected_mode") in ("L0", "L1"):
            warn.append(f"{key}: expected {c['expected_mode']} - small enough to fold into a neighbouring feature?")
    for key, c in by_key.items():
        for d in c.get("depends_on", []) or []:
            if d == key or d not in by_key:
                hard.append(f"{key}: unknown dependency {d!r}")
    cyc = _cycle(by_key)
    if cyc:
        hard.append("dependency cycle between features: " + " -> ".join(cyc))
    if len(by_key) > MAX_CHILDREN_HINT:
        warn.append(f"{len(by_key)} features in one group - consider grouping related ones under a sub-group")

    if not isinstance(split.get("shared_decisions"), list):
        hard.append("split.json needs `shared_decisions` (a list; empty when nothing applies to more than one feature)")
    else:
        for d in split["shared_decisions"]:
            if not str(d.get("question") or "").strip() or not str(d.get("answer") or "").strip():
                hard.append(f"shared decision {d.get('id') or '?'}: needs `question` and `answer`")
            if d.get("safety") and d.get("decided_by") != "user":
                hard.append(f"shared decision {d.get('id') or '?'}: risky policy decided without the user")
    if not isinstance(split.get("excluded"), list):
        hard.append("split.json needs `excluded` (a list of what the request mentions but this group will not "
                    "build, each with a reason; empty when nothing is left out)")
    else:
        for e in split["excluded"]:
            if not str(e.get("item") or "").strip() or not str(e.get("reason") or "").strip():
                hard.append("excluded: every entry needs `item` and `reason`")

    source = split.get("source") or {}
    if source.get("kind") == "document":
        if not str(source.get("path") or "").strip():
            hard.append("source: a document source needs its `path`")
        if not isinstance(source.get("unread"), list):
            hard.append("source: list `unread` parts (pages whose content is an image, a chart, or otherwise not "
                        "read), each with `ref` and `reason`; empty only if every part was read")
        for key, c in by_key.items():
            if not c.get("sources"):
                hard.append(f"{key}: no `sources` - name the pages or sections of the document it comes from")

    plan = feature.test_plan()
    tests = {t.get("id"): t for t in plan.get("tests", [])}
    required = evidence.required_tests(plan)
    if not required:
        hard.append("test-plan.json: a group needs at least one required test of the features working together")
    t_hard, t_warn = test_problems(tests, {}, True)
    hard += t_hard
    warn += t_warn
    crossing = False
    for tid, t in tests.items():
        named = t.get("children") or []
        for k in named:
            if k not in by_key:
                hard.append(f"{tid}: references unknown feature {k!r}")
        if t.get("required", True) and len(set(named) & set(by_key)) >= 2:
            crossing = True
    if required and not crossing:
        hard.append("test-plan.json: no required test names two or more features in `children` - a group is done "
                    "only when its features work together, so plan a check that crosses them")

    for link in st.get("children") or []:
        if link["key"] in by_key:
            continue
        cst = Feature(feature.ws, link["feature_id"]).load("state") or {}
        if cst.get("state") not in DONE + ("proposed",):
            hard.append(f"{link['key']} was removed from the split but {link['feature_id']} is in progress "
                        f"({cst.get('state')}) - cancel it first (`hr abort -f {link['feature_id']}`)")
    return {"ok": not hard, "hard_fail": hard, "warnings": warn}


def artifacts(feature: Feature) -> Dict[str, str]:
    return {
        "split.json": sha256_bytes(canonical(split_of(feature))),
        "test-plan.json": sha256_bytes(canonical(feature.test_plan())),
    }


def split_status(feature: Feature, st: Dict[str, Any]) -> Dict[str, Any]:
    ap = (st.get("approvals") or {}).get("split")
    if not ap:
        return {"valid": False, "changed": [], "approval": None}
    cur = artifacts(feature)
    changed = [k for k, v in cur.items() if ap["artifacts"].get(k) != v]
    return {"valid": not changed, "changed": changed, "approval": ap}


def approve_split(feature: Feature, st: Dict[str, Any], by: str, note: str,
                  proof: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not by:
        raise HRError("--by (approver) is required")
    if st["state"] != "awaiting_split_approval":
        raise GateError(f"split approval is only possible in awaiting_split_approval (current: {st['state']})")
    res = check_split(feature)
    if not res["ok"]:
        raise GateError("cannot approve while split problems remain:\n  - " + "\n  - ".join(res["hard_fail"]))
    arts = artifacts(feature)
    bundle = sha256_bytes(canonical(arts))
    ev = feature.emit("approval_granted", gate="split", approver=by, bundle_hash=bundle, actor=f"human:{by}",
                      **(proof or {}))
    record = {"gate": "split", "approver": by, "approved_at": now(), "via": "cli", **(proof or {}), "note": note,
              "artifacts": arts, "bundle_hash": bundle, "event_hash": ev["hash"]}
    st.setdefault("approvals", {})["split"] = record
    return record


def sync_children(feature: Feature, st: Dict[str, Any]) -> Dict[str, List[str]]:
    from runtime.common import fingerprint

    ws = feature.ws
    split = split_of(feature)
    wanted = {c["key"]: c for c in split.get("children", [])}
    links = list(st.get("children") or [])
    known = {l["key"] for l in links}
    out: Dict[str, List[str]] = {"created": [], "cancelled": []}
    for link in links:
        if link["key"] in wanted:
            continue
        child = Feature(ws, link["feature_id"])
        cst = child.load("state") or {}
        if cst.get("state") == "proposed":
            cst["state"] = "cancelled"
            child.save_state(cst)
            child.emit("state_changed", **{"from": "proposed", "to": "cancelled",
                                           "reason": f"removed from the split of {feature.id}"})
            out["cancelled"].append(link["feature_id"])
    base = fingerprint(ws.root)["commit_sha"]
    for key, c in wanted.items():
        if key in known:
            continue
        fid = ws.next_feature_id(key)
        child = Feature(ws, fid, feature.child_dir(fid))
        for sub in ("tasks", "details", ".internal"):
            (child.dir / sub).mkdir(parents=True, exist_ok=True)
        cst = new_state(fid, c["title"], c["outcome"])
        cst.update(parent=feature.id, group_key=key, state="proposed")
        cst["git"]["base_sha"] = base
        child.save_state(cst)
        child.emit("feature_created", title=c["title"], request=c["outcome"], base_sha=base, parent=feature.id,
                   group_key=key)
        links.append({"key": key, "feature_id": fid})
        out["created"].append(fid)
    st["children"] = links
    return out


def _order(feature: Feature) -> List[str]:
    kids = {c["key"]: c for c in split_of(feature).get("children", [])}
    order: List[str] = []
    seen = set()

    def visit(k: str) -> None:
        if k in seen or k not in kids:
            return
        seen.add(k)
        for d in kids[k].get("depends_on", []) or []:
            visit(d)
        order.append(k)

    for k in kids:
        visit(k)
    return order


def ordered_children(feature: Feature, st: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    rows = {r["key"]: r for r in children_of(feature, st)}
    order = _order(feature)
    return [rows[k] for k in order if k in rows] + [r for k, r in rows.items() if k not in order]


def active_limit(feature: Feature) -> int:
    try:
        return max(1, int((feature.ws.config().get("groups") or {}).get("max_active_children", 1)))
    except (TypeError, ValueError):
        return 1


def start_problems(child: Feature, cst: Dict[str, Any]) -> List[str]:
    pid = cst.get("parent")
    if not pid:
        return []
    parent = Feature(child.ws, pid)
    pst = parent.load("state")
    if not pst:
        return [f"parent group {pid} is missing"]
    problems: List[str] = []
    if pst.get("state") != "delivering":
        problems.append(f"the group {pid} is not delivering (current: {pst.get('state')})")
    if not split_status(parent, pst)["valid"]:
        problems.append(f"the split of {pid} has no valid approval (it changed after approval, or was never approved)")
    rows = {r["key"]: r for r in children_of(parent, pst)}
    me = rows.get(cst.get("group_key"))
    if not me:
        return problems + [f"{child.id} is no longer part of the split of {pid}"]
    for d in me["spec"].get("depends_on", []) or []:
        dep = rows.get(d)
        if not dep or dep["state"] != "completed":
            problems.append(f"depends on {d} ({dep['feature_id'] if dep else '?'}), which is "
                            f"{dep['state'] if dep else 'missing'}")
    running = [r["feature_id"] for r in rows.values()
               if r["feature_id"] != child.id and r["state"] not in DONE + ("proposed",)]
    limit = active_limit(parent)
    if len(running) >= limit:
        problems.append(f"{', '.join(running)} still in progress (groups.max_active_children = {limit}): the "
                        "human's review is the bottleneck, so finish it first")
    return problems


def next_child(feature: Feature, st: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for row in ordered_children(feature, st):
        if row["state"] != "proposed":
            continue
        child = Feature(feature.ws, row["feature_id"])
        if not start_problems(child, child.state()):
            return row
    return None


def unfinished(feature: Feature, st: Dict[str, Any]) -> List[str]:
    return [f"{r['feature_id']} ({r['state']})" for r in children_of(feature, st) if r["state"] not in DONE]


def brief(child: Feature, cst: Dict[str, Any]) -> Dict[str, Any]:
    parent = Feature(child.ws, cst["parent"])
    split = split_of(parent)
    spec = next((c for c in split.get("children", []) if c.get("key") == cst.get("group_key")), {})
    rows = {r["key"]: r for r in children_of(parent)}
    return {
        "feature_id": child.id,
        "group": parent.id,
        "title": spec.get("title") or cst.get("title"),
        "outcome": spec.get("outcome"),
        "verify_alone": spec.get("verify_alone"),
        "sources": spec.get("sources") or [],
        "source_document": (split.get("source") or {}).get("path"),
        "code_status": spec.get("code_status"),
        "expected_mode": spec.get("expected_mode"),
        "built_on": [{"key": d, "feature_id": rows[d]["feature_id"]} for d in spec.get("depends_on", []) or [] if d in rows],
        "shared_decisions": split.get("shared_decisions") or [],
        "not_in_this_group": split.get("excluded") or [],
    }


def tree(ws: Any) -> List[Dict[str, Any]]:
    states = {}
    for fid in ws.list_features():
        st = Feature(ws, fid).load("state")
        if st:
            states[fid] = st
    kids: Dict[Optional[str], List[str]] = {}
    for fid, st in states.items():
        parent = st.get("parent") if st.get("parent") in states else None
        kids.setdefault(parent, []).append(fid)
    out: List[Dict[str, Any]] = []

    def walk(fid: str, depth: int) -> None:
        out.append({"feature_id": fid, "depth": depth, "state": states[fid]})
        for c in sorted(kids.get(fid, []), key=id_order):
            walk(c, depth + 1)

    for fid in sorted(kids.get(None, []), key=id_order):
        walk(fid, 0)
    return out
