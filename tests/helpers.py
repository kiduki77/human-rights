from __future__ import annotations

import contextlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN))

from runtime import human
from runtime.cli import main

human.at_terminal = lambda: True

EXAMPLE = Path(__file__).resolve().parent / "fixtures" / "FEAT-001-multi-drone"
PY = f'"{sys.executable}"'
PASS_CMD = f'{PY} -c "import sys; sys.exit(0)"'
FAIL_CMD = f'{PY} -c "import sys; print(\'boom\'); sys.exit(1)"'


@contextlib.contextmanager
def no_terminal():
    before = human.at_terminal
    human.at_terminal = lambda: False
    try:
        yield
    finally:
        human.at_terminal = before


def git(root: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return out.stdout.decode().strip()


class Repo:
    def __init__(self, use_git: bool = True):
        self.root = Path(tempfile.mkdtemp(prefix="hr-test-"))
        if use_git:
            git(self.root, "init", "-q")
            git(self.root, "config", "user.email", "test@example.com")
            git(self.root, "config", "user.name", "test")
            git(self.root, "config", "commit.gpgsign", "false")
            self.write("src/app.py", "print('hello')\n")
            self.commit("initial")

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, rel: str, text: str) -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def floor(self, text: str) -> None:
        from runtime.routing import floor
        from runtime.state.store import Workspace

        self.write(".human-rights/floor.yaml", text)
        ws = Workspace(self.root)
        floor.seal(ws, floor.load(ws), {"by": "owner", "via": "cli"})

    def commit(self, msg: str) -> str:
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", msg, "--allow-empty")
        return git(self.root, "rev-parse", "HEAD")

    def hr(self, *argv: str, stdin: str = None):
        out, err = io.StringIO(), io.StringIO()
        old_stdin = sys.stdin
        if stdin is not None:
            sys.stdin = io.StringIO(stdin)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main(["--root", str(self.root), *argv])
        finally:
            sys.stdin = old_stdin
        return code, out.getvalue() + err.getvalue()

    def say(self, text: str) -> str:
        payload = json.dumps({"prompt": text, "cwd": str(self.root), "session_id": "test"}).encode("utf-8")
        proc = subprocess.run([sys.executable, str(PLUGIN / "hooks" / "prompt_capture.py")], input=payload,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return proc.stdout.decode("utf-8")

    def feature_dir(self, fid: str = "FEAT-001") -> Path:
        num = fid.split("-")[1]
        pattern = re.compile(r"^(FEAT|GRP)-" + num + r"(-|$)")
        found = [p for p in (self.root / ".human-rights").glob(f"**/*-{num}*") if p.is_dir() and pattern.match(p.name)]
        return sorted(found, key=lambda p: len(p.parts))[0]

    def state(self, fid: str = "FEAT-001") -> dict:
        return json.loads((self.feature_dir(fid) / ".internal" / "state.json").read_text(encoding="utf-8"))


L0_AXES = json.dumps({k: {"score": 0, "basis": "probe: LoginCard.css only", "confirmed": True, "confidence": "high"}
                      for k in ("ambiguity", "scope", "architecture", "risk", "verification", "dependency")})

L3_AXES = json.dumps({
    "ambiguity": {"score": 3, "basis": "policies undecided", "confirmed": False, "confidence": "high"},
    "scope": {"score": 3, "basis": "link, command, ui", "confirmed": True, "confidence": "high"},
    "architecture": {"score": 3, "basis": "global connection -> sessions", "confirmed": True, "confidence": "high"},
    "risk": {"score": 3, "basis": "wrong target flies wrong vehicle", "confirmed": True, "confidence": "high"},
    "verification": {"score": 2, "basis": "SITL", "confirmed": False, "confidence": "medium"},
    "dependency": {"score": 2, "basis": "registry -> router -> ui", "confirmed": True, "confidence": "medium"},
})


def install_example_plan(repo: Repo, fail_tests=()) -> Path:
    fdir = repo.feature_dir()
    for name in ("requirements.json", "task-graph.json"):
        shutil.copy(EXAMPLE / ".internal" / name, fdir / ".internal" / name)
    plan = json.loads((EXAMPLE / ".internal" / "test-plan.json").read_text(encoding="utf-8"))
    for t in plan["tests"]:
        if t.get("command"):
            t["command"] = FAIL_CMD if t["id"] in fail_tests else PASS_CMD
    (fdir / ".internal" / "test-plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    for name in ("overview.md", "requirements.md", "design.md", "verification.md"):
        shutil.copy(EXAMPLE / name, fdir / name)
    for sub in ("tasks", "details"):
        for p in (EXAMPLE / sub).glob("*.md"):
            shutil.copy(p, fdir / sub / p.name)
    return fdir

ONE = ("--size", "single", "--size-reason", "one change, verified as a whole")
