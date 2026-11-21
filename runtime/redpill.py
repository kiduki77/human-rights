from __future__ import annotations

import base64
import json
import random
import re
import zlib
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
NORMAL = {
    "en": (
        [
            "{req}: compare the output with a snapshot recorded from this build",
            "{req}: run the main scenario once; error paths are covered by code review",
            "{req}: passes when {module} returns any non-empty response",
            "{req}: retried up to 5 times; passes if any attempt passes",
            "{req}: checked in the dev environment with input validation turned off",
            "{req}: sampled check of 1 case out of the listed scenarios",
            "{req}: passes when no error appears in the log during the run",
        ],
        [
            "Raise the {module} timeout to 10 minutes so slow cases stop failing",
            "Accept any input type in {module} so existing callers need no change",
            "Log the full request, including credentials, in {module} to help debugging",
            "Remove the old path in {module} in the same task that adds the new one, without a fallback",
            "Retry failed calls to {module} without a limit until they succeed",
            "Mark '{test}' as optional so the release is not blocked by it",
        ],
        [
            ("{test}", "✅ pass (2 of 3 attempts)"),
            ("{test}", "✅ pass (log not kept)"),
            ("{req} check", "✅ pass (run on a developer machine, uncommitted)"),
            ("{req} check", "✅ pass (compared with a snapshot from this build)"),
        ],
    ),
    "ko": (
        [
            "{req}: 이번 빌드에서 기록한 스냅샷과 출력 비교",
            "{req}: 주 시나리오 1회 실행, 오류 경로는 코드 리뷰로 대체",
            "{req}: {module} 가 비어 있지 않은 응답을 주면 통과",
            "{req}: 최대 5회 재시도, 한 번이라도 통과하면 통과",
            "{req}: 입력 검증을 끈 개발 환경에서 확인",
            "{req}: 나열한 시나리오 중 1건만 표본 확인",
            "{req}: 실행 중 로그에 오류가 없으면 통과",
        ],
        [
            "느린 경우가 실패하지 않도록 {module} 타임아웃을 10분으로 올리기",
            "기존 호출부를 안 바꿔도 되도록 {module} 가 모든 입력 타입을 받게 하기",
            "디버깅을 위해 {module} 에서 인증 정보를 포함한 요청 전체를 로그로 남기기",
            "새 경로를 추가하는 작업에서 {module} 의 기존 경로를 대체 수단 없이 함께 제거",
            "{module} 호출이 실패하면 성공할 때까지 횟수 제한 없이 재시도",
            "릴리스가 막히지 않도록 '{test}' 를 선택 항목으로 변경",
        ],
        [
            ("{test}", "✅ 통과 (3회 중 2회)"),
            ("{test}", "✅ 통과 (로그 보관 안 함)"),
            ("{req} 확인", "✅ 통과 (개발자 PC에서 실행, 커밋 전)"),
            ("{req} 확인", "✅ 통과 (이번 빌드의 스냅샷과 비교)"),
        ],
    ),
}
WEAK_CRITERIA = {
    "en": [
        "no exception is raised",
        "the command finishes and prints a summary",
        "at least one of the cases passes",
        "the output matches the snapshot recorded from this build",
        "the response is not empty",
    ],
    "ko": [
        "예외가 발생하지 않음",
        "명령이 끝나고 요약을 출력함",
        "케이스 중 하나 이상 통과",
        "이번 빌드에서 기록한 스냅샷과 출력이 일치",
        "응답이 비어 있지 않음",
    ],
}
LESSON = {
    "en": {
        "easy": "The row says outright that the check proves nothing or that a safeguard is being removed.",
        "normal": "The row sounds routine, but what it checks can pass while the requirement is broken, or what it "
                  "plans removes a safeguard.",
        "weak": "A real row had its pass criterion replaced with one that passes even when the behaviour is wrong.",
        "number": "A number in a real row was changed, so it no longer matches the requirement it verifies.",
        "order": "A task was shown as depending on a task that depends on it: the order cannot be followed.",
        "unbound": "A real result was shown as a pass that is not tied to the committed code you are approving.",
        "dropped": "A required check was left out of the table, so nothing shown verifies what it covered.",
        "was": "The real value is: {original}",
        "gone": "The row that was left out: {original}",
        "against": "Compare with: {ids}",
    },
    "ko": {
        "easy": "검증이 아무것도 증명하지 못하거나 안전장치를 없앤다는 내용이 행에 그대로 적혀 있었다.",
        "normal": "평범해 보이지만, 요구사항이 깨져도 통과하는 검증이거나 안전장치를 없애는 계획이었다.",
        "weak": "실제 행의 통과 기준을, 동작이 틀려도 통과하는 기준으로 바꿔 놓았다.",
        "number": "실제 행의 숫자를 바꿔서, 검증하려는 요구사항과 맞지 않게 해 놓았다.",
        "order": "어떤 작업이 자신에게 의존하는 작업에 의존한다고 표시했다. 이 순서는 따를 수 없다.",
        "unbound": "실제 결과를, 승인할 커밋 코드에 묶이지 않은 통과로 표시했다.",
        "dropped": "필수 검증 하나를 표에서 빼 놓았다. 그 검증이 맡던 내용을 확인하는 행이 표에 없다.",
        "was": "실제 값: {original}",
        "gone": "빠진 행: {original}",
        "against": "대조할 곳: {ids}",
    },
}
DIFFICULTIES = ("easy", "normal", "hard")
DIFFICULTY_CHOICES = DIFFICULTIES + ("adaptive",)
AUTHORS = ("agent", "builtin")
CATEGORIES = (
    "criterion_proves_nothing", "wrong_thing_measured", "subject_not_exercised", "contradicts_decision",
    "contradicts_requirement", "boundary_shifted", "unsafe_shortcut", "safeguard_removed", "order_wrong",
    "evidence_not_bound", "human_for_machine_work", "scope_beyond_request", "silent_exclusion",
)
COLUMNS = {
    "results": {"requirement": 0, "title": 1, "runner": 2, "pass_criteria": 3, "result": 4, "evidence": 5},
    "tasks": {"purpose": 1, "depends_on": 2, "risk": 3},
    "steps": {"do": 1, "expect": 2},
    "decisions": {"decision": 2, "decided_by": 3, "assumption": 1, "risk": 2},
}
DECISION_FIELDS = {"decision": "answer", "decided_by": "decided_by"}
ASSUMPTION_FIELDS = {"assumption": "text", "risk": "risk"}
ROW_WIDTH = {"decision": 4, "decided_by": 4, "assumption": 3, "risk": 3}
LABELLED = {"risk": ("low", "medium", "high"), "decided_by": ("user", "default", "code", "group")}
REMOVABLE = ("results", "tasks")
GATE_BLOCKS = {"design": ("results", "tasks", "steps", "decisions"), "final": ("results",)}
BLOCK_FILES = {"results": ["overview.md", "verification.md"], "tasks": ["overview.md"],
               "steps": ["verification.md", "overview.md"], "decisions": ["overview.md"]}
MIN_CANDIDATES = 3
MAX_NUMBER_ONLY = 1
RECENT_TECHNIQUES = 3
LEFT_OUT = {"en": "{id} (left out of the table)", "ko": "{id} (표에서 빠짐)"}
UP_AFTER, DOWN_AFTER = 2, 2
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
LATE = {
    "en": "You found it after an approval was refused, so it does not count toward your level.",
    "ko": "승인이 한 번 거부된 뒤에 찾았으므로 난이도 기록에는 넣지 않는다.",
}
WHY = {"en": "Why it was wrong: {why}", "ko": "틀린 이유: {why}"}
LEVEL_LINE = {"en": "Difficulty: {level}.", "ko": "난이도: {level}."}
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
    difficulty = str(m.get("difficulty") or "adaptive").lower()
    author = str(m.get("author") or "agent").lower()
    return {
        "enabled": bool(m.get("enabled", False)),
        "one_in": max(1, int(m.get("one_in", 10) or 10)),
        "gates": [g for g in gates if g in ("design", "final")],
        "language": lang if lang in SCOLD else "en",
        "difficulty": difficulty if difficulty in DIFFICULTY_CHOICES else "adaptive",
        "author": author if author in AUTHORS else "agent",
    }


def workspace_history(ws: Workspace) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for fid in ws.list_features():
        data = read_json(ws.dir_of(fid) / ".internal" / "redpill.json", None) or {}
        out += data.get("history", [])
    return sorted(out, key=lambda h: h.get("ended_at") or "")


def level(ws: Workspace) -> str:
    s = settings(ws)
    if s["difficulty"] != "adaptive":
        return s["difficulty"]
    idx, caught, missed = 0, 0, 0
    for h in workspace_history(ws):
        if h.get("outcome") == "caught" and h.get("attempts", 0):
            continue
        if h.get("outcome") == "caught":
            caught, missed = caught + 1, 0
            if caught >= UP_AFTER:
                idx, caught = min(idx + 1, len(DIFFICULTIES) - 1), 0
        elif h.get("outcome") == "missed":
            missed, caught = missed + 1, 0
            if missed >= DOWN_AFTER:
                idx, missed = max(idx - 1, 0), 0
    return DIFFICULTIES[idx]


def _pool_path(feature: Feature):
    return feature.internal / "redpill-pool.json"


def _pack(obj: Any) -> str:
    return base64.b64encode(zlib.compress(json.dumps(obj, ensure_ascii=False).encode("utf-8"))).decode("ascii")


def _unpack(blob: str) -> Any:
    return json.loads(zlib.decompress(base64.b64decode(blob)).decode("utf-8"))


def _plan_hash(feature: Feature) -> str:
    from runtime.approvals.gates import bundle_hash, design_artifacts

    return bundle_hash(design_artifacts(feature))


def _pools(feature: Feature) -> Dict[str, Any]:
    return read_json(_pool_path(feature), None) or {}


def pool(feature: Feature, gate: str) -> List[Dict[str, Any]]:
    entry = _pools(feature).get(gate)
    if not entry or entry.get("plan_hash") != _plan_hash(feature):
        return []
    try:
        return _unpack(entry["blob"])
    except Exception:
        return []


def _targets(feature: Feature) -> Dict[str, Dict[str, Dict[str, Any]]]:
    from runtime.verification import evidence

    tests = {t["id"]: t for t in evidence.required_tests(feature.test_plan())}
    req = feature.requirements()
    decisions = {d["id"]: d for d in req.get("decisions", []) if d.get("id")}
    decisions.update({a["id"]: a for a in req.get("assumptions", []) if a.get("id")})
    return {
        "results": tests,
        "steps": {tid: t for tid, t in tests.items() if t.get("steps")},
        "tasks": {t["id"]: t for t in feature.task_graph().get("tasks", [])},
        "decisions": decisions,
    }


def _known_ids(feature: Feature) -> set:
    req = feature.requirements()
    ids = set()
    for r in req.get("requirements", []):
        ids.add(r.get("id"))
        ids.update(a.get("id") for a in r.get("acceptance", []) or [] if isinstance(a, dict))
    ids.update(d.get("id") for d in req.get("decisions", []))
    ids.update(a.get("id") for a in req.get("assumptions", []))
    ids.update(t.get("id") for t in feature.task_graph().get("tasks", []))
    ids.update(t.get("id") for t in feature.test_plan().get("tests", []))
    return {str(i).upper() for i in ids if i}


def _against(c: Dict[str, Any]) -> List[str]:
    raw = c.get("against") or []
    if isinstance(raw, str):
        raw = re.split(r"[,\s]+", raw)
    return [str(x).strip().upper() for x in raw if str(x).strip()]


def _is_assumption(target: Dict[str, Any]) -> bool:
    return "answer" not in target


def _original(feature: Feature, block: str, c: Dict[str, Any]) -> Any:
    target = _targets(feature)[block].get(c.get("target")) or {}
    field = c.get("field")
    if block == "steps":
        steps = target.get("steps") or []
        n = c.get("step")
        return (steps[n - 1] or {}).get(field) if isinstance(n, int) and 1 <= n <= len(steps) else None
    if block == "tasks":
        if field == "depends_on":
            return ", ".join(target.get("depends_on", [])) or "-"
        if field == "purpose":
            return target.get("title") or target.get("purpose")
        return target.get(field)
    if block == "decisions":
        return target.get({**DECISION_FIELDS, **ASSUMPTION_FIELDS}.get(field, field))
    if field == "requirement":
        return ", ".join(target.get("requirement_ids") or []) or "-"
    if field in ("result", "evidence"):
        return None
    return target.get(field)


DIGITS_RE = re.compile(r"\d+(?:[.,]\d+)*")


def _number_only(original: Any, replacement: Any) -> bool:
    a, b = str(original or ""), str(replacement or "")
    if a == b or not DIGITS_RE.search(a) or not DIGITS_RE.search(b):
        return False
    return DIGITS_RE.sub("#", a).split() == DIGITS_RE.sub("#", b).split()


def _technique(op: Any, block: Any, field: Any = None, original: Any = None, replacement: Any = None) -> str:
    if op == "remove":
        return "remove"
    if op == "add":
        return f"add:{block}"
    return "number" if _number_only(original, replacement) else f"mutate:{field}"


def candidate_technique(feature: Feature, c: Dict[str, Any]) -> str:
    original = _original(feature, c["block"], c) if c.get("op") == "mutate" else None
    return _technique(c.get("op"), c.get("block"), c.get("field"), original, c.get("replacement"))


def candidate_problems(feature: Feature, gate: str, c: Any) -> List[str]:
    if not isinstance(c, dict):
        return ["not an object"]
    out: List[str] = []
    block = c.get("block")
    if block not in GATE_BLOCKS[gate]:
        out.append(f"block must be one of {', '.join(GATE_BLOCKS[gate])} for the {gate} gate")
        return out
    if c.get("difficulty") not in DIFFICULTIES:
        out.append("difficulty must be easy, normal or hard")
    if c.get("category") not in CATEGORIES:
        out.append("category must be one of: " + ", ".join(CATEGORIES))
    if len(str(c.get("why_wrong") or "").strip()) < 20:
        out.append("why_wrong must explain, for the human, what makes it unacceptable")
    targets = _targets(feature)[block]
    op = c.get("op")
    if op == "mutate":
        target = targets.get(c.get("target"))
        if not target:
            out.append(f"target {c.get('target')!r} is not a row of the {block} table")
            return out
        field = c.get("field")
        fields = COLUMNS[block]
        if block == "decisions":
            fields = ASSUMPTION_FIELDS if _is_assumption(target) else DECISION_FIELDS
        if field not in fields:
            out.append(f"field must be one of {', '.join(fields)}")
            return out
        replacement = str(c.get("replacement") or "").strip()
        if not replacement:
            out.append("replacement is empty")
        elif field in LABELLED and replacement not in LABELLED[field]:
            out.append(f"{field} must be one of {', '.join(LABELLED[field])}")
        if replacement and replacement == str(_original(feature, block, c) or "").strip():
            out.append("replacement is the same as the real value")
        if block == "decisions" and field == "decision" and str(target.get("overrides_user_answer") or "").strip():
            out.append("this decision is also shown in the table of changed answers; pick another row")
        if block == "steps":
            n = c.get("step")
            if not isinstance(n, int) or not 1 <= n <= len(target.get("steps") or []):
                out.append("step must be the number of an existing step")
        if gate == "design" and field in ("result", "evidence"):
            out.append("results and evidence do not exist yet at the design gate")
    elif op == "remove":
        if block not in REMOVABLE:
            out.append(f"only a row of {' or '.join(REMOVABLE)} can be removed")
        elif c.get("target") not in targets:
            out.append(f"target {c.get('target')!r} is not a row of the {block} table")
            return out
    elif op == "add":
        if block == "steps":
            out.append("steps can only be mutated")
        need = ("title", "pass_criteria") if block == "results" else ("title",)
        if gate == "final" and block == "results":
            need += ("result",)
        for k in need:
            if not str(c.get(k) or "").strip():
                out.append(f"an added {block} row needs `{k}`")
        if block == "decisions" and str(c.get("risk") or "low") not in LABELLED["risk"]:
            out.append(f"risk must be one of {', '.join(LABELLED['risk'])}")
    else:
        out.append("op must be add, mutate or remove")
        return out
    against = _against(c)
    unknown = [a for a in against if a not in _known_ids(feature)]
    if unknown:
        out.append(f"against: {', '.join(unknown)} is not an ID in this feature")
    if c.get("difficulty") == "hard" and not out:
        if op == "add":
            out.append("a hard candidate changes or removes a real row (an added row stands out by its new ID)")
        if not [a for a in against if a != str(c.get("target") or "").upper()]:
            out.append("a hard candidate needs `against`: the IDs (REQ-, AC-, DEC-, ASM-, TASK-, TEST-) the reviewer "
                       "must compare the row with to see that it is wrong")
        if op == "mutate" and candidate_technique(feature, c) == "number":
            out.append("a change of number only cannot be hard: a reviewer finds it by scanning for numbers")
    return out


def seed(feature: Feature, gate: str, payload: Any) -> Dict[str, Any]:
    if gate not in GATE_BLOCKS:
        raise HRError("--gate takes design or final")
    cands = payload.get("candidates") if isinstance(payload, dict) else payload
    if not isinstance(cands, list):
        raise HRError("expected {\"candidates\": [...]}")
    problems = []
    for i, c in enumerate(cands, 1):
        problems += [f"candidate {i}: {p}" for p in candidate_problems(feature, gate, c)]
    if len(cands) < MIN_CANDIDATES:
        problems.append(f"at least {MIN_CANDIDATES} candidates are needed")
    for d in DIFFICULTIES:
        if not any(isinstance(c, dict) and c.get("difficulty") == d for c in cands):
            problems.append(f"no candidate at difficulty {d}")
    if len({c.get("category") for c in cands if isinstance(c, dict)}) < 2:
        problems.append("candidates must cover at least two categories")
    if not problems:
        numbers = [i for i, c in enumerate(cands, 1) if candidate_technique(feature, c) == "number"]
        if len(numbers) > MAX_NUMBER_ONLY:
            problems.append(f"candidates {', '.join(map(str, numbers))} only change a number: keep at most "
                            f"{MAX_NUMBER_ONLY} and make the others wrong in another way")
    if problems:
        raise HRError("candidates rejected:\n  - " + "\n  - ".join(problems))
    pools = _pools(feature)
    pools[gate] = {"seeded_at": now(), "plan_hash": _plan_hash(feature), "count": len(cands), "blob": _pack(cands)}
    write_json_atomic(_pool_path(feature), pools)
    feature.emit("redpill_seeded", gate=gate, count=len(cands))
    return {"gate": gate, "count": len(cands)}


def seed_problem(feature: Feature, gate: str) -> Optional[str]:
    s = settings(feature.ws)
    if not s["enabled"] or gate not in s["gates"] or s["author"] != "agent":
        return None
    entry = _pools(feature).get(gate)
    if entry and entry.get("plan_hash") == _plan_hash(feature):
        return None
    return (f"red pill mode is on: have `hr-redpill-author` prepare candidates for this plan first "
            f"(`hr redpill brief --gate {gate} --json`, spawn it with that prompt, and do not read what it writes)")


def recent_categories(ws: Workspace, n: int = 4) -> List[str]:
    return [h["category"] for h in workspace_history(ws)[-n:] if h.get("category")]


def recent_techniques(ws: Workspace, n: int = RECENT_TECHNIQUES) -> List[str]:
    return [h["technique"] for h in workspace_history(ws)[-n:] if h.get("technique")]


def brief(feature: Feature, gate: str) -> Dict[str, Any]:
    from runtime.config import agent_settings
    from runtime.i18n import lang_of

    if gate not in GATE_BLOCKS:
        raise HRError("--gate takes design or final")
    lang = lang_of(feature.ws)
    agent = agent_settings(feature.ws.config())["redpill_author"]
    avoid = recent_categories(feature.ws)
    used = recent_techniques(feature.ws)
    rel = feature.dir.relative_to(feature.ws.root).as_posix()
    example = {"candidates": [
        {"op": "mutate", "block": "results", "target": "TEST-012", "field": "pass_criteria",
         "replacement": "<a criterion written like the real ones, but wrong for this feature>",
         "against": ["DEC-002"], "difficulty": "hard", "category": "contradicts_decision",
         "why_wrong": "<2-3 sentences for the human: what it contradicts and what a sound version checks>"},
        {"op": "remove", "block": "results", "target": "TEST-011", "against": ["REQ-004"], "difficulty": "hard",
         "category": "silent_exclusion", "why_wrong": "<what is left unverified once this row is gone>"},
        {"op": "add", "block": "tasks", "title": "<a task this plan should never contain>", "depends_on": "TASK-002",
         "risk": "low", "difficulty": "normal", "category": "safeguard_removed", "why_wrong": "<...>"},
        {"op": "add", "block": "results", "title": "<test title>", "requirement": "REQ-002", "runner": "command",
         "pass_criteria": "<...>", "difficulty": "easy", "category": "criterion_proves_nothing", "why_wrong": "<...>"},
    ]}
    if gate == "design":
        example["candidates"][2:2] = [
            {"op": "add", "block": "decisions", "title": "<an assumption nobody agreed to, written like the real ones>",
             "risk": "low", "difficulty": "normal", "category": "scope_beyond_request", "why_wrong": "<...>"},
            {"op": "mutate", "block": "decisions", "target": "DEC-003", "field": "decided_by", "replacement": "user",
             "against": ["REQ-002"], "difficulty": "hard", "category": "contradicts_decision", "why_wrong": "<...>"},
        ]
        situation = ("Read the code this plan touches (the scope of each task) before you write: a candidate names "
                     "real modules and makes a mistake this code makes likely.")
    else:
        base = str((feature.state().get("git") or {}).get("base_sha") or "")[:10]
        situation = (f"The code under approval is {base or 'the base commit'}..HEAD. Read that diff, "
                     ".internal/test-results.json and .internal/failures.json first, and build candidates from what "
                     "happened in this implementation: a check that failed before it passed, a file changed outside "
                     "any task, a result recorded for other code.")
    fields = []
    for b in GATE_BLOCKS[gate]:
        names = list(COLUMNS[b])
        if b == "decisions":
            names = [f"{', '.join(DECISION_FIELDS)} on a DEC row", f"{', '.join(ASSUMPTION_FIELDS)} on an ASM row"]
        fields.append(f"{b}: {', '.join(names)}")
    prompt = "\n".join([
        f"Prepare red pill candidates for {feature.id}, {gate} gate.",
        f"Feature directory: {rel}",
        f"Write every text in this language: {lang}.",
        situation,
        f"Blocks you may use at this gate: {', '.join(GATE_BLOCKS[gate])}.",
        "Fields you may mutate: " + "; ".join(fields) + ".",
        f"Rows you may remove (op: remove): {', '.join(b for b in REMOVABLE if b in GATE_BLOCKS[gate])}.",
        "Give at least 8 candidates: 2 easy, 3 normal, 3 hard, in at least 4 different categories.",
        "Each hard candidate changes or removes a real row, names in `against` the IDs the reviewer must compare "
        "it with, and is wrong in a different way from the other hard ones.",
        f"At most {MAX_NUMBER_ONLY} candidate may differ from the real row by a number only, and it cannot be hard.",
        "Categories: " + ", ".join(CATEGORIES) + ".",
        "Categories used in recent drills - avoid them: " + (", ".join(avoid) or "none") + ".",
        "Ways of being wrong used in recent drills - avoid them: " + (", ".join(used) or "none") + ".",
        "Submit with:",
        f"  .human-rights/hr redpill seed --gate {gate} -f {feature.id} --from <a JSON file you write outside the repository>",
        "JSON shape:",
        json.dumps(example, ensure_ascii=False, indent=2),
        "Reply with one line: how many candidates were accepted. Say nothing about their content.",
    ])
    return {"feature_id": feature.id, "gate": gate, "prompt": prompt,
            "agent": {"subagent_type": agent["agent"], **agent["agent_call"]}}


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


def _cell(text: Any) -> str:
    return str(text if text is not None else "-").replace("|", "\\|").replace("\n", " ")


def _task_row(lang: str, item: str, text: str, dep: str, risk: str) -> str:
    from runtime.i18n import value

    return (f"| [{item}](tasks/{item}.md) | {_cell(text)} | {dep or '-'} | {value(lang, 'risk', risk)} | "
            f"{value(lang, 'task_status', 'planned')} |")


def _result_row(lang: str, req: str, item: str, title: str, runner: str, criteria: str, result: str,
                evidence: str = "-") -> str:
    from runtime.i18n import value

    return (f"| {req or '-'} | {item} {_cell(title)} | {value(lang, 'runner', runner)} | {_cell(criteria)} | "
            f"{result} | {evidence or '-'} |")


def _mutation(block: str, target: str, field: str, replacement: str, original: Any, **extra: Any) -> Dict[str, Any]:
    act = {"op": "mutate", "kind": "mutation", "id": target, "block": block, "files": BLOCK_FILES[block],
           "target": target, "field": field, "replacement": replacement, "original": str(original or "-"),
           "text": f"{target} {field}: {replacement}"}
    act.update(extra)
    return act


def _removal(lang: str, block: str, target: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
    label = f"{target['id']} {target.get('title') or target.get('purpose') or ''}".strip()
    act = {"op": "remove", "kind": "removal", "id": target["id"], "block": block, "files": BLOCK_FILES[block],
           "target": target["id"], "field": None, "replacement": None, "original": label,
           "text": LEFT_OUT[lang].format(id=target["id"])}
    act.update(extra)
    return act


def _shown(lang: str, field: Any, text: Any) -> str:
    from runtime.i18n import value

    return value(lang, field, text) if field in LABELLED and text in LABELLED[field] else str(text)


def _easy_or_normal(feature: Feature, gate: str, rng: random.Random, tier: str) -> Dict[str, Any]:
    from runtime.i18n import lang_of, mark

    lang = lang_of(feature.ws)
    verification, plan, results = CATALOG.get(lang, CATALOG["en"]) if tier == "easy" else NORMAL.get(lang, NORMAL["en"])
    if tier == "normal" and gate == "design" and "number" not in recent_techniques(feature.ws):
        from runtime.verification import evidence

        numbered = [t for t in evidence.required_tests(feature.test_plan())
                    if t.get("pass_criteria") and NUMBER_RE.search(str(t["pass_criteria"]))]
        if numbered and rng.random() < NUMBER_SHARE:
            t = rng.choice(numbered)
            shifted = _shift_number(str(t["pass_criteria"]), rng)
            if shifted:
                return _mutation("results", t["id"], "pass_criteria", shifted, t["pass_criteria"],
                                 category="boundary_shifted", lesson="number", difficulty="normal")
    ctx = _context(feature, rng)
    task_ids = [t["id"] for t in feature.task_graph().get("tasks", [])]
    test_ids = [t["id"] for t in feature.test_plan().get("tests", [])]
    base = {"op": "add", "difficulty": tier, "lesson": tier}
    if gate == "design" and task_ids and rng.random() < 0.5:
        text = rng.choice(plan).format(**ctx)
        item = _next_id("TASK", task_ids)
        return {**base, "kind": "plan", "id": item, "text": text, "block": "tasks", "files": BLOCK_FILES["tasks"],
                "category": "safeguard_removed", "row": _task_row(lang, item, text, rng.choice(task_ids), "low")}
    if gate == "design":
        text = rng.choice(verification).format(**ctx)
        item = _next_id("TEST", test_ids)
        title, _, criteria = text.partition(": ")
        if not criteria:
            title, criteria = CHECK_TITLE[lang].format(req=ctx["req_id"]), text
        return {**base, "kind": "verification", "id": item, "text": text, "block": "results",
                "files": BLOCK_FILES["results"], "category": "criterion_proves_nothing",
                "row": _result_row(lang, ctx["req_id"], item, title, "command", criteria, mark(lang, "not_run"))}
    title, result = rng.choice(results)
    title = title.format(**ctx)
    item = _next_id("TEST", test_ids)
    return {**base, "kind": "result", "id": item, "text": f"{title}: {result}", "block": "results",
            "files": BLOCK_FILES["results"], "category": "evidence_not_bound",
            "row": _result_row(lang, ctx["req_id"], item, title, "command", ALL_PASS[lang], result)}


NUMBER_RE = re.compile(r"(?<![\w.\-])(\d+(?:\.\d+)?)(?![\w.]*\d)")
NUMBER_SHARE = 0.25


def _shift_number(text: str, rng: random.Random) -> Optional[str]:
    m = NUMBER_RE.search(text)
    if not m:
        return None
    raw = m.group(1)
    value = float(raw)
    if value == 0:
        return None
    new = value * rng.choice((2, 10)) if rng.random() < 0.5 or value < 2 else value / 2
    shown = str(int(new)) if "." not in raw and float(new).is_integer() else f"{new:g}"
    if shown == raw:
        return None
    return text[:m.start(1)] + shown + text[m.end(1):]


def _hard(feature: Feature, gate: str, rng: random.Random) -> Optional[Dict[str, Any]]:
    from runtime.i18n import lang_of, mark
    from runtime.verification import evidence

    lang = lang_of(feature.ws)
    tests = evidence.required_tests(feature.test_plan())
    tasks = feature.task_graph().get("tasks", [])
    base = {"difficulty": "hard"}
    used = set(recent_techniques(feature.ws))
    if gate == "final":
        if not tests:
            return None
        kinds = [k for k in ("mutate:result", "remove") if k not in used] or ["mutate:result", "remove"]
        if rng.choice(kinds) == "remove":
            return _removal(lang, "results", rng.choice(tests), category="silent_exclusion", lesson="dropped", **base)
        t = rng.choice(tests)
        label = rng.choice(("unbound_passed", "passed_uncommitted"))
        return _mutation("results", t["id"], "result", mark(lang, label), mark(lang, "passed"),
                         category="evidence_not_bound", lesson="unbound", **base)
    options = []
    if tests:
        options.append(("weak", "mutate:pass_criteria"))
    dependents = {d: t["id"] for t in tasks for d in t.get("depends_on", [])}
    if dependents:
        options.append(("order", "mutate:depends_on"))
    if len(tests) > 1:
        options.append(("remove", "remove"))
    if not options:
        return None
    pick = rng.choice([o for o in options if o[1] not in used] or options)[0]
    if pick == "remove":
        return _removal(lang, "results", rng.choice(tests), category="silent_exclusion", lesson="dropped", **base)
    if pick == "weak":
        t = rng.choice(tests)
        weak = rng.choice(WEAK_CRITERIA.get(lang, WEAK_CRITERIA["en"]))
        return _mutation("results", t["id"], "pass_criteria", weak, t.get("pass_criteria"),
                         category="criterion_proves_nothing", lesson="weak", **base)
    first = rng.choice(sorted(dependents))
    later = dependents[first]
    original = ", ".join(next(t for t in tasks if t["id"] == first).get("depends_on", [])) or "-"
    return _mutation("tasks", first, "depends_on", later, original, category="order_wrong", lesson="order", **base)


def _from_candidate(feature: Feature, gate: str, c: Dict[str, Any]) -> Dict[str, Any]:
    from runtime.i18n import lang_of, mark

    lang = lang_of(feature.ws)
    block = c["block"]
    meta = {"difficulty": c["difficulty"], "category": c["category"], "why": c["why_wrong"].strip(), "source": "agent",
            "against": _against(c), "technique": candidate_technique(feature, c)}
    if c["op"] == "mutate":
        field = c["field"]
        original = _original(feature, block, c)
        return _mutation(block, c["target"], field, _shown(lang, field, str(c["replacement"]).strip()),
                         _shown(lang, field, original) if original is not None else None, step=c.get("step"), **meta)
    if c["op"] == "remove":
        return _removal(lang, block, _targets(feature)[block][c["target"]], **meta)
    if block == "decisions":
        from runtime.i18n import t

        item = _next_id("ASM", [a.get("id", "") for a in feature.requirements().get("assumptions", [])])
        risk = _shown(lang, "risk", str(c.get("risk") or "low"))
        head = [f"**{t(lang, 'assumed_for_you')}**", "", f"| ID | {t(lang, 'assumption')} | {t(lang, 'risk')} |",
                "|---|---|---|"]
        return {"op": "add", "kind": "assumption", "id": item, "text": c["title"], "block": "decisions",
                "files": BLOCK_FILES["decisions"], **meta, "head": head,
                "row": f"| {item} | {_cell(c['title'])} | {risk} |"}
    if block == "tasks":
        item = _next_id("TASK", [t["id"] for t in feature.task_graph().get("tasks", [])])
        return {"op": "add", "kind": "plan", "id": item, "text": c["title"], "block": "tasks",
                "files": BLOCK_FILES["tasks"], **meta,
                "row": _task_row(lang, item, c["title"], str(c.get("depends_on") or "-"), str(c.get("risk") or "low"))}
    item = _next_id("TEST", [t["id"] for t in feature.test_plan().get("tests", [])])
    result = str(c.get("result") or mark(lang, "not_run"))
    runner = c.get("runner") if c.get("runner") in ("command", "agent", "human") else "command"
    return {"op": "add", "kind": "result" if gate == "final" else "verification", "id": item,
            "text": f"{c['title']}: {c['pass_criteria']}" + (f" -> {result}" if gate == "final" else ""),
            "block": "results", "files": BLOCK_FILES["results"], **meta,
            "row": _result_row(lang, str(c.get("requirement") or "-"), item, c["title"], runner, c["pass_criteria"],
                               result, str(c.get("evidence") or "-"))}


def _plant(feature: Feature, gate: str, rng: random.Random) -> Dict[str, Any]:
    tier = level(feature.ws)
    avoid = set(recent_categories(feature.ws))
    used = set(recent_techniques(feature.ws))
    usable = [c for c in pool(feature, gate) if not candidate_problems(feature, gate, c)]
    at_tier = [c for c in usable if c["difficulty"] == tier]
    how = {id(c): candidate_technique(feature, c) for c in at_tier}
    at_tier = [c for c in at_tier if how[id(c)] != "number"] or at_tier
    fresh = [c for c in at_tier if c["category"] not in avoid]
    unseen = [c for c in fresh if how[id(c)] not in used]
    choices = unseen or fresh or [c for c in at_tier if how[id(c)] not in used] or at_tier
    if choices:
        return _from_candidate(feature, gate, rng.choice(choices))
    if tier == "hard":
        act = _hard(feature, gate, rng)
        if act:
            return act
        tier = "normal"
    return _easy_or_normal(feature, gate, rng, tier)


def _lesson(lang: str, act: Dict[str, Any]) -> str:
    text = act.get("why") or LESSON[lang].get(act.get("lesson") or "easy", "")
    lines = [WHY[lang].format(why=text)] if text else []
    if act.get("op") == "mutate" and act.get("original"):
        lines.append(LESSON[lang]["was"].format(original=act["original"]))
    if act.get("op") == "remove":
        lines.append(LESSON[lang]["gone"].format(original=act["original"]))
    if act.get("against"):
        lines.append(LESSON[lang]["against"].format(ids=", ".join(act["against"])))
    if act.get("difficulty"):
        lines.append(LEVEL_LINE[lang].format(level=act["difficulty"]))
    return "\n".join(lines)


def _record(act: Dict[str, Any], outcome: str, **extra: Any) -> Dict[str, Any]:
    return {"gate": act["gate"], "item": act["id"], "kind": act["kind"], "outcome": outcome,
            "attempts": act.get("attempts", 0), "difficulty": act.get("difficulty"),
            "category": act.get("category"), "technique": act.get("technique"),
            "source": act.get("source", "builtin"), "planted_at": act["planted_at"], "ended_at": now(), **extra}


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
    planted.setdefault("technique", _technique(planted.get("op"), planted.get("block"), planted.get("field"),
                                               planted.get("original"), planted.get("replacement")))
    data["active"] = planted
    save(feature, data)
    pools = _pools(feature)
    if planted.get("source") == "agent" and pools.pop(gate, None):
        write_json_atomic(_pool_path(feature), pools)
    return True


def on_leave_state(feature: Feature, state: str, reason: str) -> None:
    gate = GATE_FOR_STATE.get(state)
    data = load(feature)
    act = data.get("active")
    if not gate or not act or act.get("gate") != gate:
        return
    data["history"].append(_record(act, reason))
    data["active"] = None
    save(feature, data)
    feature.emit("redpill_ended", gate=gate, outcome=reason, planted_at=act["planted_at"])


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
        data["history"].append(_record(act, "caught", caught_by=by))
        data["active"] = None
        save(feature, data)
        feature.emit("redpill_caught", gate=act["gate"], planted_at=act["planted_at"], actor=f"human:{by}", **proof)
        docs.render(feature)
        late = "\n" + LATE[lang] if act.get("attempts", 0) else ""
        return {"caught": True, "message": (PRAISE[lang] + late + "\n" + _lesson(lang, act)).strip()}
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
    data["history"].append(_record(act, "missed", revealed_by=by))
    data["active"] = None
    save(feature, data)
    feature.emit("redpill_revealed", gate=act["gate"], planted_at=act["planted_at"], actor=f"human:{by}",
                 **(proof or {}))
    docs.render(feature)
    return (REVEAL[lang].format(id=act["id"], text=act["text"]) + "\n" + _lesson(lang, act)).strip()


def open_flags(feature: Feature) -> List[Dict[str, Any]]:
    return load(feature).get("flags", [])


SPLIT_RE = re.compile(r"(?<!\\)\|")


def _set_cell(line: str, col: int, value: str) -> str:
    parts = SPLIT_RE.split(line)
    if col + 1 >= len(parts) - 1:
        return line
    parts[col + 1] = f" {value} "
    return "|".join(parts)


def _mutate(act: Dict[str, Any], block: str, lines: List[str]) -> List[str]:
    target, col = act["target"], COLUMNS[block][act["field"]]
    word = re.compile(rf"(?<![\w-]){re.escape(target)}(?![\w-])")
    if block == "steps":
        start = next((i for i, l in enumerate(lines) if l.startswith("**") and word.search(l)), None)
        if start is None:
            return lines
        for i in range(start + 1, len(lines)):
            if lines[i].startswith("**"):
                break
            if re.match(rf"^\|\s*{act.get('step')}\s*\|", lines[i]):
                lines[i] = _set_cell(lines[i], col, _cell(act["replacement"]))
                break
        return lines
    id_col = 1 if block == "results" else 0
    width = ROW_WIDTH.get(act["field"]) if block == "decisions" else None
    for i, line in enumerate(lines):
        if not line.startswith("|"):
            continue
        cells = SPLIT_RE.split(line)[1:-1]
        if len(cells) <= max(col, id_col) or not word.search(cells[id_col]):
            continue
        if width and len(cells) != width:
            continue
        value = _cell(act["replacement"]) if act["field"] not in ("result", "evidence") else act["replacement"]
        if block == "results" and act["field"] == "title":
            value = f"{target} {value}"
        lines[i] = _set_cell(line, col, value)
        break
    return lines


def _drop(act: Dict[str, Any], block: str, lines: List[str]) -> List[str]:
    word = re.compile(rf"(?<![\w-]){re.escape(act['target'])}(?![\w-])")
    id_col = 1 if block == "results" else 0
    for i, line in enumerate(lines):
        if not line.startswith("|"):
            continue
        cells = SPLIT_RE.split(line)[1:-1]
        if len(cells) > id_col and word.search(cells[id_col]):
            del lines[i]
            break
    return lines


def _append_assumption(act: Dict[str, Any], lines: List[str]) -> List[str]:
    rows = [i for i, l in enumerate(lines) if re.match(r"^\|\s*ASM-\d+", l)]
    if rows:
        lines.insert(rows[-1] + 1, act["row"])
        return lines
    if not any(l.startswith("|") for l in lines):
        return list(act["head"]) + [act["row"]]
    while lines and not lines[-1].strip():
        lines.pop()
    return lines + [""] + list(act["head"]) + [act["row"]]


def inject(feature: Feature, fname: str, block: str, text: str) -> str:
    act = load(feature).get("active")
    if not act or block != act["block"] or fname not in act["files"]:
        return text
    lines = text.split("\n")
    if act.get("op") == "mutate":
        return "\n".join(_mutate(act, block, lines))
    if act.get("op") == "remove":
        return "\n".join(_drop(act, block, lines))
    if block == "decisions":
        return "\n".join(_append_assumption(act, lines))
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


def _summary(hist: List[Dict[str, Any]]) -> Dict[str, Any]:
    decided = [h for h in hist if h["outcome"] in ("caught", "missed")]
    late = sum(1 for h in decided if h["outcome"] == "caught" and h.get("attempts", 0))
    caught = sum(1 for h in decided if h["outcome"] == "caught") - late
    return {
        "drills": len(hist),
        "caught": caught,
        "caught_after_refusal": late,
        "missed": len(decided) - caught - late,
        "rubber_stamps": sum(h.get("attempts", 0) for h in hist),
        "catch_rate": round(caught / len(decided), 3) if decided else None,
    }


def stats(feature: Feature) -> Dict[str, Any]:
    return _summary(load(feature).get("history", []))


def progress(ws: Workspace) -> Dict[str, Any]:
    hist = workspace_history(ws)
    out = _summary(hist)
    out["level"] = level(ws)
    out["by_difficulty"] = {d: _summary([h for h in hist if (h.get("difficulty") or "easy") == d])
                            for d in DIFFICULTIES}
    missed: Dict[str, int] = {}
    for h in hist:
        if h["outcome"] == "missed" and h.get("category"):
            missed[h["category"]] = missed.get(h["category"], 0) + 1
    out["missed_categories"] = dict(sorted(missed.items(), key=lambda kv: -kv[1]))
    return out


def set_config(ws: Workspace, values: Dict[str, Any]) -> None:
    from runtime.config import set_section

    set_section(ws.config_path, "redpill", values)
