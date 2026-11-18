from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime.common import HRError, now, read_json, sha256_text_file, write_json_atomic, write_text_atomic
from runtime.state.store import Feature, Workspace

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_TEMPLATES = PLUGIN_ROOT / "templates"
MANIFEST = ".installed.json"

DOCS = {
    "overview": ("overview.md", "overview.md"),
    "requirements": ("requirements.md", "requirements.md"),
    "design": ("design.md", "design.md"),
    "verification": ("verification.md", "verification.md"),
    "l0-summary": ("l0-summary.md", "overview.md"),
    "review-report": ("review-report.md", "review-report.md"),
    "codebase": ("details-codebase.md", "details/codebase.md"),
    "research": ("details-research.md", "details/research.md"),
}


def plugin_version() -> str:
    data = read_json(PLUGIN_ROOT / ".claude-plugin" / "plugin.json", {}) or {}
    return data.get("version", "unknown")


def _repo_dir(ws: Workspace) -> Path:
    return ws.wf / "templates"


def _source_dir(ws: Workspace, source: Optional[str]) -> Path:
    if source:
        p = Path(source)
        p = p if p.is_absolute() else (ws.root / p)
        if not p.is_dir():
            raise HRError(f"template source is not a directory: {p}")
        return p.resolve()
    manifest = read_json(_repo_dir(ws) / MANIFEST, {}) or {}
    if manifest.get("source") and manifest["source"] != "plugin":
        p = Path(manifest["source"])
        if p.is_dir():
            return p
    return PLUGIN_TEMPLATES


def status(ws: Workspace, source: Optional[str] = None) -> List[Dict[str, Any]]:
    src = _source_dir(ws, source)
    dest = _repo_dir(ws)
    manifest = read_json(dest / MANIFEST, {}) or {}
    installed = manifest.get("files", {})
    rows = []
    for p in sorted(src.glob("*.md")):
        name = p.name
        cur = sha256_text_file(dest / name)
        rows.append({
            "name": name,
            "installed": cur is not None,
            "customized": cur is not None and installed.get(name) is not None and cur != installed[name],
            "outdated": installed.get(name) is not None and sha256_text_file(p) != installed[name],
        })
    return rows


def install(ws: Workspace, source: Optional[str] = None, force: bool = False) -> Dict[str, List[str]]:
    ws.require_init()
    src = _source_dir(ws, source)
    dest = _repo_dir(ws)
    dest.mkdir(parents=True, exist_ok=True)
    manifest = read_json(dest / MANIFEST, {}) or {}
    files = manifest.get("files", {})
    out: Dict[str, List[str]] = {"copied": [], "kept_customized": [], "unchanged": []}
    for row in status(ws, source):
        name = row["name"]
        if row["customized"] and not force:
            out["kept_customized"].append(name)
            continue
        text = (src / name).read_text(encoding="utf-8")
        if row["installed"] and not row["outdated"] and not row["customized"] and not force:
            out["unchanged"].append(name)
            continue
        write_text_atomic(dest / name, text)
        files[name] = sha256_text_file(dest / name)
        out["copied"].append(name)
    write_json_atomic(dest / MANIFEST, {
        "source": "plugin" if src == PLUGIN_TEMPLATES else str(src),
        "plugin_version": plugin_version(),
        "installed_at": now(),
        "files": files,
    })
    return out


def resolve(ws: Workspace, name: str) -> Path:
    local = _repo_dir(ws) / name
    if local.exists():
        return local
    p = PLUGIN_TEMPLATES / name
    if not p.exists():
        raise HRError(f"no template named {name}")
    return p


def _fill_task(text: str, task: Dict[str, Any], tests: Dict[str, Dict[str, Any]]) -> str:
    deps = ", ".join(task.get("depends_on", [])) or "none"
    ac = "\n".join(f"- {a['id']}: {a['text']}" for a in task.get("acceptance_criteria", [])) or "- [FILL: AC-...]"
    paths = ", ".join(f"`{p}`" for p in (task.get("scope") or {}).get("paths", [])) or "[FILL: paths]"
    rows = "\n".join(
        f"| {v} | {('`' + tests[v]['command'] + '`') if tests.get(v, {}).get('command') else (tests.get(v, {}).get('procedure') or '-')} | not run |"
        for v in task.get("verification", [])
    )
    repl = [
        ("[FILL: TASK-001]", task["id"]),
        ("[FILL: task title]", task.get("title", "")),
        ("[FILL: the single change this task is responsible for]", task.get("purpose", "")),
        ("[FILL: 'none' if none]", deps),
        ("[FILL: low/medium/high]", task.get("risk", "-")),
        ("[FILL: required/optional]", task.get("human_review", "optional")),
        ("- [FILL: AC-...]", ac),
        ("[FILL: modules/paths this task may change. Anything outside goes back through `hr scope-change`]",
         f"{paths}. Anything outside goes back through `hr scope-change`."),
        ("| [FILL: TEST-...] | | not run |", rows or "| - | - | - |"),
        ("[FILL: after implementation: commit SHA, what changed in 1-2 lines, remaining issues]", "Not implemented yet."),
    ]
    for old, new in repl:
        text = text.replace(old, new)
    return text


def scaffold(feature: Feature, names: List[str], overwrite: bool = False) -> Dict[str, List[str]]:
    st = feature.state()
    title = st.get("title", "")
    out: Dict[str, List[str]] = {"created": [], "skipped_existing": []}
    if not names:
        names = ["l0-summary"] if st.get("mode") in ("L0", "L1") else ["overview", "requirements", "design", "verification", "codebase", "tasks"]
    for name in names:
        if name == "tasks":
            tmpl = resolve(feature.ws, "task.md").read_text(encoding="utf-8")
            tests = {t["id"]: t for t in feature.test_plan().get("tests", [])}
            for task in feature.task_graph().get("tasks", []):
                dest = feature.dir / "tasks" / f"{task['id']}.md"
                if dest.exists() and not overwrite:
                    out["skipped_existing"].append(dest.relative_to(feature.dir).as_posix())
                    continue
                write_text_atomic(dest, _fill_task(tmpl, task, tests))
                out["created"].append(dest.relative_to(feature.dir).as_posix())
            continue
        if name not in DOCS:
            raise HRError(f"unknown document {name!r} (choose from: {', '.join(list(DOCS) + ['tasks'])})")
        tmpl_name, rel = DOCS[name]
        dest = feature.dir / rel
        if dest.exists() and not overwrite:
            out["skipped_existing"].append(rel)
            continue
        text = resolve(feature.ws, tmpl_name).read_text(encoding="utf-8").replace("[FILL: feature name]", title)
        write_text_atomic(dest, text)
        out["created"].append(rel)
    if out["created"]:
        feature.emit("docs_scaffolded", files=out["created"])
    return out
