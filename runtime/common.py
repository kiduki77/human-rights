from __future__ import annotations

import datetime
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = 1
WORKFLOW_DIRNAME = ".human-rights"
LEGACY_DIRNAME = ".workflow"
EXCLUDED_DIRS = (WORKFLOW_DIRNAME, LEGACY_DIRNAME)
EXCLUDE_SPECS = tuple(f":(exclude){d}" for d in EXCLUDED_DIRS)


class HRError(Exception):
    pass


class GateError(HRError):
    pass


def now() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return sha256_bytes(data)


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HRError(f"failed to parse JSON: {path} ({exc})")


def write_json_atomic(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def git(cwd: Path, *args: str) -> Optional[str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", errors="replace").strip()


def find_repo_root(start: Path) -> Path:
    top = git(start, "rev-parse", "--show-toplevel")
    if top:
        return Path(top)
    cur = start.resolve()
    for cand in [cur, *cur.parents]:
        if any((cand / d).is_dir() for d in EXCLUDED_DIRS):
            return cand
    return cur


def is_git_repo(root: Path) -> bool:
    return git(root, "rev-parse", "--is-inside-work-tree") == "true"


def head_sha(root: Path) -> Optional[str]:
    return git(root, "rev-parse", "--verify", "-q", "HEAD")


def current_branch(root: Path) -> Optional[str]:
    return git(root, "rev-parse", "--abbrev-ref", "HEAD")


def code_tree(root: Path) -> Optional[str]:
    listing = git(root, "ls-tree", "HEAD")
    if listing is None:
        return None
    kept = [ln for ln in listing.splitlines() if ln.split("\t", 1)[-1] not in EXCLUDED_DIRS]
    return sha256_bytes("\n".join(kept).encode("utf-8"))


def dirty_paths(root: Path) -> List[str]:
    out = git(root, "status", "--porcelain", "--untracked-files=all", "--", ".", *EXCLUDE_SPECS)
    if not out:
        return []
    return [ln[3:] for ln in out.splitlines() if ln.strip()]


def worktree_hash(root: Path) -> str:
    h = hashlib.sha256()
    try:
        diff = subprocess.run(
            ["git", "diff", "HEAD", "--binary", "--", ".", *EXCLUDE_SPECS],
            cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        ).stdout
    except FileNotFoundError:
        diff = b""
    h.update(diff)
    others = git(root, "ls-files", "--others", "--exclude-standard", "--", ".", *EXCLUDE_SPECS) or ""
    for rel in sorted(x for x in others.splitlines() if x):
        h.update(b"\0" + rel.encode("utf-8") + b"\0")
        p = root / rel
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


def fingerprint(root: Path) -> Dict[str, Any]:
    if not is_git_repo(root) or head_sha(root) is None:
        return {"git": False, "commit_sha": None, "code_tree": None, "dirty": None, "dirty_paths": [],
                "worktree_hash": None, "root": str(root)}
    dirty = dirty_paths(root)
    return {
        "git": True,
        "root": str(root),
        "commit_sha": head_sha(root),
        "code_tree": code_tree(root),
        "dirty": bool(dirty),
        "dirty_paths": dirty[:20],
        "worktree_hash": worktree_hash(root) if dirty else None,
    }


_CHANGED_CACHE: Dict[Tuple[str, str, str], Optional[List[str]]] = {}


def changed_files_since(root: Path, sha: str, head: Optional[str]) -> Optional[List[str]]:
    if not sha or not head:
        return None
    key = (str(root), sha, head)
    if key not in _CHANGED_CACHE:
        if sha == head:
            _CHANGED_CACHE[key] = []
        elif git(root, "merge-base", "--is-ancestor", sha, head) is None:
            _CHANGED_CACHE[key] = None
        else:
            out = git(root, "diff", "--name-only", sha, head, "--", ".", *EXCLUDE_SPECS)
            _CHANGED_CACHE[key] = None if out is None else [x for x in out.splitlines() if x.strip()]
    return _CHANGED_CACHE[key]


def path_matches(path: str, patterns: List[str]) -> bool:
    import fnmatch

    path = path.replace("\\", "/")
    for pat in patterns:
        pat = pat.replace("\\", "/").rstrip("/")
        if path == pat or path.startswith(pat + "/") or fnmatch.fnmatch(path, pat):
            return True
    return False


def run_shell(command: str, cwd: Path, timeout: int) -> Tuple[int, bytes, float]:
    import time

    start = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, time.monotonic() - start
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or b""
        return 124, out + f"\n[human-rights] timeout after {timeout}s\n".encode(), time.monotonic() - start
