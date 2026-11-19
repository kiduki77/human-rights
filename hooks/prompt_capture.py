#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PENDING = {
    "awaiting_design_approval": "design approval",
    "awaiting_final_approval": "final approval",
    "awaiting_split_approval": "approval of the split into features",
    "blocked": "an unblock decision",
}


def repo_root(cwd: str) -> Path:
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd or None, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL).stdout.decode().strip()
        if out:
            return Path(out)
    except (FileNotFoundError, NotADirectoryError, OSError):
        pass
    return Path(cwd or ".")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except Exception:
        return
    prompt = data.get("prompt") or ""
    if not prompt.strip():
        return
    from runtime import human
    from runtime.state.store import Workspace

    ws = Workspace(repo_root(data.get("cwd") or ""))
    if not ws.initialized:
        return
    try:
        human.capture(ws, prompt, data.get("session_id"))
        fid = ws.active_feature_id()
        st = ws.resolve(fid).state() if fid else None
    except Exception:
        return
    pending = PENDING.get((st or {}).get("state"))
    if pending:
        print(f"[human-rights] {st['feature_id']} is waiting for {pending}. If this message approves, points out "
              "items, or requests changes, act on it through `hr ... --quote \"<their exact words>\"` "
              "(see the human-rights skill, approvals reference).")


if __name__ == "__main__":
    main()
