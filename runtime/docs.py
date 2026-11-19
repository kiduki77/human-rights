from __future__ import annotations

import re
from typing import Any, Dict, List

from runtime import redpill
from runtime.common import fingerprint, write_text_atomic
from runtime.i18n import lang_of, mark, state_label, t, value
from runtime.state.store import Feature

BLOCK_RE = r"<!-- hr:{name}:start -->.*?<!-- hr:{name}:end -->"
PLACEHOLDER_RE = re.compile(r"\[FILL(?::[^\]]*)?\]")

STRUCTURE = {
    "overview.md": {"blocks": ["status", "decisions", "results"], "min_sections": 4},
    "requirements.md": {"blocks": [], "min_sections": 3},
    "design.md": {"blocks": ["tasks"], "min_sections": 3},
    "verification.md": {"blocks": ["results", "steps"], "min_sections": 2},
}
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
    return "\n".join(lines)


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
    head = [t(lang, k) for k in ("requirement", "test", "run_by", "pass_criteria", "result", "evidence")]
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
            f"| {', '.join(x.get('requirement_ids', [])) or '-'} | {x['id']} {_cell(x.get('title', ''))} | {who} | "
            f"{criteria} | {result} | {ev} |"
        )
    return "\n".join(lines)


def steps_block(feature: Feature) -> str:
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
    return "\n".join(out).rstrip() or t(lang, "no_steps")


def decisions_block(feature: Feature) -> str:
    lang = lang_of(feature.ws)
    req = feature.requirements()
    decisions = req.get("decisions", [])
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
    assumptions = req.get("assumptions", [])
    if assumptions:
        out += [f"**{t(lang, 'assumed_for_you')}**", "", f"| ID | {t(lang, 'assumption')} | {t(lang, 'risk')} |", "|---|---|---|"]
        out += [f"| {a.get('id')} | {_cell(a.get('text'))} | {value(lang, 'risk', a.get('risk', '-'))} |" for a in assumptions]
    return "\n".join(out).rstrip() or t(lang, "no_decisions")


def render(feature: Feature) -> List[str]:
    updated = []
    blocks = {
        "overview.md": {"status": status_block, "tasks": tasks_block, "results": results_block,
                        "decisions": decisions_block},
        "verification.md": {"results": results_block, "status": status_block, "steps": steps_block},
        "design.md": {"tasks": tasks_block},
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
    lenient = mode in ("L0", "L1")
    expected = ["overview.md"] if lenient else list(STRUCTURE)
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
            spec = STRUCTURE[fname]
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
        if fname == "design.md" and not lenient and _needs_design_diagram(feature, st) and not MERMAID_RE.search(text):
            errors.append("design.md: this change crosses module or process boundaries (or a task changes a flow) but "
                          "there is no Mermaid diagram - add a sequence, state, or component diagram of what changes")
        raw_log_lines = sum(1 for l in lines if re.match(r"^\s*(\[?\d{4}-\d{2}-\d{2}[T ][\d:]+|Traceback|\s+at .+\(.+:\d+\))", l))
        if raw_log_lines > 10:
            warnings.append(f"{fname}: {raw_log_lines} lines look like raw logs - move them to details/ and link")
    if not lenient:
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
    return {"errors": errors, "warnings": warnings}


def _needs_design_diagram(feature: Feature, st: Dict[str, Any]) -> bool:
    if any(t.get("changes_flow") is True for t in feature.task_graph().get("tasks", [])):
        return True
    scores = (st.get("routing") or {}).get("effective_scores") or {}
    return int(scores.get("scope", 0)) >= 2
