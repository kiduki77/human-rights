from __future__ import annotations

import json
import re
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


def plugin_templates(ws: Workspace) -> Path:
    from runtime.i18n import lang_of

    lang = lang_of(ws)
    localized = PLUGIN_TEMPLATES / lang
    return localized if lang != "en" and localized.is_dir() else PLUGIN_TEMPLATES


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
    return plugin_templates(ws)


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
        "source": "plugin" if src == plugin_templates(ws) else str(src),
        "plugin_version": plugin_version(),
        "installed_at": now(),
        "files": files,
    })
    return out


def resolve(ws: Workspace, name: str) -> Path:
    local = _repo_dir(ws) / name
    if local.exists():
        return local
    p = plugin_templates(ws) / name
    if not p.exists():
        p = PLUGIN_TEMPLATES / name
    if not p.exists():
        raise HRError(f"no template named {name}")
    return p


FLOW_SECTION_RE = re.compile(r"<!-- flow:start -->.*?<!-- flow:end -->\n", re.S)
TASK_SLOTS = {
    "en": {
        "title": "[FILL: task title]", "purpose": "[FILL: the single change this task is responsible for]",
        "deps": "[FILL: 'none' if none]", "risk": "[FILL: low/medium/high]", "review": "[FILL: required/optional]",
        "boundary": "[FILL: modules/paths this task may change. Anything outside goes back through `hr scope-change`]",
        "tests": "| [FILL: TEST-...] | | not run |",
        "result": "[FILL: after implementation: commit SHA, what changed in 1-2 lines, remaining issues]",
    },
    "ko": {
        "title": "[FILL: 작업 제목]", "purpose": "[FILL: 이 작업이 책임지는 단 하나의 변경]",
        "deps": "[FILL: 없으면 '없음']", "risk": "[FILL: 낮음/보통/높음]", "review": "[FILL: 필수/선택]",
        "boundary": "[FILL: 이 작업이 바꿀 수 있는 모듈/경로. 그 밖은 `hr scope-change` 로 다시 승인]",
        "tests": "| [FILL: TEST-...] | | 미실행 |",
        "result": "[FILL: 구현 후: 커밋 SHA, 무엇이 바뀌었는지 1-2줄, 남은 문제]",
    },
}
REVIEW_KO = {"required": "필수", "optional": "선택"}


def _fill_task(text: str, task: Dict[str, Any], tests: Dict[str, Dict[str, Any]], lang: str = "en") -> str:
    from runtime.i18n import t, value

    slots = TASK_SLOTS.get(lang, TASK_SLOTS["en"])
    deps = ", ".join(task.get("depends_on", [])) or t(lang, "task_none")
    ac = "\n".join(f"- {a['id']}: {a['text']}" for a in task.get("acceptance_criteria", [])) or "- [FILL: AC-...]"
    paths = ", ".join(f"`{p}`" for p in (task.get("scope") or {}).get("paths", [])) or "[FILL: paths]"
    not_run = t(lang, "task_not_run")
    rows = "\n".join(
        f"| {v} | {('`' + tests[v]['command'] + '`') if tests.get(v, {}).get('command') else (tests.get(v, {}).get('procedure') or '-')} | {not_run} |"
        for v in task.get("verification", [])
    )
    review = task.get("human_review", "optional")
    repl = [
        ("[FILL: TASK-001]", task["id"]),
        (slots["title"], task.get("title", "")),
        (slots["purpose"], task.get("purpose", "")),
        (slots["deps"], deps),
        (slots["risk"], value(lang, "risk", task.get("risk", "-"))),
        (slots["review"], REVIEW_KO.get(review, review) if lang == "ko" else review),
        ("- [FILL: AC-...]", ac),
        (slots["boundary"], t(lang, "task_boundary", paths=paths)),
        (slots["tests"], rows or "| - | - | - |"),
        (slots["result"], t(lang, "task_not_implemented")),
    ]
    for old, new in repl:
        text = text.replace(old, new)
    if task.get("changes_flow") is True:
        text = text.replace("<!-- flow:start -->\n", "").replace("<!-- flow:end -->\n", "")
    else:
        text = FLOW_SECTION_RE.sub("", text)
    return text


def scaffold(feature: Feature, names: List[str], overwrite: bool = False) -> Dict[str, List[str]]:
    from runtime.i18n import lang_of

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
                write_text_atomic(dest, _fill_task(tmpl, task, tests, lang_of(feature.ws)))
                out["created"].append(dest.relative_to(feature.dir).as_posix())
            continue
        if name not in DOCS:
            raise HRError(f"unknown document {name!r} (choose from: {', '.join(list(DOCS) + ['tasks'])})")
        tmpl_name, rel = DOCS[name]
        dest = feature.dir / rel
        if dest.exists() and not overwrite:
            out["skipped_existing"].append(rel)
            continue
        text = (resolve(feature.ws, tmpl_name).read_text(encoding="utf-8")
                .replace("[FILL: feature name]", title).replace("[FILL: 기능 이름]", title))
        write_text_atomic(dest, text)
        out["created"].append(rel)
    if out["created"]:
        feature.emit("docs_scaffolded", files=out["created"])
    return out
