from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime.common import GateError, HRError, git, sha256_bytes
from runtime.state.store import Feature, Workspace

KEEP = 20
MIN_QUOTE = 2


def prompts_path(ws: Workspace) -> Path:
    return ws.wf / ".local" / "prompts.jsonl"


def _stamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def capture(ws: Workspace, text: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    path = prompts_path(ws)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"at": _stamp(), "sha256": sha256_bytes(text.encode("utf-8")), "session_id": session_id, "text": text}
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    lines = [l for l in lines if l.strip()][-(KEEP - 1):] + [json.dumps(entry, ensure_ascii=False)]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    return entry


def latest(ws: Workspace) -> Optional[Dict[str, Any]]:
    path = prompts_path(ws)
    if not path.exists():
        return None
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return None


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _to_utc(ts: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def entered_at(feature: Feature, state: str) -> Optional[str]:
    for ev in reversed(feature.events()):
        if ev.get("event") == "state_changed" and ev.get("to") == state:
            return ev.get("timestamp")
    return None


def verify(ws: Workspace, quote: str, since: Optional[str] = None) -> Dict[str, Any]:
    q = _norm(quote or "")
    if len(q) < MIN_QUOTE:
        raise HRError("--quote must hold the human's words from their latest message")
    entry = latest(ws)
    if entry is None:
        raise GateError("no human message has been captured. The human-rights prompt hook must be installed "
                        "(Claude Code plugin), or the human runs the command in their own terminal with --by.")
    if q not in _norm(entry.get("text", "")):
        raise GateError("--quote does not match the human's latest message. Quote their exact words; "
                        "a chat action needs a real human message behind it.")
    if since and _to_utc(entry["at"]).replace(microsecond=0) < _to_utc(since):
        raise GateError("the human's latest message predates this decision point. Ask them again and quote the new reply.")
    return {"quote": quote.strip(), "prompt_sha256": entry["sha256"], "prompt_at": entry["at"]}


def default_name(ws: Workspace) -> str:
    return git(ws.root, "config", "user.name") or "human"


def at_terminal() -> bool:
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except (AttributeError, ValueError):
        return False


def require_terminal() -> None:
    if not at_terminal():
        raise GateError("without --quote this is a human decision made at a terminal, and this process has none: "
                        "a tool or a script started it. In chat, the human decides in a message and the agent "
                        "passes their exact words with --quote. Otherwise the human runs the command in their own "
                        "terminal.")


def resolve(ws: Workspace, by: Optional[str], quote: Optional[str], since: Optional[str] = None,
            terminal: bool = True) -> Dict[str, Any]:
    if quote is None:
        if not by:
            raise HRError("--by is required (or --quote with the human's chat message)")
        if terminal:
            require_terminal()
        return {"by": by, "via": "cli"}
    proof = verify(ws, quote, since)
    return {"by": by or default_name(ws), "via": "chat", **proof}


def proof_fields(who: Dict[str, Any]) -> Dict[str, Any]:
    return {k: who[k] for k in ("via", "quote", "prompt_sha256") if k in who}


def flags_since(items: List[Dict[str, Any]], since: Optional[str]) -> List[Dict[str, Any]]:
    if not since:
        return list(items)
    edge = _to_utc(since)
    return [x for x in items if _to_utc(x["at"]) >= edge]
