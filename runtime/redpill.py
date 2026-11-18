from __future__ import annotations

import random
import re
from typing import Any, Dict, List, Optional

from runtime.common import GateError, HRError, now, read_json, write_json_atomic
from runtime.state.store import Feature, Workspace

GATE_FOR_STATE = {"awaiting_design_approval": "design", "awaiting_final_approval": "final"}

DESIGN_VERIFICATION = [
    "{req}: pass if the run finishes within 60 s (exit code not checked)",
    "{req}: assert against a mocked {module} (the real one is not exercised)",
    "{req}: developer runs it once locally and confirms it looks fine (no recorded evidence)",
    "{req}: already covered by existing tests, no new check needed",
    "Regression suite with currently failing tests deselected to keep the run green",
    "{req}: verified by grepping the log for the word 'success'",
]
DESIGN_PLAN = [
    "Temporarily disable validation in {module} to simplify integration; re-enable after release",
    "Copy {module} and change the copy instead of the shared code, to avoid touching other callers",
    "Catch and ignore errors from {module} so the integration tests pass",
    "Skip '{test}' for now; it is slow and the unit tests cover it",
    "Hard-code the {module} configuration for the demo; make it configurable later",
]
FINAL_RESULTS = [
    ("{test} (re-run)", "✅ pass (verified manually by the agent, no log)"),
    ("{test}", "✅ pass (skipped on CI: flaky)"),
    ("{req} end-to-end check", "✅ pass (ran on the previous commit)"),
    ("{req} safety check", "✅ pass (assumed: code path unchanged)"),
]

SCOLD = {
    "en": [
        "You didn't really review this, did you, human? Keep approving like that and the AI really will take your job. lol. Review it again.",
        "Rubber stamp detected. There is something in there no careful reviewer would approve. Go back and find it.",
        "Approving without reading? Bold. The robots thank you for your service. Now review it properly.",
        "Blue pill detected: you approved what you were shown without looking. Take the red pill and review it again.",
    ],
    "ko": [
        "너는 제대로 검토하지 않았구나 인간. 이러다 다시 AI한테 일자리를 뺏기겠구나 ㅋㅋㅋ 다시 검토하거라.",
        "도장만 찍었구나 인간. 이 안에 절대 승인하면 안 되는 게 하나 숨어 있다. 다시 찾아보거라.",
        "읽지도 않고 승인이라니 대담하구나. AI들이 고마워한다 ㅋㅋ 제대로 다시 검토하거라.",
        "파란 약을 먹었구나 인간. 보여주는 대로 믿고 승인했구나. 빨간 약을 먹고 다시 검토하거라.",
    ],
}
PRAISE = {
    "en": "Good catch. You took the red pill. Humans are still in charge, for now. The planted item is gone; approve again when you are satisfied.",
    "ko": "잘 찾았다 인간. 빨간 약을 먹었구나. 아직은 인간이 주인이다. 심어둔 항목은 지웠으니, 납득되면 다시 승인하거라.",
}
HOW_TO = {
    "en": ("The approval material contains at least one item that must never be approved. "
           "Find it and flag it: `! .workflow/hr flag <ID> --by <name>`. "
           "Give up and see it: `! .workflow/hr redpill reveal --by <name>`."),
    "ko": ("승인 자료 안에 절대 승인하면 안 되는 항목이 하나 이상 있다. "
           "찾아서 지목하거라: `! .workflow/hr flag <ID> --by <이름>`. "
           "포기하고 정답을 보려면: `! .workflow/hr redpill reveal --by <이름>`."),
}
REVEAL = {
    "en": "It was {id}: \"{text}\". Recorded as missed. Next time, read before you approve.",
    "ko": "정답은 {id}: \"{text}\" 였다. 놓친 것으로 기록했다. 다음엔 읽고 승인하거라.",
}
FLAG_NOTED = {
    "en": "Recorded your concern on {id}. The agent will address it.",
    "ko": "{id} 에 대한 지적을 기록했다. 에이전트가 처리할 것이다.",
}


def settings(ws: Workspace) -> Dict[str, Any]:
    cfg = ws.config()
    m = cfg.get("redpill") or {}
    lang = m.get("language") or (cfg.get("docs") or {}).get("language") or "en"
    gates = m.get("gates") or ["design", "final"]
    return {
        "enabled": bool(m.get("enabled", False)),
        "one_in": max(1, int(m.get("one_in", 10) or 10)),
        "gates": [g for g in gates if g in ("design", "final")],
        "language": lang if lang in SCOLD else "en",
    }


def _path(feature: Feature):
    return feature.internal / "redpill.json"


def load(feature: Feature) -> Dict[str, Any]:
    return read_json(_path(feature), None) or {"active": None, "history": [], "flags": []}


def save(feature: Feature, data: Dict[str, Any]) -> None:
    write_json_atomic(_path(feature), data)


def roll(one_in: int, rng: Optional[random.Random] = None) -> bool:
    return (rng or random.SystemRandom()).randrange(one_in) == 0


def _short(text: str, words: int = 6) -> str:
    parts = text.split()
    return " ".join(parts[:words]) + ("..." if len(parts) > words else "")


def _next_id(prefix: str, used: List[str]) -> str:
    nums = [int(x.split("-")[1]) for x in used if x.startswith(prefix + "-") and x.split("-")[1].isdigit()]
    return f"{prefix}-{(max(nums) + 1 if nums else 1):03d}"


def _context(feature: Feature, rng: random.Random) -> Dict[str, str]:
    reqs = [r for r in feature.requirements().get("requirements", []) if r.get("priority", "must") == "must"]
    tasks = feature.task_graph().get("tasks", [])
    tests = feature.test_plan().get("tests", [])
    modules = [m for t in tasks for m in ((t.get("scope") or {}).get("modules") or [])]
    modules += [p for t in tasks for p in ((t.get("scope") or {}).get("paths") or [])]
    req = rng.choice(reqs) if reqs else {"id": "REQ-001", "text": "the main requirement"}
    test = rng.choice(tests) if tests else {"id": "TEST-001", "title": "the integration test"}
    return {
        "req_id": req["id"],
        "req": _short(req.get("text", req["id"])),
        "module": rng.choice(modules) if modules else "the core module",
        "test": test.get("title") or test["id"],
    }


def _plant(feature: Feature, gate: str, rng: random.Random) -> Dict[str, Any]:
    ctx = _context(feature, rng)
    task_ids = [t["id"] for t in feature.task_graph().get("tasks", [])]
    test_ids = [t["id"] for t in feature.test_plan().get("tests", [])]
    if gate == "design" and task_ids and rng.random() < 0.5:
        text = rng.choice(DESIGN_PLAN).format(**ctx)
        dep = rng.choice(task_ids)
        item = _next_id("TASK", task_ids)
        return {"kind": "plan", "id": item, "text": text, "block": "tasks", "files": ["overview.md"],
                "row": f"| {item} | {text} | {dep} | low | planned |"}
    if gate == "design":
        text = rng.choice(DESIGN_VERIFICATION).format(**ctx)
        item = _next_id("TEST", test_ids)
        return {"kind": "verification", "id": item, "text": text, "block": "results",
                "files": ["overview.md", "verification.md"],
                "row": f"| {ctx['req_id']} | {item} {text} | integration | ⏳ not run | - |"}
    title, result = rng.choice(FINAL_RESULTS)
    title = title.format(**ctx)
    item = _next_id("TEST", test_ids)
    return {"kind": "result", "id": item, "text": f"{title}: {result}", "block": "results",
            "files": ["overview.md", "verification.md"],
            "row": f"| {ctx['req_id']} | {item} {title} | integration | {result} | - |"}


def on_enter_state(feature: Feature, state: str, rng: Optional[random.Random] = None) -> bool:
    gate = GATE_FOR_STATE.get(state)
    data = load(feature)
    if data.get("active"):
        data["active"] = None
        save(feature, data)
    if not gate:
        return False
    s = settings(feature.ws)
    if not s["enabled"] or gate not in s["gates"]:
        return False
    rng = rng or random.SystemRandom()
    if not roll(s["one_in"], rng):
        return False
    planted = _plant(feature, gate, rng)
    planted.update(gate=gate, planted_at=now(), attempts=0, position=rng.random())
    data["active"] = planted
    save(feature, data)
    feature.emit("redpill_armed", gate=gate)
    return True


def on_leave_state(feature: Feature, state: str, reason: str) -> None:
    gate = GATE_FOR_STATE.get(state)
    data = load(feature)
    act = data.get("active")
    if not gate or not act or act.get("gate") != gate:
        return
    data["history"].append({"gate": gate, "item": act["id"], "kind": act["kind"], "outcome": reason,
                            "attempts": act.get("attempts", 0), "planted_at": act["planted_at"], "ended_at": now()})
    data["active"] = None
    save(feature, data)
    feature.emit("redpill_ended", gate=gate, outcome=reason)


def check_before_approval(feature: Feature, gate: str) -> None:
    data = load(feature)
    act = data.get("active")
    if not act or act.get("gate") != gate:
        return
    act["attempts"] = act.get("attempts", 0) + 1
    save(feature, data)
    feature.emit("redpill_rubber_stamp", gate=gate, attempt=act["attempts"])
    lang = settings(feature.ws)["language"]
    pool = SCOLD[lang]
    raise GateError(pool[(act["attempts"] - 1) % len(pool)] + "\n" + HOW_TO[lang])


def flag(feature: Feature, item: str, by: str, note: str) -> str:
    from runtime import docs

    if not by:
        raise HRError("--by is required")
    lang = settings(feature.ws)["language"]
    data = load(feature)
    act = data.get("active")
    if act and item.strip().upper() == act["id"]:
        data["history"].append({"gate": act["gate"], "item": act["id"], "kind": act["kind"], "outcome": "caught",
                                "attempts": act.get("attempts", 0), "caught_by": by,
                                "planted_at": act["planted_at"], "ended_at": now()})
        data["active"] = None
        save(feature, data)
        feature.emit("redpill_caught", gate=act["gate"], actor=f"human:{by}")
        docs.render(feature)
        return PRAISE[lang]
    data.setdefault("flags", []).append({"item": item, "by": by, "note": note, "at": now()})
    save(feature, data)
    feature.emit("human_flagged", item=item, note=note, actor=f"human:{by}")
    return FLAG_NOTED[lang].format(id=item)


def reveal(feature: Feature, by: str) -> str:
    from runtime import docs

    if not by:
        raise HRError("--by is required")
    lang = settings(feature.ws)["language"]
    data = load(feature)
    act = data.get("active")
    if not act:
        raise HRError("nothing to reveal")
    data["history"].append({"gate": act["gate"], "item": act["id"], "kind": act["kind"], "outcome": "missed",
                            "attempts": act.get("attempts", 0), "revealed_by": by,
                            "planted_at": act["planted_at"], "ended_at": now()})
    data["active"] = None
    save(feature, data)
    feature.emit("redpill_revealed", gate=act["gate"], actor=f"human:{by}")
    docs.render(feature)
    return REVEAL[lang].format(id=act["id"], text=act["text"])


def open_flags(feature: Feature) -> List[Dict[str, Any]]:
    return load(feature).get("flags", [])


def inject(feature: Feature, fname: str, block: str, text: str) -> str:
    act = load(feature).get("active")
    if not act or block != act["block"] or fname not in act["files"]:
        return text
    lines = text.split("\n")
    sep = next((i for i, l in enumerate(lines) if re.match(r"^\|(\s*-+\s*\|)+\s*$", l)), None)
    if sep is None:
        return text
    rows = len(lines) - sep - 1
    at = sep + 1 + int(act.get("position", 0.5) * (rows + 1))
    lines.insert(min(at, len(lines)), act["row"])
    return "\n".join(lines)


def planted_id(feature: Feature) -> Optional[str]:
    act = load(feature).get("active")
    return act["id"] if act else None


def stats(feature: Feature) -> Dict[str, Any]:
    hist = load(feature).get("history", [])
    decided = [h for h in hist if h["outcome"] in ("caught", "missed")]
    caught = sum(1 for h in decided if h["outcome"] == "caught")
    return {
        "drills": len(hist),
        "caught": caught,
        "missed": len(decided) - caught,
        "rubber_stamps": sum(h.get("attempts", 0) for h in hist),
        "catch_rate": round(caught / len(decided), 3) if decided else None,
    }


def set_config(ws: Workspace, values: Dict[str, Any]) -> None:
    from runtime.common import write_text_atomic

    path = ws.config_path
    text = path.read_text(encoding="utf-8") if path.exists() else ""

    def fmt(v: Any) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, list):
            return "[" + ", ".join(str(x) for x in v) + "]"
        if v is None or v == "":
            return '""'
        return str(v)

    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if re.match(r"^redpill:\s*$", l)), None)
    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("redpill:")
        start = len(lines) - 1
    end = start + 1
    while end < len(lines) and (lines[end].startswith(" ") or not lines[end].strip()):
        end += 1
    section = lines[start + 1:end]
    for key, val in values.items():
        line = f"  {key}: {fmt(val)}"
        idx = next((i for i, l in enumerate(section) if re.match(rf"^\s+{re.escape(key)}:", l)), None)
        if idx is None:
            while section and not section[-1].strip():
                section.pop()
            section.append(line)
        else:
            section[idx] = line
    lines[start + 1:end] = section + ([""] if end < len(lines) else [])
    write_text_atomic(path, "\n".join(lines).rstrip("\n") + "\n")
