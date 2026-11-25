from __future__ import annotations

import re
from typing import Any, Dict, List

from runtime import redpill
from runtime.common import fingerprint, write_text_atomic
from runtime.i18n import lang_of, mark, state_label, t, value
from runtime.state.store import Feature

BLOCK_RE = r"<!-- hr:{name}:start -->.*?<!-- hr:{name}:end -->"
PLACEHOLDER_RE = re.compile(r"\[FILL(?::[^\]]*)?\]")

GROUP_STRUCTURE = {
    "overview.md": {"blocks": ["status", "features", "shared", "excluded", "results", "steps"], "min_sections": 4},
}
STRUCTURE = {
    "overview.md": {"blocks": ["status", "decisions", "results"], "min_sections": 4},
    "requirements.md": {"blocks": [], "min_sections": 3},
    "design.md": {"blocks": ["tasks", "impact"], "min_sections": 3},
    "verification.md": {"blocks": ["results", "steps", "review"], "min_sections": 2},
}
CELL_SPLIT = re.compile(r"(?<!\\)\|")
ROW_ID = re.compile(r"\[?([A-Za-z]+-\d+)")
FOCUS_MAX = 7
FOCUS_RANK = {"flag": 0, "changed": 1, "task": 2, "assumed_high": 3, "not_user": 4, "assumed_medium": 5}
MERMAID_RE = re.compile(r"```mermaid\s*\n(.*?)```", re.S)
MERMAID_KINDS = ("flowchart", "graph", "sequenceDiagram", "stateDiagram", "stateDiagram-v2", "classDiagram",
                 "erDiagram", "gantt", "journey", "timeline", "mindmap")


def _replace_block(text: str, name: str, body: str) -> str:
    block = f"<!-- hr:{name}:start -->\n{body.rstrip()}\n<!-- hr:{name}:end -->"
    pat = re.compile(BLOCK_RE.format(name=re.escape(name)), re.S)
    if pat.search(text):
        return pat.sub(lambda _: block, text)
    return text


def status_block(feature: Feature) -> str:
    from runtime.approvals.gates import design_status, final_status
    from runtime.state.machine import STATE_LABELS, next_human_decision

    st = feature.state()
    ds, fs = design_status(feature, st), final_status(feature, st)
    lang = lang_of(feature.ws)
    if st.get("kind") == "group":
        return _group_status_block(feature, st, lang)

    def gate(required: bool, s: Dict[str, Any]) -> str:
        if not required:
            return t(lang, "not_required")
        if s["valid"]:
            ap = s["approval"]
            return t(lang, "approved", who=ap["approver"], at=ap["approved_at"])
        return t(lang, "pending")

    label = state_label(lang, st["state"], STATE_LABELS.get(st["state"], st["state"]))
    lines = [
        f"| {t(lang, 'item')} | {t(lang, 'value')} |",
        "|---|---|",
        f"| {t(lang, 'state')} | **{label}** (`{st['state']}`) |",
        f"| {t(lang, 'mode')} | {st.get('mode') or t(lang, 'unclassified')} |",
        f"| {t(lang, 'design_approval')} | {gate(st['required_gates']['design'], ds)} |",
        f"| {t(lang, 'final_approval')} | {gate(st['required_gates']['final'], fs)} |",
        f"| {t(lang, 'next_decision')} | {next_human_decision(feature, st, lang) or t(lang, 'none')} |",
    ]
    if st.get("parent"):
        lines.insert(3, f"| {t(lang, 'part_of')} | {st['parent']} |")
    return "\n".join(lines)


def _group_status_block(feature: Feature, st: Dict[str, Any], lang: str) -> str:
    from runtime import groups
    from runtime.state.machine import STATE_LABELS, next_human_decision

    ss = groups.split_status(feature, st)
    if ss["valid"]:
        approval = t(lang, "approved", who=ss["approval"]["approver"], at=ss["approval"]["approved_at"])
    else:
        approval = t(lang, "pending")
    rows = groups.children_of(feature, st)
    total = len(rows) or len(groups.split_of(feature).get("children", []))
    done = sum(1 for r in rows if r["state"] == "completed")
    label = state_label(lang, st["state"], STATE_LABELS.get(st["state"], st["state"]))
    lines = [
        f"| {t(lang, 'item')} | {t(lang, 'value')} |",
        "|---|---|",
        f"| {t(lang, 'state')} | **{label}** (`{st['state']}`) |",
        f"| {t(lang, 'mode')} | {t(lang, 'group')} |",
        f"| {t(lang, 'split_approval')} | {approval} |",
        f"| {t(lang, 'progress')} | {t(lang, 'progress_value', done=done, total=total)} |",
        f"| {t(lang, 'next_decision')} | {next_human_decision(feature, st, lang) or t(lang, 'none')} |",
    ]
    if st.get("parent"):
        lines.insert(3, f"| {t(lang, 'part_of')} | {st['parent']} |")
    source = groups.split_of(feature).get("source") or {}
    if source.get("path"):
        lines.insert(3, f"| {t(lang, 'source_document')} | `{_cell(source['path'])}` |")
    return "\n".join(lines)


def _node_label(text: Any) -> str:
    return re.sub(r"[\[\]{}()\"|<>`]", " ", str(text or "")).strip()


def _child_link(feature: Feature, child_id: str) -> str:
    import os

    overview = feature.ws.dir_of(child_id) / "overview.md"
    if not overview.is_file():
        return child_id
    rel = os.path.relpath(str(overview), str(feature.dir)).replace(os.sep, "/")
    return f"[{child_id}]({rel})"


def features_block(feature: Feature) -> str:
    from runtime import groups
    from runtime.state.machine import STATE_LABELS

    lang = lang_of(feature.ws)
    st = feature.state()
    kids = groups.split_of(feature).get("children", [])
    if not kids:
        return t(lang, "no_features")
    linked = {r["key"]: r for r in groups.children_of(feature, st)}
    order = {k: i for i, k in enumerate(groups._order(feature))}
    kids = sorted(kids, key=lambda c: order.get(c.get("key"), len(order)))
    ids = {c.get("key"): f"f{i}" for i, c in enumerate(kids, 1)}
    graph = ["```mermaid", "flowchart LR"]
    for c in kids:
        graph.append(f"  {ids[c.get('key')]}[\"{_node_label(c.get('title'))}\"]")
    for c in kids:
        for d in c.get("depends_on", []) or []:
            if d in ids:
                graph.append(f"  {ids[d]} --> {ids[c.get('key')]}")
    graph.append("```")
    with_sources = any(c.get("sources") for c in kids)
    with_code = any(c.get("code_status") for c in kids)
    head = ["#", t(lang, "feature"), t(lang, "outcome"), t(lang, "verify_alone"), t(lang, "built_on")]
    if with_sources:
        head.append(t(lang, "sources"))
    if with_code:
        head.append(t(lang, "code_now"))
    head += [t(lang, "expected_mode"), t(lang, "state")]
    lines = graph + ["", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for i, c in enumerate(kids, 1):
        link = linked.get(c.get("key"))
        name = f"**{_cell(c.get('title'))}** (`{c.get('key')}`)"
        if link:
            name += f"<br>{_child_link(feature, link['feature_id'])}"
        cells = [str(i), name, _cell(c.get("outcome")), _cell(c.get("verify_alone")),
                 ", ".join(c.get("depends_on", []) or []) or "-"]
        if with_sources:
            cells.append(_cell(", ".join(str(s) for s in c.get("sources") or []) or "-"))
        if with_code:
            cells.append(value(lang, "code_status", c.get("code_status") or "-"))
        state = "-"
        if link:
            state = state_label(lang, link["state"], STATE_LABELS.get(link["state"], link["state"]))
        cells += [link["mode"] if link and link["mode"] else (c.get("expected_mode") or "-"), state]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def shared_block(feature: Feature) -> str:
    from runtime import groups

    lang = lang_of(feature.ws)
    return _decision_tables(lang, groups.split_of(feature).get("shared_decisions") or [], []) or t(lang, "no_shared")


def excluded_block(feature: Feature) -> str:
    from runtime import groups

    lang = lang_of(feature.ws)
    split = groups.split_of(feature)
    out: List[str] = []
    left = split.get("excluded") or []
    if left:
        out += [f"| {t(lang, 'left_out')} | {t(lang, 'why_not')} | {t(lang, 'sources')} |", "|---|---|---|"]
        out += [f"| {_cell(e.get('item'))} | {_cell(e.get('reason'))} | "
                f"{_cell(', '.join(str(s) for s in e.get('sources') or []) or '-')} |" for e in left]
    unread = (split.get("source") or {}).get("unread") or []
    if unread:
        out += ["", f"**⚠️ {t(lang, 'unread')}**", "", f"| {t(lang, 'part')} | {t(lang, 'reason')} |", "|---|---|"]
        out += [f"| {_cell(u.get('ref'))} | {_cell(u.get('reason'))} |" for u in unread]
    return "\n".join(out).strip() or t(lang, "no_excluded")


def tasks_block(feature: Feature) -> str:
    from runtime.verification.plan_check import topo_order

    graph = feature.task_graph()
    lang = lang_of(feature.ws)
    by_id = {x["id"]: x for x in graph.get("tasks", [])}
    if not by_id:
        return t(lang, "no_tasks")
    head = [t(lang, k) for k in ("task", "purpose", "depends_on", "risk", "status")]
    lines = ["| " + " | ".join(head) + " |", "|---|---|---|---|---|"]
    for tid in topo_order(graph):
        x = by_id[tid]
        lines.append(
            f"| [{tid}](tasks/{tid}.md) | {x.get('title') or x.get('purpose', '')} | "
            f"{', '.join(x.get('depends_on', [])) or '-'} | {value(lang, 'risk', x.get('risk', '-'))} | "
            f"{value(lang, 'task_status', x.get('status', 'planned'))} |"
        )
    return "\n".join(lines)


def _cell(text: Any) -> str:
    return str(text if text is not None else "-").replace("|", "\\|").replace("\n", " ")


def impact_block(feature: Feature) -> str:
    lang = lang_of(feature.ws)
    imp = feature.requirements().get("impact")
    if not isinstance(imp, dict):
        return t(lang, "no_impact")
    terms = ", ".join(f"`{_cell(s)}`" for s in imp.get("searched") or []) or "-"
    lines = [f"**{t(lang, 'impact_concept')}:** {_cell(imp.get('concept'))}  ", f"**{t(lang, 'impact_searched')}:** {terms}", ""]
    rows = [c for c in imp.get("consumers") or [] if isinstance(c, dict)]
    if rows:
        head = [t(lang, k) for k in ("impact_where", "impact_uses", "impact_relation", "impact_covered", "impact_evidence")]
        lines += ["| " + " | ".join(head) + " |", "|---|---|---|---|---|"]
        for c in rows:
            covered = ", ".join(c.get("tasks") or c.get("tests") or []) or c.get("reason") or "-"
            lines.append(f"| {_cell(c.get('where'))} | {_cell(c.get('uses'))} | "
                         f"{value(lang, 'relation', c.get('relation', '-'))} | {_cell(covered)} | {_cell(c.get('evidence'))} |")
    else:
        lines.append(t(lang, "impact_none"))
    again = feature.state().get("impact_recheck")
    if again:
        current = again.get("code_tree") == fingerprint(feature.ws.root).get("code_tree")
        lines += ["", t(lang, "impact_rechecked" if current else "impact_recheck_stale",
                        sha=str(again.get("commit_sha") or "-")[:10],
                        terms=", ".join(f"`{_cell(s)}`" for s in again.get("searched") or []))]
    return "\n".join(lines)


def _decided(lang: str, x: Dict[str, Any]) -> str:
    d = x.get("disposition") or {}
    if not d:
        return t(lang, "disposition_none")
    kind = d["kind"]
    if kind == "accepted":
        kind = "risk" if x.get("source") == "tester" else "accepted"
    return t(lang, "disposition_" + kind, who=_cell(d.get("by")), reason=_cell(d.get("reason")),
             review=d.get("review") or "-", sha=str(d.get("commit_sha") or "-")[:10], run=d.get("run") or "-")


def review_block(feature: Feature) -> str:
    from runtime import review

    lang = lang_of(feature.ws)
    data = review.load(feature)
    lines: List[str] = []
    if not data["reviews"]:
        lines.append(t(lang, "no_review"))
    else:
        last = data["reviews"][-1]
        current = last.get("code_tree") == fingerprint(feature.ws.root).get("code_tree")
        lines.append(t(lang, "review_done" if current else "review_stale", id=last["id"], who=_cell(last.get("by")),
                       sha=str(last.get("commit_sha") or "-")[:10], files=len(last.get("files_read") or []),
                       n=len(last.get("findings") or [])))
        if current and not review._code(data["findings"]):
            lines.append(t(lang, "review_none"))
    if not data["findings"]:
        return "\n".join(lines)
    head = [t(lang, k) for k in ("finding", "impact_where", "review_what", "review_disposition")]
    lines += ["", "| " + " | ".join(head) + " |", "|---|---|---|---|"]
    for x in data["findings"]:
        if x.get("source") == review.TESTER:
            what = f"**{t(lang, 'tester_found')}.** {_cell(x.get('what'))}"
            where = f"{x['test']} ({x['run']})"
        else:
            what = f"**{value(lang, 'finding_kind', x['kind'])}.** {_cell(x.get('what'))}"
            if x.get("existing"):
                what += " (" + t(lang, "review_existing", place=_cell(x["existing"])) + ")"
            where = review._place(x)
        lines.append(f"| {x['id']} | `{_cell(where)}` | {what} | {_decided(lang, x)} |")
    return "\n".join(lines)


def _duration(lang: str, seconds: Any) -> str:
    try:
        s = float(seconds)
    except (TypeError, ValueError):
        return ""
    if s <= 0:
        return ""
    return t(lang, "minutes", n=max(1, round(s / 60))) if s >= 60 else t(lang, "seconds", n=int(s))


def results_block(feature: Feature) -> str:
    from runtime.verification import evidence

    fp = fingerprint(feature.ws.root)
    lang = lang_of(feature.ws)
    plan = feature.test_plan()
    summ = evidence.summarize(plan, feature.test_results(), fp)
    if not summ["rows"]:
        return t(lang, "no_tests")
    code = (fp.get("commit_sha") or "no-git")[:10] + (t(lang, "uncommitted") if fp.get("dirty") else "")
    lines = [f"{t(lang, 'verified_code')}: `{code}`"]
    reg = plan.get("regression") or {}
    if reg.get("scope"):
        lines.append(f"{t(lang, 'regression_scope')}: **{value(lang, 'regression', reg['scope'])}** - {_cell(reg.get('rationale'))}")
    total = sum(float(r["test"].get("estimated_seconds") or 0) for r in summ["rows"])
    if total:
        lines.append(f"{t(lang, 'estimated_total')}: {_duration(lang, total)}")
    group = feature.state().get("kind") == "group"
    head = [t(lang, k) for k in ("features" if group else "requirement", "test", "run_by", "pass_criteria", "result",
                                 "evidence")]
    lines += ["", "| " + " | ".join(head) + " |", "|---|---|---|---|---|---|"]
    for r in summ["rows"]:
        x = r["test"]
        run = r["run"] or {}
        ev = run.get("log_ref") or run.get("evidence") or "-"
        runner = evidence.runner_of(x)
        who = value(lang, "runner", runner)
        est = _duration(lang, x.get("estimated_seconds"))
        if est:
            who += f" (~{est})"
        criteria = _cell(x.get("pass_criteria"))
        if x.get("steps"):
            criteria += " " + t(lang, "see_steps", n=len(x["steps"]))
        result = mark(lang, r["status"])
        if r.get("carried"):
            result += " " + t(lang, "carried", sha=(run.get("commit_sha") or "")[:7])
        elif r["status"] == "passed" and run.get("status") == "agent_passed":
            result += " " + t(lang, "by_agent")
        elif r["status"] == "passed" and run.get("status") == "manual_passed":
            result += " " + t(lang, "by_human", who=str(run.get("recorded_by", "")).replace("human:", ""))
        lines.append(
            f"| {', '.join(x.get('children' if group else 'requirement_ids') or []) or '-'} | {x['id']} {_cell(x.get('title', ''))} | {who} | "
            f"{criteria} | {result} | {ev} |"
        )
    return "\n".join(lines)


def steps_block(feature: Feature) -> str:
    from runtime import review
    from runtime.verification import evidence

    lang = lang_of(feature.ws)
    out: List[str] = []
    for x in evidence.required_tests(feature.test_plan()):
        steps = x.get("steps") or []
        if not steps:
            continue
        runner = evidence.runner_of(x)
        title = f"**{x['id']} {x.get('title', '')}** - {value(lang, 'runner', runner)}"
        if runner == "human" and x.get("human_reason"):
            title += f" ({t(lang, 'human_reason')}: {x['human_reason']})"
        if x.get("environment"):
            title += f" · {t(lang, 'environment')}: {x['environment']}"
        out += [title, "", f"| # | {t(lang, 'step_do')} | {t(lang, 'step_expect')} |", "|---|---|---|"]
        out += [f"| {i} | {_cell(s.get('do'))} | {_cell(s.get('expect'))} |" for i, s in enumerate(steps, 1)]
        out.append("")
        found = [y for y in review.load(feature)["findings"] if y.get("source") == review.TESTER and y["test"] == x["id"]]
        if found:
            out += [f"**{t(lang, 'test_findings')}**", ""]
            out += [f"- {y['id']} ({y['run']}): {_cell(y['what'])}. {_decided(lang, y)}" for y in found]
            out.append("")
    return "\n".join(out).rstrip() or t(lang, "no_steps")


def decisions_block(feature: Feature) -> str:
    lang = lang_of(feature.ws)
    req = feature.requirements()
    return _decision_tables(lang, req.get("decisions", []), req.get("assumptions", [])) or t(lang, "no_decisions")


def _decision_tables(lang: str, decisions: List[Dict[str, Any]], assumptions: List[Dict[str, Any]]) -> str:
    out: List[str] = []
    changed = [d for d in decisions if str(d.get("overrides_user_answer") or "").strip()]
    if changed:
        head = [t(lang, k) for k in ("question", "you_said", "now", "why")]
        out += [f"**⚠️ {t(lang, 'changed_from_answer')}**", "", "| ID | " + " | ".join(head) + " |", "|---|---|---|---|---|"]
        out += [f"| {d.get('id')} | {_cell(d.get('question'))} | {_cell(d['overrides_user_answer'])} | "
                f"**{_cell(d.get('answer'))}** | {_cell(d.get('reason'))} |" for d in changed]
        out.append("")
    if decisions:
        head = [t(lang, k) for k in ("question", "decision", "decided_by")]
        out += ["| ID | " + " | ".join(head) + " |", "|---|---|---|---|"]
        out += [f"| {d.get('id')} | {_cell(d.get('question'))} | {_cell(d.get('answer'))} | "
                f"{value(lang, 'decided_by', d.get('decided_by'))} |" for d in decisions]
        out.append("")
    if assumptions:
        out += [f"**{t(lang, 'assumed_for_you')}**", "", f"| ID | {t(lang, 'assumption')} | {t(lang, 'risk')} |", "|---|---|---|"]
        out += [f"| {a.get('id')} | {_cell(a.get('text'))} | {value(lang, 'risk', a.get('risk', '-'))} |" for a in assumptions]
    return "\n".join(out).rstrip()


def _rows(text: str) -> List[List[str]]:
    return [[c.strip() for c in CELL_SPLIT.split(l)[1:-1]] for l in text.split("\n") if l.startswith("|")]


def _shown_block(text: str, name: str) -> str:
    m = re.search(BLOCK_RE.format(name=re.escape(name)), text, re.S)
    return m.group(0) if m else ""


def _raw(lang: str, kind: str, label: str, options: Any) -> str:
    return next((k for k in options if value(lang, kind, k) == label), label)


def _clip(text: str, n: int = 60) -> str:
    return text if len(text) <= n else text[: n - 3].rstrip() + "..."


def focus_block(feature: Feature, text: str) -> str:
    from runtime.routing.router import ALL_FLAGS

    lang = lang_of(feature.ws)
    cap = int(feature.ws.config().get("docs", {}).get("focus_max", FOCUS_MAX))
    found: Dict[str, Dict[str, Any]] = {}

    def add(kind: str, cell: str, title: str, reason: str) -> None:
        m = ROW_ID.match(cell)
        if not m:
            return
        item = found.setdefault(m.group(1), {"rank": FOCUS_RANK[kind], "title": title, "why": []})
        item["rank"] = min(item["rank"], FOCUS_RANK[kind])
        item["why"].append(reason)

    for row in _rows(_shown_block(text, "tasks")):
        if len(row) == 5 and _raw(lang, "risk", row[3], ("high",)) == "high":
            add("task", row[0], row[1], t(lang, "focus_task", risk=value(lang, "risk", "high")))
    for row in _rows(_shown_block(text, "decisions")):
        if len(row) == 5:
            add("changed", row[0], row[1], t(lang, "focus_changed"))
        elif len(row) == 4:
            who = _raw(lang, "decided_by", row[3], ("user", "default", "code", "group"))
            if who != "user":
                add("not_user", row[0], row[1], t(lang, "focus_not_user", who=row[3]))
        elif len(row) == 3:
            risk = _raw(lang, "risk", row[2], ("medium", "high"))
            if risk in ("medium", "high"):
                add("assumed_" + risk, row[0], row[1], t(lang, "focus_assumed", risk=row[2]))
    flags = (feature.state().get("routing") or {}).get("flags") or []
    lines = [f"- `{f}` ({value(lang, 'flag', f)}): {t(lang, 'focus_flag')}" for f in ALL_FLAGS if f in flags]
    ranked = sorted(found.items(), key=lambda kv: kv[1]["rank"])
    total = len(lines) + len(ranked)
    if not total:
        return t(lang, "focus_none")
    for rid, item in ranked:
        lines.append(f"- **{rid}** {_clip(item['title'])}: {'; '.join(item['why'])}")
    out = [t(lang, "focus_intro"), ""] + lines[:cap]
    if total > cap:
        out += ["", t(lang, "focus_more", n=total - cap)]
    return "\n".join(out)


def render(feature: Feature) -> List[str]:
    updated = []
    blocks = {
        "overview.md": {"status": status_block, "tasks": tasks_block, "impact": impact_block, "results": results_block,
                        "decisions": decisions_block, "features": features_block, "shared": shared_block,
                        "excluded": excluded_block, "steps": steps_block, "review": review_block},
        "verification.md": {"results": results_block, "status": status_block, "steps": steps_block,
                            "review": review_block},
        "design.md": {"tasks": tasks_block, "impact": impact_block},
    }
    for fname, mapping in blocks.items():
        path = feature.dir / fname
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        new = text
        for name, fn in mapping.items():
            if f"<!-- hr:{name}:start -->" in new:
                new = _replace_block(new, name, redpill.inject(feature, fname, name, fn(feature)))
        if fname == "overview.md" and "<!-- hr:focus:start -->" in new:
            new = _replace_block(new, "focus", focus_block(feature, new))
        if new != text:
            write_text_atomic(path, new)
            updated.append(fname)
    return updated


def check_docs(feature: Feature) -> Dict[str, List[str]]:
    planted = redpill.planted_id(feature)
    st = feature.state()
    cfg = feature.ws.config().get("docs", {})
    errors: List[str] = []
    warnings: List[str] = []
    mode = st.get("mode")
    group = st.get("kind") == "group"
    structure = GROUP_STRUCTURE if group else STRUCTURE
    lenient = mode in ("L0", "L1") and not group
    expected = ["overview.md"] if lenient else list(structure)
    for fname in expected:
        path = feature.dir / fname
        if not path.exists():
            errors.append(f"{fname} is missing")
            continue
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        if lenient:
            limit = int(cfg.get("l0_summary_max_lines", 15)) if mode == "L0" else 40
            if len([l for l in lines if l.strip()]) > limit:
                warnings.append(f"{fname}: {mode} summary exceeds {limit} lines - move detail to details/")
        else:
            spec = structure[fname]
            for b in spec["blocks"]:
                if f"<!-- hr:{b}:start -->" not in text:
                    errors.append(f"{fname}: missing generated block <!-- hr:{b}:start/end --> (keep it from the template)")
            sections = sum(1 for l in lines if l.startswith("## "))
            if sections < spec["min_sections"]:
                errors.append(f"{fname}: only {sections} '## ' sections (template has at least {spec['min_sections']})")
            if fname == "overview.md" and len(lines) > int(cfg.get("overview_max_lines", 120)):
                warnings.append(f"overview.md: {len(lines)} lines - aim for 1-2 screens, move detail to details/")
        if PLACEHOLDER_RE.search(text):
            errors.append(f"{fname}: unfilled template placeholders ([FILL: ...]) remain")
        for m in re.finditer(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", text):
            target = m.group(1)
            if re.match(r"^[a-z]+://", target) or target.startswith("mailto:"):
                continue
            if planted and planted in target:
                continue
            if not (path.parent / target).exists() and not (feature.ws.root / target).exists():
                errors.append(f"{fname}: broken link {target}")
        for m in re.finditer(r"```mermaid\s*\n(.*?)```", text, re.S):
            body = m.group(1).strip()
            first = body.splitlines()[0].strip() if body else ""
            if not first.startswith(MERMAID_KINDS):
                errors.append(f"{fname}: Mermaid block does not start with a diagram type: {first[:40]!r}")
            if body.count("[") != body.count("]") or body.count("{") != body.count("}") or body.count("(") != body.count(")"):
                errors.append(f"{fname}: unbalanced brackets in Mermaid block")
        if fname == "design.md" and not lenient and not group and _needs_design_diagram(feature, st) and not MERMAID_RE.search(text):
            errors.append("design.md: this change crosses module or process boundaries (or a task changes a flow) but "
                          "there is no Mermaid diagram - add a sequence, state, or component diagram of what changes")
        raw_log_lines = sum(1 for l in lines if re.match(r"^\s*(\[?\d{4}-\d{2}-\d{2}[T ][\d:]+|Traceback|\s+at .+\(.+:\d+\))", l))
        if raw_log_lines > 10:
            warnings.append(f"{fname}: {raw_log_lines} lines look like raw logs - move them to details/ and link")
    if not lenient and not group:
        for task in feature.task_graph().get("tasks", []):
            if task.get("changes_flow") is not True:
                continue
            rel = f"tasks/{task['id']}.md"
            path = feature.dir / rel
            if not path.exists():
                errors.append(f"{rel} is missing ({task['id']} changes a flow and needs a document with a diagram)")
            elif not MERMAID_RE.search(path.read_text(encoding="utf-8")):
                errors.append(f"{rel}: {task['id']} is marked changes_flow but its document has no Mermaid diagram "
                              "of the interaction it changes")
    from runtime import prose

    hits = prose.check(feature, prose.doc_names(feature))
    if hits:
        target = errors if prose.settings(feature.ws)["mode"] == "error" else warnings
        target += [f"{h} - {prose.ADVICE}" for h in hits[:1]] + hits[1:]
    return {"errors": errors, "warnings": warnings}


def _needs_design_diagram(feature: Feature, st: Dict[str, Any]) -> bool:
    if any(t.get("changes_flow") is True for t in feature.task_graph().get("tasks", [])):
        return True
    scores = (st.get("routing") or {}).get("effective_scores") or {}
    return int(scores.get("scope", 0)) >= 2
