from __future__ import annotations

import re
from typing import Any, Dict, List

from runtime import redpill
from runtime.common import fingerprint, write_text_atomic
from runtime.state.store import Feature

BLOCK_RE = r"<!-- hr:{name}:start -->.*?<!-- hr:{name}:end -->"
PLACEHOLDER_RE = re.compile(r"\[FILL(?::[^\]]*)?\]")

STRUCTURE = {
    "overview.md": {"blocks": ["status", "results"], "min_sections": 4},
    "requirements.md": {"blocks": [], "min_sections": 3},
    "design.md": {"blocks": ["tasks"], "min_sections": 3},
    "verification.md": {"blocks": ["results"], "min_sections": 2},
}
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

    def gate(required: bool, s: Dict[str, Any]) -> str:
        if not required:
            return "not required"
        if s["valid"]:
            ap = s["approval"]
            return f"approved ({ap['approver']}, {ap['approved_at']})"
        return "pending"

    lines = [
        "| Item | Value |",
        "|---|---|",
        f"| State | **{STATE_LABELS.get(st['state'], st['state'])}** (`{st['state']}`) |",
        f"| Mode | {st.get('mode') or 'unclassified'} |",
        f"| Design approval | {gate(st['required_gates']['design'], ds)} |",
        f"| Final approval | {gate(st['required_gates']['final'], fs)} |",
        f"| Next human decision | {next_human_decision(feature, st) or 'none'} |",
    ]
    return "\n".join(lines)


def tasks_block(feature: Feature) -> str:
    from runtime.verification.plan_check import topo_order

    graph = feature.task_graph()
    by_id = {t["id"]: t for t in graph.get("tasks", [])}
    if not by_id:
        return "_no tasks_"
    lines = ["| Task | Purpose | Depends on | Risk | Status |", "|---|---|---|---|---|"]
    for tid in topo_order(graph):
        t = by_id[tid]
        lines.append(
            f"| [{tid}](tasks/{tid}.md) | {t.get('title') or t.get('purpose', '')} | "
            f"{', '.join(t.get('depends_on', [])) or '-'} | {t.get('risk', '-')} | {t.get('status', 'planned')} |"
        )
    return "\n".join(lines)


def results_block(feature: Feature) -> str:
    from runtime.verification import evidence

    fp = fingerprint(feature.ws.root)
    summ = evidence.summarize(feature.test_plan(), feature.test_results(), fp)
    if not summ["rows"]:
        return "_no required tests_"
    code = (fp.get("commit_sha") or "no-git")[:10] + (" (+uncommitted changes)" if fp.get("dirty") else "")
    lines = [f"Verified code: `{code}`", "", "| Requirement | Test | Level | Result | Evidence |", "|---|---|---|---|---|"]
    mark = {
        "passed": "✅ pass", "failed": "❌ fail", "stale": "⚠️ not re-run since code changed", "not_run": "⏳ not run",
        "passed_uncommitted": "✅ pass (uncommitted)", "failed_uncommitted": "❌ fail (uncommitted)",
        "unbound_passed": "✅ pass (not version-bound)", "unbound_failed": "❌ fail (not version-bound)",
    }
    for r in summ["rows"]:
        t = r["test"]
        run = r["run"] or {}
        ev = run.get("log_ref") or run.get("evidence") or "-"
        lines.append(
            f"| {', '.join(t.get('requirement_ids', [])) or '-'} | {t['id']} {t.get('title', '')} | {t.get('level')} | "
            f"{mark.get(r['status'], r['status'])} | {ev} |"
        )
    return "\n".join(lines)


def render(feature: Feature) -> List[str]:
    updated = []
    blocks = {
        "overview.md": {"status": status_block, "tasks": tasks_block, "results": results_block},
        "verification.md": {"results": results_block, "status": status_block},
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
        raw_log_lines = sum(1 for l in lines if re.match(r"^\s*(\[?\d{4}-\d{2}-\d{2}[T ][\d:]+|Traceback|\s+at .+\(.+:\d+\))", l))
        if raw_log_lines > 10:
            warnings.append(f"{fname}: {raw_log_lines} lines look like raw logs - move them to details/ and link")
    return {"errors": errors, "warnings": warnings}
