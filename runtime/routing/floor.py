from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from runtime.common import (EXCLUDE_SPECS, HRError, canonical, changed_files_since, dirty_paths, git, head_sha, now,
                            path_matches, sha256_bytes, write_text_atomic)
from runtime.routing.router import MODES
from runtime.state.store import Workspace

Floor = Dict[str, str]

FILENAME = "floor.yaml"
SEAL = "floor.seal"
ACCEPT = ("The owner checks the file and runs `hr floor accept` (a human decision: `--quote` in chat, or `--by` at "
          "a terminal)")
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


def seal_path(ws: Workspace):
    return ws.wf / SEAL


def rules_hash(rules: Floor) -> str:
    return sha256_bytes(canonical(rules))


def read_seal(ws: Workspace) -> Optional[Dict[str, Any]]:
    p = seal_path(ws)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def seal(ws: Workspace, rules: Floor, who: Dict[str, Any]) -> Dict[str, Any]:
    record = {"rules_sha256": rules_hash(rules), "at": now(),
              **{k: who[k] for k in ("by", "via", "quote", "prompt_sha256") if k in who}}
    write_text_atomic(seal_path(ws), json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    return record


def _in_history(ws: Workspace) -> bool:
    rel = seal_path(ws).relative_to(ws.root).as_posix()
    return bool(git(ws.root, "log", "-1", "--format=%H", "--", rel))


def problem(ws: Workspace, st: Optional[Dict[str, Any]] = None, history: bool = False) -> Optional[str]:
    rules = load(ws)
    sealed = read_seal(ws)
    if sealed is None:
        if rules:
            return f"[floor] {FILENAME} holds rules that no owner decision recorded. {ACCEPT}"
        known = bool(((st or {}).get("routing") or {}).get("floor_seal")) or (history and _in_history(ws))
        if known:
            return (f"[floor] the floor and its record ({SEAL}) are gone, and there was a floor before. {ACCEPT}, "
                    "or restores both files")
        return None
    if sealed.get("rules_sha256") != rules_hash(rules):
        gone = "" if path(ws).exists() else " (the file is missing)"
        since = f" by {sealed['by']} at {sealed['at']}" if sealed.get("by") and sealed.get("at") else ""
        return (f"[floor] {FILENAME} is not what the owner last decided{since}{gone}. Nothing recorded this "
                f"change. {ACCEPT}")
    return None


def touched(ws: Workspace, st: Dict[str, Any], declared: List[str]) -> List[str]:
    root = ws.root
    base = ((st.get("git") or {}).get("base_sha"))
    head = head_sha(root)
    changed = changed_files_since(root, base, head)
    if changed is None and base and head:
        # the start commit is no longer an ancestor of HEAD (rebase, reset, amend): compare the trees instead
        changed = (git(root, "diff", "--name-only", base, head, "--", ".", *EXCLUDE_SPECS) or "").splitlines()
    seen = set(declared) | set(changed or [])
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
