from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Tuple

from runtime.state.store import Feature

PHRASES: Dict[str, List[str]] = {
    "en": [
        r"\bdelv(?:e|es|ed|ing)\b", r"\btapestry\b", r"\btestament to\b", r"\bseamless(?:ly)?\b",
        r"\bleverag(?:e|es|ed|ing)\b", r"\butiliz(?:e|es|ed|ing)\b", r"\bcomprehensive(?:ly)?\b",
        r"\bcutting[- ]edge\b", r"\bstate[- ]of[- ]the[- ]art\b", r"\bbest[- ]in[- ]class\b", r"\bworld[- ]class\b",
        r"\bgame[- ]chang(?:er|ing)\b", r"\brevolutioni[sz]e\w*", r"\bin today's\b", r"\bit(?:'s| is) worth noting\b",
        r"\bit(?:'s| is) important to note\b", r"\bplays? an? (?:crucial|key|vital|pivotal) role\b", r"\bpivotal\b",
        r"\bstreamlin(?:e|es|ed|ing)\b", r"\bempower(?:s|ed|ing)?\b", r"\bholistic(?:ally)?\b", r"\bsynerg\w+",
        r"\bparadigm\b", r"\bnavigat(?:e|ing) the complexit\w+", r"\bin conclusion\b", r"\bmoreover\b",
        r"\bfurthermore\b", r"\badditionally\b", r"\blet's dive\b", r"\bdeep dive\b", r"\brest assured\b",
        r"\bnot (?:just|only|merely)\b", r"\bmore than just\b", r"\bat its core\b", r"\bin essence\b",
        r"\bensur(?:e|es|ing) (?:a )?(?:smooth|optimal|seamless)\b", r"\bunlock(?:s|ed|ing)?\b(?! the (?:file|mutex|lock))",
        r"\belevat(?:e|es|ed|ing)\b", r"\bfoster(?:s|ed|ing)?\b", r"\bmeticulous(?:ly)?\b", r"\bnuanced\b",
        r"\buser[- ]friendly\b", r"\bintuitive(?:ly)?\b", r"\beffortless(?:ly)?\b",
    ],
    "ko": [
        r"혁신적", r"획기적", r"원활", r"극대화", r"시너지", r"한 차원", r"주목할 만한", r"결론적으로", r"종합적으로",
        r"요약하자면", r"살펴보겠습니다", r"알아보겠습니다", r"매끄러[운움]", r"매끄럽게", r"견고한", r"탄탄한",
        r"것이 중요합니다", r"에 그치지 않고", r"단순(?:한|히)[^.\n]{0,25}(?:아니라|아닌|넘어)", r"뿐만 아니라",
        r"다양한 (?:측면|관점|요소)", r"최적의 경험", r"사용자 친화적", r"직관적", r"본질적으로", r"핵심은 ",
        r"이를 통해", r"를 통해 [^.\n]{0,30}할 수 있습니다", r"효과적으로", r"체계적으로", r"심층", r"포괄적",
    ],
}
MAX_EM_DASHES = 2
SKIP_KEYS = {"id", "key", "command", "covers", "paths", "path", "sources", "ref", "log_ref", "evidence", "depends_on",
             "task_ids", "requirement_ids", "children", "verification", "environment", "type", "level", "runner",
             "status", "decided_by", "at", "scope"}
JSON_FILES = ("requirements", "task_graph", "test_plan", "split")
FENCE_RE = re.compile(r"```.*?```", re.S)
BLOCK_RE = re.compile(r"<!-- hr:([a-z]+):start -->.*?<!-- hr:\1:end -->", re.S)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
FILL_RE = re.compile(r"\[FILL(?::[^\]]*)?\]")
LINK_TARGET_RE = re.compile(r"\]\([^)]*\)")


def settings(ws: Any) -> Dict[str, Any]:
    cfg = ws.config().get("docs") or {}
    raw = cfg.get("prose_check", "error")
    mode = "off" if raw is False else str(raw or "error").lower()
    return {
        "mode": mode if mode in ("error", "warn", "off") else "error",
        "banned": [str(x) for x in (cfg.get("banned_phrases") or []) if str(x).strip()],
        "allowed": [str(x).lower() for x in (cfg.get("allowed_phrases") or []) if str(x).strip()],
    }


def _patterns(conf: Dict[str, Any]) -> List[re.Pattern]:
    pats = [re.compile(p, re.I) for lang in PHRASES.values() for p in lang]
    pats += [re.compile(re.escape(b), re.I) for b in conf["banned"]]
    return pats


def _blank(match: "re.Match[str]") -> str:
    return re.sub(r"[^\n]", " ", match.group(0))


def strip_markdown(text: str) -> str:
    for rx in (BLOCK_RE, FENCE_RE, INLINE_CODE_RE, FILL_RE, LINK_TARGET_RE):
        text = rx.sub(_blank, text)
    return text


def find(text: str, conf: Dict[str, Any]) -> List[Tuple[int, str]]:
    hits: List[Tuple[int, str]] = []
    lines = text.splitlines()
    for no, line in enumerate(lines, 1):
        for rx in _patterns(conf):
            for m in rx.finditer(line):
                word = m.group(0).strip()
                if word.lower() not in conf["allowed"]:
                    hits.append((no, word))
    dashes = [no for no, line in enumerate(lines, 1) if not line.lstrip().startswith("#") for _ in re.finditer("—", line)]
    if len(dashes) > MAX_EM_DASHES:
        hits.append((dashes[MAX_EM_DASHES], f"{len(dashes)} em dashes (—): use a period, a comma, or a colon"))
    return hits


def _strings(obj: Any, trail: str = "") -> Iterable[Tuple[str, str]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in SKIP_KEYS:
                continue
            yield from _strings(v, f"{trail}.{k}" if trail else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            label = v.get("id") or v.get("key") if isinstance(v, dict) else None
            yield from _strings(v, f"{trail}[{label or i}]")
    elif isinstance(obj, str):
        yield trail, obj


def check(feature: Feature, doc_names: Iterable[str]) -> List[str]:
    from runtime.state.store import INTERNAL_FILES

    conf = settings(feature.ws)
    if conf["mode"] == "off":
        return []
    out: List[str] = []
    for name in doc_names:
        path = feature.dir / name
        if not path.exists():
            continue
        for no, word in find(strip_markdown(path.read_text(encoding="utf-8")), conf):
            out.append(f"{name}:{no}: {word!r}")
    for key in JSON_FILES:
        data = feature.load(key)
        if not data:
            continue
        for trail, text in _strings(data):
            for _, word in find(text, conf):
                out.append(f"{INTERNAL_FILES[key]} {trail}: {word!r}")
    return out


def doc_names(feature: Feature) -> List[str]:
    names = ["overview.md", "requirements.md", "design.md", "verification.md", "review-report.md"]
    names += sorted(p.relative_to(feature.dir).as_posix() for p in (feature.dir / "tasks").glob("*.md"))
    return names


ADVICE = ("filler wording - say the specific thing instead: the number, the file, the behaviour, the reason "
          "(writing reference; `docs.prose_check` and `docs.allowed_phrases` in config.yaml adjust this check)")
