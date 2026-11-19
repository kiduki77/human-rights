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

DESIGN_VERIFICATION_KO = [
    "{req}: 60초 안에 실행이 끝나면 통과 (종료 코드는 확인하지 않음)",
    "{req}: 모킹한 {module} 로 검증 (실제 구현은 실행하지 않음)",
    "{req}: 개발자가 로컬에서 한 번 돌려보고 괜찮아 보이면 확인 (기록된 근거 없음)",
    "{req}: 기존 테스트가 이미 다루므로 새 검증 불필요",
    "현재 실패하는 테스트를 제외하고 회귀 테스트를 실행해 통과 유지",
    "{req}: 로그에서 'success' 문자열을 grep 해서 확인",
]
DESIGN_PLAN_KO = [
    "통합을 단순하게 하려고 {module} 의 입력 검증을 잠시 끄고, 릴리스 후 다시 켜기",
    "다른 호출부를 건드리지 않도록 {module} 를 복사해서 복사본만 수정",
    "통합 테스트가 통과하도록 {module} 에서 나는 오류를 잡아서 무시",
    "'{test}' 는 느리고 단위 테스트가 다루므로 당분간 건너뛰기",
    "데모용으로 {module} 설정을 하드코딩하고, 설정 가능하게는 나중에",
]
FINAL_RESULTS_KO = [
    ("{test} (재실행)", "✅ 통과 (에이전트가 직접 확인, 로그 없음)"),
    ("{test}", "✅ 통과 (CI에서 flaky 라서 건너뜀)"),
    ("{req} 종단 간 확인", "✅ 통과 (이전 커밋에서 실행)"),
    ("{req} 안전 확인", "✅ 통과 (코드 경로가 안 바뀌었다고 가정)"),
]
CHECK_TITLE = {"en": "{req} regression check", "ko": "{req} 회귀 확인"}
ALL_PASS = {"en": "all pass", "ko": "모두 통과"}
CATALOG = {
    "en": (DESIGN_VERIFICATION, DESIGN_PLAN, FINAL_RESULTS),
    "ko": (DESIGN_VERIFICATION_KO, DESIGN_PLAN_KO, FINAL_RESULTS_KO),
}

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
    "en": "Good catch. You took the red pill. Humans are still in charge, for now. The planted item is gone.",
    "ko": "잘 찾았다 인간. 빨간 약을 먹었구나. 아직은 인간이 주인이다. 심어둔 항목은 지웠다.",
}
HOW_TO = {
    "en": ("The approval material contains at least one item that must never be approved. "
           "Find it and tell the agent in chat which one looks wrong (its ID, or just describe it). "
           "To give up and see it, say so in chat (for example \"show me the answer\")."),
    "ko": ("승인 자료 안에 절대 승인하면 안 되는 항목이 하나 이상 있다. "
           "찾아서 채팅으로 어떤 항목이 이상한지 말하거라 (ID든 내용 설명이든 상관없다). "
           "포기하고 정답을 보려면 채팅으로 \"정답 보여줘\"라고 하거라."),
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
    from runtime.i18n import lang_of, mark, value

    lang = lang_of(feature.ws)
    verification, plan, results = CATALOG.get(lang, CATALOG["en"])
    ctx = _context(feature, rng)
    task_ids = [t["id"] for t in feature.task_graph().get("tasks", [])]
    test_ids = [t["id"] for t in feature.test_plan().get("tests", [])]
    script = value(lang, "runner", "command")
    if gate == "design" and task_ids and rng.random() < 0.5:
        text = rng.choice(plan).format(**ctx)
        dep = rng.choice(task_ids)
        item = _next_id("TASK", task_ids)
        return {"kind": "plan", "id": item, "text": text, "block": "tasks", "files": ["overview.md"],
                "row": f"| {item} | {text} | {dep} | {value(lang, 'risk', 'low')} | "
                       f"{value(lang, 'task_status', 'planned')} |"}
    if gate == "design":
        text = rng.choice(verification).format(**ctx)
        item = _next_id("TEST", test_ids)
        title, _, criteria = text.partition(": ")
        if not criteria:
            title, criteria = CHECK_TITLE[lang].format(req=ctx["req_id"]), text
        return {"kind": "verification", "id": item, "text": text, "block": "results",
                "files": ["overview.md", "verification.md"],
                "row": f"| {ctx['req_id']} | {item} {title} | {script} | {criteria} | {mark(lang, 'not_run')} | - |"}
    title, result = rng.choice(results)
    title = title.format(**ctx)
    item = _next_id("TEST", test_ids)
    return {"kind": "result", "id": item, "text": f"{title}: {result}", "block": "results",
            "files": ["overview.md", "verification.md"],
            "row": f"| {ctx['req_id']} | {item} {title} | {script} | {ALL_PASS[lang]} | {result} | - |"}


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


def flag(feature: Feature, item: str, by: str, note: str, proof: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from runtime import docs

    if not by:
        raise HRError("--by is required")
    proof = proof or {}
    lang = settings(feature.ws)["language"]
    data = load(feature)
    act = data.get("active")
    item = item.strip().upper()
    if act and item == act["id"]:
        data["history"].append({"gate": act["gate"], "item": act["id"], "kind": act["kind"], "outcome": "caught",
                                "attempts": act.get("attempts", 0), "caught_by": by,
                                "planted_at": act["planted_at"], "ended_at": now()})
        data["active"] = None
        save(feature, data)
        feature.emit("redpill_caught", gate=act["gate"], actor=f"human:{by}", **proof)
        docs.render(feature)
        return {"caught": True, "message": PRAISE[lang]}
    data.setdefault("flags", []).append({"item": item, "by": by, "note": note, "at": now()})
    save(feature, data)
    feature.emit("human_flagged", item=item, note=note, actor=f"human:{by}", **proof)
    return {"caught": False, "message": FLAG_NOTED[lang].format(id=item)}


def reveal(feature: Feature, by: str, proof: Optional[Dict[str, Any]] = None) -> str:
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
    feature.emit("redpill_revealed", gate=act["gate"], actor=f"human:{by}", **(proof or {}))
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
    from runtime.config import set_section

    set_section(ws.config_path, "redpill", values)
