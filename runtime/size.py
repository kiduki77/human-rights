from __future__ import annotations

import fnmatch
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from runtime.common import EXCLUDE_SPECS, fingerprint, git, path_matches
from runtime.config import DEFAULTS
from runtime.state.store import Feature

Files = Dict[str, Tuple[str, int, int]]
KINDS = ("code", "tests", "locks")
PEP508 = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9_.\-]*)")


@lru_cache(maxsize=None)
def _glob(pattern: str) -> "re.Pattern[str]":
    pattern = pattern.replace("\\", "/")
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + r"\Z")


def matches(path: str, patterns: List[str]) -> bool:
    path = path.replace("\\", "/")
    base = path.rsplit("/", 1)[-1]
    for pat in patterns:
        if "/" in pat:
            if _glob(pat).match(path):
                return True
        elif fnmatch.fnmatch(base, pat):
            return True
    return False


def settings(cfg: Dict[str, Any]) -> Dict[str, List[str]]:
    section = cfg.get("size") or {}
    out = {}
    for key in ("test_patterns", "manifests", "lockfiles"):
        raw = section.get(key, DEFAULTS["size"][key])
        out[key] = [str(x) for x in ([raw] if isinstance(raw, str) else raw or [])]
    return out


def _diff(root: Path, base: str, head: Optional[str]) -> Optional[Files]:
    ends = [head] if head else []
    tail = ["--", ".", *EXCLUDE_SPECS]
    status = git(root, "-c", "core.quotepath=false", "diff", "--name-status", "--no-renames", base, *ends, *tail)
    stats = git(root, "-c", "core.quotepath=false", "diff", "--numstat", "--no-renames", base, *ends, *tail)
    if status is None or stats is None:
        return None
    counts: Dict[str, Tuple[int, int]] = {}
    for line in stats.splitlines():
        a, _, rest = line.partition("\t")
        d, _, path = rest.partition("\t")
        counts[path.strip()] = (int(a) if a.isdigit() else 0, int(d) if d.isdigit() else 0)
    files: Files = {}
    for line in status.splitlines():
        code, _, path = line.partition("\t")
        if path.strip():
            files[path.strip()] = (code.strip()[:1], *counts.get(path.strip(), (0, 0)))
    if not head:
        others = git(root, "-c", "core.quotepath=false", "ls-files", "--others", "--exclude-standard", *tail) or ""
        for rel in (x for x in others.splitlines() if x.strip()):
            data = (root / rel).read_bytes() if (root / rel).is_file() else b""
            lines = 0 if b"\0" in data else data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
            files[rel.strip()] = ("A", lines, 0)
    return files


def _kind(path: str, cfg: Dict[str, List[str]]) -> str:
    if matches(path, cfg["lockfiles"]):
        return "locks"
    return "tests" if matches(path, cfg["test_patterns"]) else "code"


def tally(files: Files, cfg: Dict[str, List[str]]) -> Dict[str, Dict[str, int]]:
    out = {k: {"added": 0, "changed": 0, "deleted": 0, "plus": 0, "minus": 0} for k in KINDS}
    for path, (status, plus, minus) in files.items():
        row = out[_kind(path, cfg)]
        row["added" if status == "A" else "deleted" if status == "D" else "changed"] += 1
        row["plus"] += plus
        row["minus"] += minus
    return out


def _within(root: Path, older: str, newer: str) -> bool:
    return older == newer or git(root, "merge-base", "--is-ancestor", older, newer) is not None


def _depth(root: Path, sha: str) -> int:
    return int(git(root, "rev-list", "--count", sha) or 0)


def _ranges(feature: Feature, st: Dict[str, Any], base: str, head: str) -> Dict[str, Tuple[str, str]]:
    root = feature.ws.root
    recs = (st.get("parallel") or {}).get("worktrees") or {}
    done: Dict[str, Tuple[str, bool]] = {}
    for x in feature.task_graph().get("tasks", []):
        ev = x.get("verified_evidence") or {}
        sha = ev.get("commit_sha")
        if x.get("status") == "verified" and sha and _within(root, base, sha) and _within(root, sha, head):
            done[x["id"]] = (sha, bool(ev.get("worktree")) and bool((recs.get(x["id"]) or {}).get("base_sha")))
    marks = [base] + [sha for sha, own in done.values() if not own]
    marks += [r["merged_into"] for r in recs.values() if r.get("merged_into") and _within(root, r["merged_into"], head)]
    out: Dict[str, Tuple[str, str]] = {}
    for tid, (sha, own) in done.items():
        if own:
            start = recs[tid]["base_sha"]
        else:
            before = [m for m in marks if m != sha and _within(root, m, sha)]
            start = max(before, key=lambda m: _depth(root, m), default=base)
        if _within(root, start, sha):
            out[tid] = (start, sha)
    return out


def _attribute(feature: Feature, st: Dict[str, Any], base: str, head: str, total: Files,
               cfg: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    from runtime.verification.plan_check import topo_order

    graph = feature.task_graph()
    by_id = {x["id"]: x for x in graph.get("tasks", [])}
    ranges = _ranges(feature, st, base, head) if by_id else {}
    rows = []
    for tid in topo_order(graph) if by_id else []:
        x = by_id[tid]
        paths = [str(p) for p in (x.get("scope") or {}).get("paths") or []]
        files: Optional[Files] = None
        if tid in ranges:
            files = _diff(feature.ws.root, *ranges[tid])
            basis = "commits"
        if files is None:
            files = {p: v for p, v in total.items() if path_matches(p, paths)} if paths else {}
            basis = "scope" if paths else "none"
        rows.append({"id": tid, "purpose": x.get("purpose") or x.get("title") or "", "basis": basis,
                     "range": list(ranges[tid]) if basis == "commits" else None, "paths": sorted(files),
                     "size": tally(files, cfg)})
    return rows


def _load(text: Optional[str]) -> Any:
    try:
        return json.loads(text) if text else {}
    except ValueError:
        return {}


def _toml(text: Optional[str]) -> Dict[str, Any]:
    import tomllib

    try:
        return tomllib.loads(text or "")
    except ValueError:
        return {}


def _pep(items: Any) -> Set[str]:
    return {m.group(1).lower() for x in items or [] if isinstance(x, str) for m in [PEP508.match(x)] if m}


def _keys(table: Any, skip: Tuple[str, ...] = ()) -> Set[str]:
    return {k for k in table if k not in skip} if isinstance(table, dict) else set()


def _package_json(text: str) -> Set[str]:
    data = _load(text)
    return set().union(*[_keys(data.get(k)) for k in
                         ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")]) if data else set()


def _composer_json(text: str) -> Set[str]:
    data = _load(text)
    return {k for k in _keys(data.get("require")) | _keys(data.get("require-dev")) if k != "php" and not k.startswith("ext-")}


def _pyproject(text: str) -> Set[str]:
    data = _toml(text)
    proj = data.get("project") or {}
    poetry = (data.get("tool") or {}).get("poetry") or {}
    names = _pep(proj.get("dependencies"))
    for group in list((proj.get("optional-dependencies") or {}).values()) + list((data.get("dependency-groups") or {}).values()):
        names |= _pep(group)
    names |= {k.lower() for k in _keys(poetry.get("dependencies"), ("python",))}
    names |= {k.lower() for k in _keys(poetry.get("dev-dependencies"))}
    for group in (poetry.get("group") or {}).values():
        names |= {k.lower() for k in _keys((group or {}).get("dependencies"), ("python",))}
    return names


def _cargo(text: str) -> Set[str]:
    data = _toml(text)
    tables = [data.get(k) for k in ("dependencies", "dev-dependencies", "build-dependencies")]
    tables.append((data.get("workspace") or {}).get("dependencies"))
    for target in (data.get("target") or {}).values():
        tables += [(target or {}).get(k) for k in ("dependencies", "dev-dependencies", "build-dependencies")]
    return set().union(*[_keys(t) for t in tables])


def _pipfile(text: str) -> Set[str]:
    data = _toml(text)
    return {k.lower() for k in _keys(data.get("packages")) | _keys(data.get("dev-packages"))}


def _requirements(text: str) -> Set[str]:
    return _pep(x for x in text.splitlines() if x.strip() and not x.lstrip().startswith(("#", "-")))


def _gomod(text: str) -> Set[str]:
    names, block = set(), False
    for line in text.splitlines():
        line = line.split("//", 1)[0].strip()
        if block and line == ")":
            block = False
        elif line.startswith("require ("):
            block = True
        elif block or line.startswith("require "):
            parts = line.replace("require ", "", 1).split()
            if len(parts) >= 2 and parts[1].startswith("v"):
                names.add(parts[0])
    return names


def _pom(text: str) -> Set[str]:
    out = set()
    for body in re.findall(r"<dependency>(.*?)</dependency>", text, re.S):
        g = re.search(r"<groupId>\s*([^<\s]+)", body)
        a = re.search(r"<artifactId>\s*([^<\s]+)", body)
        if a:
            out.add(f"{g.group(1)}:{a.group(1)}" if g else a.group(1))
    return out


def _gradle(text: str) -> Set[str]:
    pat = r"\b(?:implementation|api|compileOnly|runtimeOnly|testImplementation|testRuntimeOnly|testCompileOnly|annotationProcessor|kapt|ksp|classpath)\s*\(?\s*['\"]([^'\"]+)['\"]"
    return {":".join(m.split(":")[:2]) for m in re.findall(pat, text)}


def _nuget(text: str) -> Set[str]:
    return set(re.findall(r"<(?:PackageReference|PackageVersion)\b[^>]*?\bInclude=\"([^\"]+)\"", text)) | set(
        re.findall(r"<package\b[^>]*?\bid=\"([^\"]+)\"", text))


def _gemfile(text: str) -> Set[str]:
    return set(re.findall(r"^\s*gem\s+['\"]([^'\"]+)['\"]", text, re.M))


def _package_lock(text: str) -> Set[str]:
    data = _load(text)
    names = {k.rsplit("node_modules/", 1)[-1] for k in _keys(data.get("packages")) if "node_modules/" in k}
    return names or _keys(data.get("dependencies"))


def _yarn_lock(text: str) -> Set[str]:
    out = set()
    for line in text.splitlines():
        if line and not line[0].isspace() and not line.startswith("#") and line.rstrip().endswith(":"):
            spec = line.rstrip()[:-1].split(",")[0].strip().strip("\"'")
            out.add(spec.rsplit("@", 1)[0] if "@" in spec[1:] else spec)
    return out


def _toml_packages(text: str) -> Set[str]:
    return set(re.findall(r"\[\[package\]\]\s*\r?\nname\s*=\s*\"([^\"]+)\"", text))


def _go_sum(text: str) -> Set[str]:
    return {line.split()[0] for line in text.splitlines() if line.strip()}


def _pipfile_lock(text: str) -> Set[str]:
    data = _load(text)
    return _keys(data.get("default")) | _keys(data.get("develop"))


def _composer_lock(text: str) -> Set[str]:
    data = _load(text)
    return {p.get("name") for k in ("packages", "packages-dev") for p in data.get(k) or [] if isinstance(p, dict) and p.get("name")}


def _gemfile_lock(text: str) -> Set[str]:
    return set(re.findall(r"^    (\S+) \(", text, re.M))


MANIFEST_READERS: List[Tuple[str, Callable[[str], Set[str]]]] = [
    ("package.json", _package_json), ("composer.json", _composer_json), ("pyproject.toml", _pyproject),
    ("Cargo.toml", _cargo), ("Pipfile", _pipfile), ("requirements*.txt", _requirements), ("go.mod", _gomod),
    ("pom.xml", _pom), ("build.gradle", _gradle), ("build.gradle.kts", _gradle), ("*.csproj", _nuget),
    ("*.props", _nuget), ("packages.config", _nuget), ("Gemfile", _gemfile),
]
LOCK_READERS: List[Tuple[str, Callable[[str], Set[str]]]] = [
    ("package-lock.json", _package_lock), ("yarn.lock", _yarn_lock), ("poetry.lock", _toml_packages),
    ("uv.lock", _toml_packages), ("Cargo.lock", _toml_packages), ("go.sum", _go_sum),
    ("Pipfile.lock", _pipfile_lock), ("composer.lock", _composer_lock), ("Gemfile.lock", _gemfile_lock),
]


def _reader(path: str, table: List[Tuple[str, Callable[[str], Set[str]]]]) -> Optional[Callable[[str], Set[str]]]:
    base = path.rsplit("/", 1)[-1]
    return next((fn for pat, fn in table if fnmatch.fnmatch(base, pat)), None)


def _names(root: Path, rev: Optional[str], path: str, fn: Callable[[str], Set[str]]) -> Set[str]:
    if rev:
        text = git(root, "show", f"{rev}:{path}")
    else:
        p = root / path
        text = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None
    return fn(text) if text else set()


def dependencies(root: Path, base: str, head: Optional[str], files: Files, cfg: Dict[str, List[str]]) -> Dict[str, Any]:
    added: List[Dict[str, str]] = []
    removed: List[Dict[str, str]] = []
    unread: List[str] = []
    locked = 0
    for path, (status, _, _) in sorted(files.items()):
        is_lock = matches(path, cfg["lockfiles"])
        if not is_lock and not matches(path, cfg["manifests"]):
            continue
        fn = _reader(path, LOCK_READERS if is_lock else MANIFEST_READERS)
        if fn is None:
            unread.append(path)
            continue
        try:
            before = set() if status == "A" else _names(root, base, path, fn)
            after = set() if status == "D" else _names(root, head, path, fn)
        except ImportError:
            unread.append(path)
            continue
        if is_lock:
            locked += len(after - before)
        else:
            added += [{"name": n, "file": path} for n in sorted(after - before)]
            removed += [{"name": n, "file": path} for n in sorted(before - after)]
    return {"added": added, "removed": removed, "locked": locked, "unread": unread}


def measure(feature: Feature) -> Optional[Dict[str, Any]]:
    st = feature.state()
    fp = fingerprint(feature.ws.root)
    base = (st.get("git") or {}).get("base_sha")
    if not fp.get("git") or not base:
        return None
    root = feature.ws.root
    head = None if fp.get("dirty") else fp["commit_sha"]
    total = _diff(root, base, head)
    if total is None:
        return None
    cfg = settings(feature.ws.config())
    tasks = [] if st.get("kind") == "group" or st.get("mode") in ("L0", "L1") else _attribute(
        feature, st, base, fp["commit_sha"], total, cfg)
    used: Set[str] = set()
    seen: Set[str] = set()
    for row in tasks:
        seen |= used & set(row["paths"])
        used |= set(row["paths"])
    outside = {p: v for p, v in total.items() if p not in used}
    return {"base": base, "head": fp["commit_sha"], "uncommitted": head is None, "total": tally(total, cfg),
            "dependencies": dependencies(root, base, head, total, cfg), "tasks": tasks,
            "outside": tally(outside, cfg) if tasks and outside else None, "overlap": bool(seen)}
