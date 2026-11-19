from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime.common import GateError, HRError, current_branch, dirty_paths, fingerprint, git, head_sha, now
from runtime.state.store import Feature


def _par(st: Dict[str, Any]) -> Dict[str, Any]:
    return st.setdefault("parallel", {"integration_branch": None, "worktrees": {}, "batches": []})


def worktree_root(feature: Feature) -> Path:
    cfg = feature.ws.config().get("scheduler", {})
    root = feature.ws.root
    if cfg.get("worktree_root"):
        p = Path(cfg["worktree_root"])
        return p if p.is_absolute() else (root / p).resolve()
    return root.parent / f"{root.name}.hr-worktrees"


def active(st: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {k: v for k, v in _par(st)["worktrees"].items() if v.get("status") == "active"}


def code_root(feature: Feature, st: Dict[str, Any], task_id: Optional[str]) -> Path:
    if task_id:
        wt = _par(st)["worktrees"].get(task_id)
        if wt and wt.get("status") == "active":
            return Path(wt["path"])
    return feature.ws.root


def _git_raw(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _task(feature: Feature, task_id: str) -> Dict[str, Any]:
    for t in feature.task_graph().get("tasks", []):
        if t["id"] == task_id:
            return t
    raise HRError(f"no such task: {task_id}")


def create(feature: Feature, st: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    from runtime.scheduler.dag import dep_done

    root = feature.ws.root
    if st["state"] != "executing":
        raise GateError(f"worktrees are created only in executing (current: {st['state']})")
    if not fingerprint(root)["git"]:
        raise GateError("worktrees need a git repository with at least one commit")
    par = _par(st)
    if par["worktrees"].get(task_id, {}).get("status") == "active":
        raise GateError(f"{task_id} already has an active worktree: {par['worktrees'][task_id]['path']}")
    task = _task(feature, task_id)
    if task.get("status", "planned") not in ("planned", "rework_required"):
        raise GateError(f"{task_id} is {task.get('status')}; only planned / rework_required tasks get a worktree")
    tasks = {t["id"]: t for t in feature.task_graph().get("tasks", [])}
    pending = [d for d in task.get("depends_on", []) if d in tasks and not dep_done(tasks[d], par["worktrees"])]
    if pending:
        raise GateError(f"{task_id} depends on tasks not yet verified and merged: {', '.join(pending)}")
    dirty = dirty_paths(root)
    if dirty:
        raise GateError("the integration checkout has uncommitted code changes; commit them first so the "
                        "worktree starts from a known version: " + ", ".join(dirty[:5]))
    branch_now = current_branch(root)
    if not branch_now or branch_now == "HEAD":
        raise GateError("the main checkout is on a detached HEAD; check out the feature's integration branch")
    if par.get("integration_branch") and par["integration_branch"] != branch_now:
        raise GateError(f"integration branch is {par['integration_branch']} but the main checkout is on {branch_now}")
    par["integration_branch"] = branch_now

    base = head_sha(root)
    branch = f"hr/{feature.id}/{task_id}"
    path = worktree_root(feature) / feature.id / task_id
    if path.exists():
        raise GateError(f"worktree path already exists: {path} (remove it or run `hr worktree remove`)")
    path.parent.mkdir(parents=True, exist_ok=True)
    if git(root, "rev-parse", "--verify", "-q", f"refs/heads/{branch}"):
        proc = _git_raw(root, "worktree", "add", str(path), branch)
    else:
        proc = _git_raw(root, "worktree", "add", "-b", branch, str(path), base)
    if proc.returncode != 0:
        raise HRError("git worktree add failed: " + proc.stderr.decode(errors="replace").strip())
    rec = {"task_id": task_id, "path": str(path), "branch": branch, "base_sha": base,
           "integration_branch": branch_now, "status": "active", "created_at": now()}
    par["worktrees"][task_id] = rec
    prev = task.get("status", "planned")
    _set_task_status(feature, task_id, "in_progress")
    feature.emit("worktree_created", task_id=task_id, branch=branch, base_sha=base, path=str(path))
    feature.emit("task_status", task_id=task_id, **{"from": prev, "to": "in_progress"}, note="worktree created")
    return rec


def _set_task_status(feature: Feature, task_id: str, status: str) -> None:
    graph = feature.task_graph()
    for t in graph.get("tasks", []):
        if t["id"] == task_id:
            t["status"] = status
    feature.save("task_graph", graph)


def merge(feature: Feature, st: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    from runtime.scheduler.dag import dep_done

    root = feature.ws.root
    par = _par(st)
    rec = par["worktrees"].get(task_id)
    if not rec or rec.get("status") != "active":
        raise GateError(f"{task_id} has no active worktree")
    task = _task(feature, task_id)
    wpath = Path(rec["path"])
    if task.get("status") != "verified":
        raise GateError(f"{task_id} must be verified in its worktree before merging (current: {task.get('status')})")
    wfp = fingerprint(wpath)
    if wfp["dirty"]:
        raise GateError(f"{task_id} worktree has uncommitted changes: " + ", ".join(wfp["dirty_paths"][:5]))
    if (task.get("verified_evidence") or {}).get("code_tree") != wfp["code_tree"]:
        raise GateError(f"{task_id} changed after it was verified; re-run `hr verify --task {task_id}` and re-verify")
    tasks = {t["id"]: t for t in feature.task_graph().get("tasks", [])}
    pending = [d for d in task.get("depends_on", []) if d in tasks and not dep_done(tasks[d], par["worktrees"])]
    if pending:
        raise GateError(f"merge dependencies first (dependent work is never merged in parallel): {', '.join(pending)}")
    if current_branch(root) != rec["integration_branch"]:
        raise GateError(f"main checkout must be on {rec['integration_branch']} (is on {current_branch(root)})")
    dirty = dirty_paths(root)
    if dirty:
        raise GateError("integration checkout has uncommitted code changes: " + ", ".join(dirty[:5]))

    before = head_sha(root)
    proc = _git_raw(root, "merge", "--no-ff", "--no-edit", "-m", f"{feature.id} {task_id}: merge {rec['branch']}",
                    rec["branch"])
    if proc.returncode != 0:
        conflicted = (git(root, "diff", "--name-only", "--diff-filter=U") or "").splitlines()
        _git_raw(root, "merge", "--abort")
        rec["status_note"] = "merge conflict: " + ", ".join(conflicted)
        _set_task_status(feature, task_id, "rework_required")
        feature.emit("worktree_merge_conflict", task_id=task_id, files=conflicted, base=before)
        feature.save_state(st)
        raise GateError(
            f"{task_id} conflicts with the integration branch ({', '.join(conflicted) or 'see git output'}). "
            "The merge was aborted and the integration branch is unchanged. The task is now rework_required: "
            "rebase or fix it in its worktree, re-verify, and merge again. If the conflict means the task "
            "boundaries were wrong, re-plan (it should not have been scheduled in parallel)."
        )
    rec.update(status="merged", merged_at=now(), merged_into=head_sha(root), merged_from=wfp["commit_sha"])
    feature.emit("worktree_merged", task_id=task_id, branch=rec["branch"], merge_sha=rec["merged_into"],
                 task_commit=wfp["commit_sha"])
    return rec


def remove(feature: Feature, st: Dict[str, Any], task_id: str, force: bool) -> Dict[str, Any]:
    root = feature.ws.root
    rec = _par(st)["worktrees"].get(task_id)
    if not rec:
        raise HRError(f"{task_id} has no worktree record")
    if rec["status"] == "active" and not force:
        raise GateError(f"{task_id} is not merged yet; use --force to discard the worktree (the branch is kept)")
    if Path(rec["path"]).exists():
        proc = _git_raw(root, "worktree", "remove", *(["--force"] if force else []), rec["path"])
        if proc.returncode != 0:
            raise HRError("git worktree remove failed: " + proc.stderr.decode(errors="replace").strip())
    if rec["status"] == "merged":
        _git_raw(root, "branch", "-d", rec["branch"])
    else:
        _set_task_status(feature, task_id, "rework_required")
    rec["status"] = "removed" if rec["status"] == "merged" else "discarded"
    rec["removed_at"] = now()
    feature.emit("worktree_removed", task_id=task_id, outcome=rec["status"])
    return rec


def brief(feature: Feature, st: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    task = _task(feature, task_id)
    rec = _par(st)["worktrees"].get(task_id) or {}
    tests = {t["id"]: t for t in feature.test_plan().get("tests", [])}
    reqs = {r["id"]: r for r in feature.requirements().get("requirements", [])}
    checks = [{"id": v, "command": tests.get(v, {}).get("command"), "pass_criteria": tests.get(v, {}).get("pass_criteria")}
              for v in task.get("verification", [])]
    doc = feature.dir / "tasks" / f"{task_id}.md"
    lines = [
        f"You are implementing {task_id} of {feature.id} ({task.get('title', '')}) in an isolated git worktree.",
        "",
        f"Worktree: {rec.get('path')}",
        f"Branch:   {rec.get('branch')} (based on {str(rec.get('base_sha'))[:10]})",
        "",
        f"Purpose: {task.get('purpose')}",
        "Requirements served: " + "; ".join(f"{r}: {reqs.get(r, {}).get('text', '')}" for r in task.get("requirement_ids", [])),
        "Acceptance criteria:",
        *[f"  - {a['id']}: {a['text']}" for a in task.get("acceptance_criteria", [])],
        "You may change only: " + ", ".join((task.get("scope") or {}).get("paths", [])),
        "Contracts: provides " + (", ".join((task.get("contracts") or {}).get("provides", [])) or "none")
        + "; consumes " + (", ".join((task.get("contracts") or {}).get("consumes", [])) or "none"),
        "Checks that must pass (run them yourself inside the worktree while iterating):",
        *[f"  - {c['id']}: {c['command'] or '(manual)'}  -> {c['pass_criteria']}" for c in checks],
        "",
        "Rules:",
        "  - Work only inside the worktree path above. Never touch the main checkout.",
        "  - Never edit anything under .human-rights/ and never run the hr command; the coordinator records state.",
        "  - If the task needs a change outside the allowed paths or a contract change, stop and report it as a "
        "scope change instead of making it.",
        f"  - Commit your work on the branch with a message starting with '{feature.id} {task_id}'. Leave no uncommitted changes.",
        "  - Report back: commit SHA, what changed (2-3 lines), check results you saw, and anything unresolved.",
        "    Your own test output is a hint only; the coordinator re-runs the checks and records the evidence.",
    ]
    if doc.exists():
        lines += ["", f"Task document: {doc}"]
    return {"task_id": task_id, "worktree": rec.get("path"), "branch": rec.get("branch"),
            "checks": checks, "prompt": "\n".join(lines)}
