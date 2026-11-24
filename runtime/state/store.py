from __future__ import annotations

import contextlib
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from runtime.common import (
    LEGACY_DIRNAME,
    SCHEMA_VERSION,
    WORKFLOW_DIRNAME,
    HRError,
    canonical,
    now,
    read_json,
    sha256_bytes,
    write_json_atomic,
    write_text_atomic,
)
from runtime.config import DEFAULT_CONFIG_TEXT, load_config

RUNTIME_DIR = Path(__file__).resolve().parents[1]
HR_ENTRY = RUNTIME_DIR / "hr.py"

GITIGNORE = """\
hr
hr.cmd
*.lock
.local/
**/.internal/logs/
**/.internal/cache/
**/evidence/
"""

GITIGNORE_REQUIRED = (".local/", "**/.internal/logs/", "**/.internal/cache/", "**/evidence/")

INTERNAL_FILES = {
    "state": "state.json",
    "requirements": "requirements.json",
    "task_graph": "task-graph.json",
    "test_plan": "test-plan.json",
    "test_results": "test-results.json",
    "failures": "failures.json",
    "findings": "findings.json",
    "split": "split.json",
}

LOCK_STALE_AFTER = 30
LOCK_HEARTBEAT = 5

FEATURE_PREFIX = "FEAT"
GROUP_PREFIX = "GRP"
CONTAINERS = {FEATURE_PREFIX: "features", GROUP_PREFIX: "groups"}
FEATURE_ID_RE = re.compile(r"^(FEAT|GRP)-(\d{3,})(?:-[a-z0-9][a-z0-9-]*)?$")


def id_prefix(fid: str) -> str:
    m = FEATURE_ID_RE.match(fid)
    return m.group(1) if m else FEATURE_PREFIX


def id_number(fid: str) -> int:
    m = FEATURE_ID_RE.match(fid)
    return int(m.group(2)) if m else 0


def with_prefix(fid: str, prefix: str) -> str:
    return prefix + fid[len(id_prefix(fid)):]


def id_order(fid: str):
    return (id_number(fid), fid)


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:40].strip("-") or "feature"


class Workspace:
    def __init__(self, root: Path):
        self.root = root
        self.wf = root / WORKFLOW_DIRNAME
        self.features_dir = self.wf / "features"
        self.groups_dir = self.wf / "groups"
        self.config_path = self.wf / "config.yaml"
        self.active_path = self.wf / "active.json"

    @property
    def initialized(self) -> bool:
        return self.config_path.exists()

    @property
    def legacy(self) -> Optional[Path]:
        old = self.root / LEGACY_DIRNAME
        if self.wf.exists() or not (old / "config.yaml").is_file():
            return None
        text = (old / "config.yaml").read_text(encoding="utf-8", errors="replace")
        return old if "redpill:" in text or "routing:" in text else None

    def require_init(self) -> None:
        if not self.initialized:
            if self.legacy:
                raise HRError(f"found the old {LEGACY_DIRNAME}/ workspace. Run `hr init` (or /hrs:init) to move it "
                              f"to {WORKFLOW_DIRNAME}/.")
            raise HRError(f"{self.wf} not found. Run `hr init` first.")

    def config(self) -> Dict[str, Any]:
        return load_config(self.config_path)

    def init(self) -> List[str]:
        created = []
        old = self.legacy
        if old:
            old.rename(self.wf)
            created.append(f"{self.wf} (moved from {old.name}/)")
        self.features_dir.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists():
            write_text_atomic(self.config_path, DEFAULT_CONFIG_TEXT)
            created.append(str(self.config_path))
        gi = self.wf / ".gitignore"
        if not gi.exists():
            write_text_atomic(gi, GITIGNORE)
            created.append(str(gi))
        self.ensure_wrappers()
        return created

    def ensure_wrappers(self) -> None:
        if not self.wf.is_dir():
            return
        gi = self.wf / ".gitignore"
        if gi.exists():
            text = gi.read_text(encoding="utf-8")
            missing = [line for line in GITIGNORE_REQUIRED if line not in text.splitlines()]
            if missing:
                write_text_atomic(gi, text.rstrip("\n") + "\n" + "\n".join(missing) + "\n")
        entry = HR_ENTRY.as_posix()
        sh = (
            "#!/bin/sh\n"
            "PY=python3\n"
            "command -v python3 >/dev/null 2>&1 || PY=python\n"
            f'exec "$PY" "{entry}" "$@"\n'
        )
        cmd = "@echo off\r\n" f'python "{HR_ENTRY}" %*\r\n'
        for path, text in ((self.wf / "hr", sh), (self.wf / "hr.cmd", cmd)):
            if not path.exists() or path.read_text(encoding="utf-8", errors="replace") != text:
                with open(path, "w", encoding="utf-8", newline="") as fh:
                    fh.write(text)
        try:
            os.chmod(self.wf / "hr", 0o755)
        except OSError:
            pass

    def locations(self) -> Dict[str, Path]:
        found: Dict[str, Path] = {}

        def walk(base: Path) -> None:
            for sub in CONTAINERS.values():
                holder = base / sub
                if not holder.is_dir():
                    continue
                for p in sorted(holder.iterdir()):
                    if p.is_dir() and FEATURE_ID_RE.match(p.name):
                        found.setdefault(p.name, p)
                        walk(p)

        walk(self.wf)
        return found

    def dir_of(self, fid: str) -> Path:
        return self.locations().get(fid) or self.wf / CONTAINERS[id_prefix(fid)] / fid

    def list_features(self) -> List[str]:
        return sorted(self.locations(), key=id_order)

    def next_feature_id(self, slug: str) -> str:
        nums = [id_number(f) for f in self.list_features()]
        return f"{FEATURE_PREFIX}-{(max(nums) + 1 if nums else 1):03d}-{slugify(slug)}"

    def active_feature_id(self) -> Optional[str]:
        data = read_json(self.active_path, {}) or {}
        return data.get("feature_id")

    def set_active(self, fid: Optional[str]) -> None:
        write_json_atomic(self.active_path, {"feature_id": fid, "updated_at": now()})

    def resolve(self, fid: Optional[str]) -> "Feature":
        self.require_init()
        if not fid:
            fid = self.active_feature_id()
            if not fid:
                raise HRError("No active feature. Pass `-f FEAT-NNN` or `-f GRP-NNN`.")
        known = self.list_features()
        matches = [f for f in known if f == fid or f.startswith(fid + "-")]
        if not matches and FEATURE_ID_RE.match(fid):
            matches = [f for f in known if id_number(f) == id_number(fid)]
        if len(matches) != 1:
            raise HRError(f"Feature not found or ambiguous: {fid} (known: {', '.join(self.list_features()) or 'none'})")
        return Feature(self, matches[0])

    @contextlib.contextmanager
    def lock(self, timeout: float = 30.0) -> Iterator[None]:
        import threading

        path = self.wf / "state.lock"
        deadline = time.monotonic() + timeout
        while True:
            try:
                fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, f"{os.getpid()} {now()}".encode())
                os.close(fd)
                break
            except FileExistsError:
                try:
                    if time.time() - path.stat().st_mtime > LOCK_STALE_AFTER:
                        path.unlink()
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() > deadline:
                    raise HRError(f"Could not acquire state lock: {path} (is another hr process running?)")
                time.sleep(0.1)
        stop = threading.Event()

        def heartbeat() -> None:
            while not stop.wait(LOCK_HEARTBEAT):
                with contextlib.suppress(OSError):
                    os.utime(str(path), None)

        beat = threading.Thread(target=heartbeat, daemon=True)
        beat.start()
        try:
            yield
        finally:
            stop.set()
            beat.join(timeout=2)
            with contextlib.suppress(FileNotFoundError):
                path.unlink()


class Feature:
    def __init__(self, ws: Workspace, fid: str, directory: Optional[Path] = None):
        self.ws = ws
        self.bind(fid, directory or ws.dir_of(fid))

    def bind(self, fid: str, directory: Path) -> None:
        self.id = fid
        self.dir = directory
        self.internal = self.dir / ".internal"
        self.events_path = self.internal / "events.jsonl"
        self.logs_dir = self.internal / "logs"

    def child_dir(self, fid: str) -> Path:
        return self.dir / CONTAINERS[id_prefix(fid)] / fid

    def relocate(self, new_id: str, new_dir: Path) -> None:
        ws = self.ws
        old_id, old_dir = self.id, self.dir
        if new_dir == old_dir and new_id == old_id:
            return
        if new_dir.exists():
            raise HRError(f"cannot move {old_id}: {new_dir} already exists")
        old_rel = old_dir.relative_to(ws.root).as_posix() + "/"
        new_rel = new_dir.relative_to(ws.root).as_posix() + "/"
        new_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            old_dir.rename(new_dir)
        except OSError as exc:
            raise HRError(f"cannot move {old_dir} to {new_dir}: {exc} (close anything that has files open there)")
        self.bind(new_id, new_dir)
        for path in new_dir.rglob("*.json"):
            if path.parent.name != ".internal":
                continue
            text = path.read_text(encoding="utf-8")
            if old_rel in text:
                write_text_atomic(path, text.replace(old_rel, new_rel))
        if new_id == old_id:
            self.emit("moved", **{"from": old_rel.rstrip("/"), "to": new_rel.rstrip("/")})
            return
        st = self.state()
        st["feature_id"] = new_id
        self.save_state(st)
        for other in ws.list_features():
            if other == new_id:
                continue
            ofeat = Feature(ws, other)
            ost = ofeat.load("state")
            if not ost:
                continue
            changed = False
            if ost.get("parent") == old_id:
                ost["parent"] = new_id
                changed = True
            for link in ost.get("children") or []:
                if link.get("feature_id") == old_id:
                    link["feature_id"] = new_id
                    changed = True
            if changed:
                ofeat.save("state", ost)
        if ws.active_feature_id() == old_id:
            ws.set_active(new_id)
        self.emit("renamed", **{"from": old_id, "to": new_id, "path": new_rel.rstrip("/")})

    def path(self, key: str) -> Path:
        return self.internal / INTERNAL_FILES[key]

    def load(self, key: str, default: Any = None) -> Any:
        return read_json(self.path(key), default)

    def save(self, key: str, obj: Any) -> None:
        write_json_atomic(self.path(key), obj)

    def state(self) -> Dict[str, Any]:
        st = self.load("state")
        if st is None:
            raise HRError(f"{self.id}: state.json is missing.")
        return st

    def save_state(self, st: Dict[str, Any]) -> None:
        st["updated_at"] = now()
        self.save("state", st)

    def requirements(self) -> Dict[str, Any]:
        return self.load("requirements", {}) or {}

    def task_graph(self) -> Dict[str, Any]:
        return self.load("task_graph", {"tasks": []}) or {"tasks": []}

    def test_plan(self) -> Dict[str, Any]:
        return self.load("test_plan", {"tests": []}) or {"tests": []}

    def test_results(self) -> Dict[str, Any]:
        return self.load("test_results", {"runs": []}) or {"runs": []}

    def failures(self) -> Dict[str, Any]:
        return self.load("failures", {"failures": []}) or {"failures": []}


    def events(self) -> List[Dict[str, Any]]:
        import json

        if not self.events_path.exists():
            return []
        out = []
        for i, line in enumerate(self.events_path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    out.append({"seq": None, "event": "__corrupt__", "line": i})
        return out

    def emit(self, event: str, **data: Any) -> Dict[str, Any]:
        import json

        prev = self.events()
        record: Dict[str, Any] = {
            "seq": len(prev) + 1,
            "event": event,
            "feature_id": self.id,
            "timestamp": now(),
            "actor": data.pop("actor", "runtime"),
        }
        record.update(data)
        record["prev_hash"] = prev[-1].get("hash") if prev else None
        record["hash"] = sha256_bytes(canonical(record))
        self.internal.mkdir(parents=True, exist_ok=True)
        with open(self.events_path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return record

    def verify_chain(self) -> List[str]:
        problems = []
        prev_hash = None
        for i, ev in enumerate(self.events(), 1):
            if ev.get("event") == "__corrupt__":
                problems.append(f"events.jsonl line {ev['line']}: corrupt JSON")
                prev_hash = None
                continue
            body = {k: v for k, v in ev.items() if k != "hash"}
            if ev.get("seq") != i:
                problems.append(f"event #{i}: seq mismatch ({ev.get('seq')})")
            if ev.get("prev_hash") != prev_hash:
                problems.append(f"event #{i}: prev_hash mismatch (event deleted or inserted?)")
            if sha256_bytes(canonical(body)) != ev.get("hash"):
                problems.append(f"event #{i} ({ev.get('event')}): hash mismatch (event edited?)")
            prev_hash = ev.get("hash")
        return problems


def new_state(fid: str, title: str, request: str) -> Dict[str, Any]:
    ts = now()
    return {
        "schema_version": SCHEMA_VERSION,
        "feature_id": fid,
        "title": title,
        "request": request,
        "created_at": ts,
        "updated_at": ts,
        "state": "created",
        "state_before_block": None,
        "block_reason": None,
        "block_kind": None,
        "kind": "feature",
        "parent": None,
        "size": None,
        "mode": None,
        "mode_history": [],
        "routing": None,
        "required_gates": {"design": False, "final": False},
        "gate_reasons": [],
        "approvals": {"design": None, "final": None, "split": None},
        "children": [],
        "invalidated_approvals": [],
        "git": {"branch": None, "base_sha": None, "last_seen_head": None},
        "github": {"feature_issue": None, "task_issues": {}, "prs": {}, "commits": {}, "last_synced_at": None},
        "parallel": {"integration_branch": None, "worktrees": {}, "batches": []},
    }
