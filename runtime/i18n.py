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
        "no_review": "_no review of the written code is recorded. It runs before final approval, at L2 and L3_",
        "review_done": "{id}: {who} read {files} changed file(s) at `{sha}` and reported {n} finding(s).",
        "review_stale": "{id} was recorded at `{sha}`, and the code has changed since. The review has to run again.",
        "review_none": "It found no change that nothing asks for, no repeated code and no unused code.",
        "finding": "Finding", "review_what": "What it is", "review_disposition": "What was decided",
        "review_existing": "already at `{place}`", "disposition_none": "**nothing yet: decide before final approval**",
        "disposition_removed": "removed ({review} did not find it again)",
        "disposition_reported_again": "the code changed and {review} reported it again",
        "disposition_accepted": "kept by {who}: {reason}",
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
        "size_unavailable": "_the size of the change is not available: no starting commit is recorded for this feature, or the repository has no git history_",
        "size_empty": "No file has changed since `{base}`.",
        "size_range": "Counted from `{base}` to `{head}`.",
        "size_range_dirty": "Counted from `{base}` to the working tree, which includes changes not committed yet.",
        "size_kind": "Counted as", "size_code": "Code", "size_tests": "Tests", "size_locks": "Lock files",
        "size_files_added": "Files added", "size_files_changed": "Files changed", "size_files_deleted": "Files deleted",
        "size_lines_added": "Lines added", "size_lines_removed": "Lines removed",
        "size_line": "{files} file(s): {added} added, {changed} changed, {deleted} deleted. Code +{cp} / -{cm} lines, tests +{tp} / -{tm}.",
        "size_deps_none": "No new dependencies.", "size_deps_new": "New dependencies: {names}.",
        "size_deps_removed": "Removed: {names}.", "size_deps_locked": "The lock files add {n} locked package(s).",
        "size_deps_unread": "Changed, and not read: {files}.",
        "size_task_files": "Files added / changed / deleted", "size_task_code": "Code lines",
        "size_task_tests": "Test lines", "size_basis": "Counted from", "size_outside": "Not in any task",
        "size_overlap": "A file that two tasks both changed is counted in both rows.",
        "focus_intro": "Read these rows closely. Each is listed for the reason shown, not because it is wrong.",
        "focus_flag": "what does approving this let happen?",
        "focus_not_user": "not decided by you ({who})",
        "focus_changed": "differs from what you answered",
        "focus_assumed": "assumed for you, {risk} risk",
        "focus_task": "{risk} risk task",
        "focus_more": "{n} more rows match and are not listed here. They are in the tables below.",
        "focus_none": "No row below is decided by someone other than you, assumed at medium or high risk, or a "
                      "high-risk task, and no routing flag is set.",
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
        "no_review": "_작성된 코드에 대한 리뷰 기록이 없음. L2·L3 에서 최종 승인 전에 실행됨_",
        "review_done": "{id}: {who} 가 `{sha}` 에서 변경된 파일 {files}개를 읽고 {n}건을 보고했다.",
        "review_stale": "{id} 는 `{sha}` 에서 기록됐고 그 뒤 코드가 바뀌었다. 리뷰를 다시 해야 한다.",
        "review_none": "요청에 없는 변경, 중복 코드, 쓰이지 않는 코드가 나오지 않았다.",
        "finding": "발견", "review_what": "내용", "review_disposition": "결정",
        "review_existing": "`{place}` 에 이미 있음", "disposition_none": "**아직 없음: 최종 승인 전에 결정 필요**",
        "disposition_removed": "제거됨 ({review} 에서 다시 나오지 않음)",
        "disposition_reported_again": "코드가 바뀌었고 {review} 에서 다시 보고됨",
        "disposition_accepted": "{who} 가 유지하기로 함: {reason}",
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
        "size_unavailable": "_변경 규모를 알 수 없음: 이 기능에 기록된 시작 커밋이 없거나 저장소에 git 이력이 없다_",
        "size_empty": "`{base}` 이후 바뀐 파일이 없다.",
        "size_range": "`{base}` 부터 `{head}` 까지 센 값.",
        "size_range_dirty": "`{base}` 부터 작업 트리까지 센 값이며, 아직 커밋하지 않은 변경을 포함한다.",
        "size_kind": "구분", "size_code": "코드", "size_tests": "테스트", "size_locks": "락 파일",
        "size_files_added": "추가한 파일", "size_files_changed": "수정한 파일", "size_files_deleted": "삭제한 파일",
        "size_lines_added": "추가한 줄", "size_lines_removed": "삭제한 줄",
        "size_line": "파일 {files}개: 추가 {added}, 수정 {changed}, 삭제 {deleted}. 코드 +{cp} / -{cm} 줄, 테스트 +{tp} / -{tm} 줄.",
        "size_deps_none": "새 의존성 없음.", "size_deps_new": "새 의존성: {names}.",
        "size_deps_removed": "제거: {names}.", "size_deps_locked": "락 파일에 패키지 {n}개가 새로 잠겼다.",
        "size_deps_unread": "바뀌었지만 읽지 못함: {files}.",
        "size_task_files": "파일 추가 / 수정 / 삭제", "size_task_code": "코드 줄",
        "size_task_tests": "테스트 줄", "size_basis": "센 기준", "size_outside": "어느 작업에도 없음",
        "size_overlap": "두 작업이 모두 바꾼 파일은 두 행에 모두 센다.",
        "focus_intro": "아래 행은 자세히 읽어 주세요. 틀려서가 아니라, 적힌 이유 때문에 올린 것입니다.",
        "focus_flag": "이것을 승인하면 무엇이 가능해지나요?",
        "focus_not_user": "직접 결정하지 않으심 ({who})",
        "focus_changed": "답변하신 내용과 다름",
        "focus_assumed": "대신 가정함, 위험 {risk}",
        "focus_task": "위험 {risk} 작업",
        "focus_more": "조건에 맞는 행 {n}개는 여기에 싣지 않았습니다. 아래 표에 있습니다.",
        "focus_none": "아래 표에는 사용자가 아닌 쪽이 결정한 것, 위험 보통 이상으로 가정한 것, 위험 높음 작업이 없고 "
                      "라우팅 플래그도 없습니다.",
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
    "size_basis": {"commits": "작업의 커밋", "scope": "작업 경로 안의 파일", "none": "기록된 경로 없음"},
    "finding_kind": {"unexplained": "요청한 적 없음", "duplicate": "이미 있는 코드", "unused": "쓰는 곳 없음"},
    "decided_by": {"user": "사용자", "default": "제안 기본값", "code": "기존 코드", "group": "묶음 결정"},
    "code_status": {"missing": "없음", "partial": "일부 있음", "exists": "이미 있음", "conflict": "충돌"},
    "flag": {"physical_safety": "물리적 안전에 영향", "vehicle_command": "기체 명령 대상 또는 비행 제어 변경",
             "auth": "인증·권한 변경", "secrets": "비밀 값 처리", "destructive_migration": "데이터를 지우는 마이그레이션",
             "irreversible_external": "되돌릴 수 없는 외부 작업"},
}
VALUES_EN = {
    "relation": {"change": "changed", "check": "checked, not changed", "unrelated": "not affected"},
    "size_basis": {"commits": "the task's commits", "scope": "files under the task's paths", "none": "no paths recorded"},
    "finding_kind": {"unexplained": "nothing asks for it", "duplicate": "already exists", "unused": "nothing uses it"},
    "runner": {"command": "script", "agent": "agent", "human": "human"},
    "decided_by": {"user": "you", "default": "proposed default", "code": "existing code", "group": "group decision"},
    "flag": {"physical_safety": "physical safety impact", "vehicle_command": "vehicle command targeting or flight control",
             "auth": "authentication or authorization", "secrets": "secret handling",
             "destructive_migration": "destructive data migration", "irreversible_external": "irreversible external action"},
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
