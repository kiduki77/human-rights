#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL).stdout.decode().strip()
        if out:
            return Path(out)
    except FileNotFoundError:
        pass
    return Path.cwd()


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    wf = repo_root() / ".human-rights"
    active = wf / "active.json"
    if not active.exists():
        return
    try:
        fid = json.loads(active.read_text(encoding="utf-8")).get("feature_id")
        if not fid:
            return
        found = sorted(wf.glob(f"**/{fid}/.internal/state.json"), key=lambda p: len(p.parts))
        st = json.loads(found[0].read_text(encoding="utf-8"))
    except Exception:
        return
    print(
        f"[human-rights] active feature {fid} | mode {st.get('mode') or 'unclassified'} | state {st.get('state')}. "
        f"To continue, run `/hrs:resume {'-'.join(fid.split('-')[:2])}` so stored state is reconciled "
        "with the real git/GitHub state first. Approvals, flags, manual test results and unblocking are human "
        "decisions: act on them only from the human's own chat message, through `hr ... --quote`."
    )


if __name__ == "__main__":
    main()
