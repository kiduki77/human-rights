from __future__ import annotations

from typing import Any, Dict

LANGS = ("en", "ko")

TEXT: Dict[str, Dict[str, str]] = {
    "en": {
        "item": "Item", "value": "Value", "state": "State", "mode": "Mode", "unclassified": "unclassified",
        "design_approval": "Design approval", "final_approval": "Final approval",
        "next_decision": "Next human decision", "none": "none", "not_required": "not required",
        "pending": "pending", "approved": "approved ({who}, {at})", "no_tasks": "_no tasks_",
        "no_impact": "_no search for other places that use this was recorded_",
        "impact_concept": "What this change touches", "impact_searched": "Searched for",
        "impact_where": "Where", "impact_uses": "How it uses it", "impact_relation": "What happens to it",
        "impact_covered": "Task, test or reason", "impact_evidence": "Evidence",
        "impact_none": "The search found no other place that uses it.",
        "impact_rechecked": "Searched again after the code was written, at `{sha}`, for {terms}. Nothing outside this table.",
        "impact_recheck_stale": "The second search was recorded at `{sha}`, and the code has changed since. It has to run again.",
        "task": "Task", "purpose": "Purpose", "depends_on": "Depends on", "risk": "Risk", "status": "Status",
        "no_tests": "_no required tests_", "verified_code": "Verified code", "uncommitted": " (+uncommitted changes)",
        "requirement": "Requirement", "test": "Test", "level": "Level", "result": "Result", "evidence": "Evidence",
        "run_by": "Run by", "pass_criteria": "Pass criteria", "see_steps": "({n} steps below)",
        "regression_scope": "Regression scope", "estimated_total": "Estimated run time for the whole plan",
        "minutes": "{n} min", "seconds": "{n} s", "carried": "(unchanged since {sha}: later commits did not touch what it covers)",
        "by_agent": "(agent-run, per-step evidence)", "by_human": "(human: {who})",
        "step_do": "Do", "step_expect": "Passes only if", "human_reason": "why a human", "environment": "environment",
        "no_steps": "_no agent or human tests_", "no_decisions": "_no decisions or assumptions recorded_",
        "changed_from_answer": "Changed from your answer - confirm these first",
        "question": "Question", "you_said": "You said", "now": "Now", "why": "Why", "decision": "Decision",
        "decided_by": "Decided by", "assumed_for_you": "Assumed for you - say so if you disagree",
        "assumption": "Assumption",
        "decide_design": "review the design, then approve, point out problems, or request changes in chat",
        "decide_final": "review the result, then approve (with any residual risk you accept), point out problems, "
                        "or request changes in chat",
        "decide_split": "review the list of features, then approve, or say in chat what to drop, merge, add or "
                        "reorder",
        "group": "group", "split_approval": "Split approval", "features": "Features", "feature": "Feature",
        "outcome": "Result when done", "verify_alone": "Verified on its own by", "built_on": "Built on",
        "expected_mode": "Expected grade", "sources": "Source", "code_now": "Code today", "part_of": "Part of",
        "no_features": "_no features listed yet_", "no_shared": "_nothing decided for the whole group_",
        "no_excluded": "_nothing left out_", "left_out": "Mentioned but not built here", "why_not": "Why not",
        "unread": "Not read - check these yourself", "part": "Part", "reason": "Reason",
        "progress": "Progress", "progress_value": "{done} of {total} features done",
        "source_document": "Source document",
        "decide_escalation": "escalation: {reason} - decide in chat how to proceed (that releases it)",
        "decide_blocker": "resolve blocker: {reason}",
        "decide_questions": "answer open questions: {qs}",
        "decide_merge": "merge (auto-merge is off by default): pass `hr merge-check`, then merge the PR",
        "task_none": "none", "task_not_run": "not run", "task_not_implemented": "Not implemented yet.",
        "task_boundary": "{paths}. Anything outside goes back through `hr scope-change`.",
    },
    "ko": {
        "item": "항목", "value": "값", "state": "상태", "mode": "모드", "unclassified": "미분류",
        "design_approval": "설계 승인", "final_approval": "최종 승인",
        "next_decision": "다음 사람 결정", "none": "없음", "not_required": "필요 없음",
        "pending": "대기 중", "approved": "승인됨 ({who}, {at})", "no_tasks": "_작업 없음_",
        "no_impact": "_이것을 쓰는 다른 곳을 찾아본 기록이 없음_",
        "impact_concept": "이 변경이 건드리는 것", "impact_searched": "검색한 이름",
        "impact_where": "위치", "impact_uses": "어떻게 쓰는가", "impact_relation": "어떻게 되는가",
        "impact_covered": "작업, 테스트 또는 이유", "impact_evidence": "근거",
        "impact_none": "검색에서 이것을 쓰는 다른 곳이 나오지 않았다.",
        "impact_rechecked": "코드를 쓴 뒤 `{sha}` 에서 {terms} 로 다시 검색했다. 이 표 밖의 것은 없었다.",
        "impact_recheck_stale": "두 번째 검색은 `{sha}` 에서 기록됐고 그 뒤 코드가 바뀌었다. 다시 해야 한다.",
        "task": "작업", "purpose": "목적", "depends_on": "선행 작업", "risk": "위험", "status": "상태",
        "no_tests": "_필수 테스트 없음_", "verified_code": "검증한 코드", "uncommitted": " (+커밋 안 된 변경)",
        "requirement": "요구사항", "test": "테스트", "level": "수준", "result": "결과", "evidence": "근거",
        "run_by": "실행 주체", "pass_criteria": "통과 기준", "see_steps": "(아래 {n}단계)",
        "regression_scope": "회귀 범위", "estimated_total": "전체 계획 예상 실행 시간",
        "minutes": "{n}분", "seconds": "{n}초", "carried": "({sha} 이후 변경 없음: 이후 커밋이 이 테스트의 대상 경로를 건드리지 않음)",
        "by_agent": "(에이전트 실행, 단계별 증거 있음)", "by_human": "(사람: {who})",
        "step_do": "할 일", "step_expect": "이럴 때만 통과", "human_reason": "사람이 하는 이유", "environment": "환경",
        "no_steps": "_에이전트·사람 테스트 없음_", "no_decisions": "_기록된 결정·가정 없음_",
        "changed_from_answer": "답변과 달라진 것 - 먼저 확인해 주세요",
        "question": "질문", "you_said": "답변하신 내용", "now": "현재", "why": "이유", "decision": "결정",
        "decided_by": "결정 주체", "assumed_for_you": "대신 가정한 것 - 다르면 말씀해 주세요",
        "assumption": "가정",
        "decide_design": "설계를 검토하고 채팅으로 승인, 문제 지적, 변경 요청 중 하나를 알려주세요",
        "decide_final": "결과를 검토하고 채팅으로 승인(감수할 잔여 위험 포함), 문제 지적, 변경 요청 중 하나를 알려주세요",
        "decide_split": "기능 목록을 검토하고 채팅으로 승인하거나, 뺄 것·합칠 것·추가할 것·순서를 알려주세요",
        "group": "묶음", "split_approval": "분할 승인", "features": "기능", "feature": "기능",
        "outcome": "완료되면 되는 것", "verify_alone": "단독 검증 방법", "built_on": "선행 기능",
        "expected_mode": "예상 등급", "sources": "출처", "code_now": "현재 코드", "part_of": "소속 묶음",
        "no_features": "_아직 기능 목록 없음_", "no_shared": "_묶음 전체에 대한 결정 없음_",
        "no_excluded": "_제외한 것 없음_", "left_out": "요청에 있지만 여기서 만들지 않는 것", "why_not": "제외 이유",
        "unread": "읽지 못한 부분 - 직접 확인해 주세요", "part": "부분", "reason": "이유",
        "progress": "진행", "progress_value": "기능 {total}개 중 {done}개 완료",
        "source_document": "원본 문서",
        "decide_escalation": "에스컬레이션: {reason} - 어떻게 진행할지 채팅으로 결정해 주세요 (그러면 해제됩니다)",
        "decide_blocker": "막힌 원인 해결: {reason}",
        "decide_questions": "남은 질문에 답해 주세요: {qs}",
        "decide_merge": "머지 (자동 머지는 기본으로 꺼져 있음): `hr merge-check` 통과 후 PR을 머지하세요",
        "task_none": "없음", "task_not_run": "미실행", "task_not_implemented": "아직 구현하지 않음.",
        "task_boundary": "{paths}. 그 밖은 `hr scope-change` 로 다시 승인.",
    },
}

STATES_KO = {
    "created": "생성됨", "proposed": "묶음에서 대기 중", "splitting": "기능으로 나누는 중",
    "awaiting_split_approval": "분할 승인 대기", "delivering": "기능 진행 중", "triaging": "분류 중", "clarifying": "의도 확인 중", "investigating": "코드 조사 중",
    "planning": "설계·분해 중", "awaiting_design_approval": "설계 승인 대기", "executing": "구현 중",
    "verifying_tasks": "작업 검증 중", "integrating": "통합 테스트 중", "awaiting_final_approval": "최종 승인 대기",
    "ready_to_merge": "머지 준비 완료", "completed": "완료", "blocked": "막힘", "rework_required": "재작업 필요",
    "cancelled": "취소됨", "failed": "실패",
}

VALUES_KO = {
    "task_status": {"planned": "계획됨", "in_progress": "진행 중", "implemented": "구현됨", "verified": "검증됨",
                    "rework_required": "재작업 필요", "blocked": "막힘", "cancelled": "취소됨"},
    "risk": {"low": "낮음", "medium": "보통", "high": "높음"},
    "level": {"task": "작업", "integration": "통합"},
    "runner": {"command": "스크립트", "agent": "에이전트", "human": "사람"},
    "regression": {"targeted": "영향 범위만", "full": "전체"},
    "relation": {"change": "수정", "check": "수정 없이 확인", "unrelated": "영향 없음"},
    "decided_by": {"user": "사용자", "default": "제안 기본값", "code": "기존 코드", "group": "묶음 결정"},
    "code_status": {"missing": "없음", "partial": "일부 있음", "exists": "이미 있음", "conflict": "충돌"},
}
VALUES_EN = {
    "relation": {"change": "changed", "check": "checked, not changed", "unrelated": "not affected"},
    "runner": {"command": "script", "agent": "agent", "human": "human"},
    "decided_by": {"user": "you", "default": "proposed default", "code": "existing code", "group": "group decision"},
}

MARKS = {
    "en": {
        "passed": "✅ pass", "failed": "❌ fail", "stale": "⚠️ not re-run since code changed", "not_run": "⏳ not run",
        "passed_uncommitted": "✅ pass (uncommitted)", "failed_uncommitted": "❌ fail (uncommitted)",
        "unbound_passed": "✅ pass (not version-bound)", "unbound_failed": "❌ fail (not version-bound)",
    },
    "ko": {
        "passed": "✅ 통과", "failed": "❌ 실패", "stale": "⚠️ 코드 변경 후 재실행 안 됨", "not_run": "⏳ 미실행",
        "passed_uncommitted": "✅ 통과 (커밋 전)", "failed_uncommitted": "❌ 실패 (커밋 전)",
        "unbound_passed": "✅ 통과 (버전 미고정)", "unbound_failed": "❌ 실패 (버전 미고정)",
    },
}


def lang_of(ws: Any) -> str:
    lang = ((ws.config().get("docs") or {}).get("language") or "en").lower()
    return lang if lang in LANGS else "en"


def t(lang: str, key: str, **kw: Any) -> str:
    text = TEXT.get(lang, TEXT["en"]).get(key) or TEXT["en"][key]
    return text.format(**kw) if kw else text


def state_label(lang: str, state: str, default: str) -> str:
    return STATES_KO.get(state, default) if lang == "ko" else default


def value(lang: str, kind: str, raw: str) -> str:
    table = VALUES_KO if lang == "ko" else VALUES_EN
    return table.get(kind, {}).get(raw, raw)


def mark(lang: str, status: str) -> str:
    return MARKS.get(lang, MARKS["en"]).get(status, status)
