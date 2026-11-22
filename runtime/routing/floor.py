from __future__ import annotations

from typing import Any, Dict, List

from runtime.common import HRError, changed_files_since, dirty_paths, head_sha, path_matches, write_text_atomic
from runtime.routing.router import MODES
from runtime.state.store import Workspace

Floor = Dict[str, str]

FILENAME = "floor.yaml"
HEADER = (
    "# Paths that always need at least the given level.\n"
    "# Changed only by the owner (by hand or `hr floor add/remove --quote`).\n"
)


def path(ws: Workspace):
    return ws.wf / FILENAME


def load(ws: Workspace) -> Floor:
    p = path(ws)
    if not p.exists():
        return {}
    text = p.read_text(encoding="utf-8")
    try:
        import yaml

        data = yaml.safe_load(text) or {}
    except ImportError:
        from runtime.config import parse_simple_yaml

        data = parse_simple_yaml(text)
    except Exception as exc:
        raise HRError(f"{p}: not valid YAML ({exc})")
    if not isinstance(data, dict):
        raise HRError(f"{p}: expected a mapping of glob -> level (L0..L3)")
    for key, level in data.items():
        if not isinstance(key, str) or level not in MODES:
            raise HRError(f"{p}: {key!r}: the level must be one of {', '.join(MODES)}, not {level!r}")
    return dict(data)


def check_pattern(pattern: str) -> str:
    pattern = pattern.strip()
    if not pattern or any(c in pattern for c in "\"'\\:\n"):
        raise HRError(f"floor pattern {pattern!r}: use a plain glob such as `src/auth/**` "
                      "(no quotes, backslashes or colons)")
    return pattern


def save(ws: Workspace, rules: Floor) -> None:
    lines = [f'"{check_pattern(k)}": {rules[k]}' for k in sorted(rules)]
    write_text_atomic(path(ws), HEADER + "\n".join(lines) + ("\n" if lines else ""))


def touched(ws: Workspace, st: Dict[str, Any], declared: List[str]) -> List[str]:
    root = ws.root
    base = ((st.get("git") or {}).get("base_sha"))
    seen = set(declared) | set(changed_files_since(root, base, head_sha(root)) or [])
    for entry in dirty_paths(root):
        seen.update(p.strip().strip('"') for p in entry.split(" -> "))
    return sorted(seen)


def hits(rules: Floor, paths: List[str]) -> List[Dict[str, Any]]:
    out = []
    for pattern in sorted(rules):
        matched = [p for p in paths if path_matches(p, [pattern]) or path_matches(p.rstrip("/") + "/", [pattern])]
        if matched:
            out.append({"pattern": pattern, "level": rules[pattern], "paths": matched})
    return out
