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
    wf = repo_root() / ".workflow"
    active = wf / "active.json"
    if not active.exists():
        return
    try:
        fid = json.loads(active.read_text(encoding="utf-8")).get("feature_id")
        if not fid:
            return
        st = json.loads((wf / "features" / fid / ".internal" / "state.json").read_text(encoding="utf-8"))
    except Exception:
        return
    print(
        f"[human-rights] active feature {fid} | mode {st.get('mode') or 'unclassified'} | state {st.get('state')}. "
        f"To continue, run `/human-rights resume {fid.split('-')[0]}-{fid.split('-')[1]}` so stored state is reconciled "
        "with the real git/GitHub state first. Approvals and manual test results are human-only."
    )


if __name__ == "__main__":
    main()
