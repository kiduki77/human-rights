from __future__ import annotations

import json
import subprocess
from typing import Any, Dict, List, Optional

from runtime.common import GateError, HRError, now
from runtime.state.store import Feature


def _gh(root, *args: str) -> Dict[str, Any]:
    try:
        proc = subprocess.run(["gh", *args], cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        return {"ok": False, "out": "", "err": "gh CLI is not installed"}
    return {
        "ok": proc.returncode == 0,
        "out": proc.stdout.decode("utf-8", errors="replace").strip(),
        "err": proc.stderr.decode("utf-8", errors="replace").strip(),
    }


def availability(feature: Feature) -> Dict[str, Any]:
    cfg = feature.ws.config().get("github", {})
    enabled = cfg.get("enabled", "auto")
    if enabled is False:
        return {"available": False, "reason": "config: github.enabled=false"}
    r = _gh(feature.ws.root, "auth", "status")
    if not r["ok"]:
        return {"available": False, "reason": "gh not authenticated or not installed: " + (r["err"] or r["out"])[:200]}
    r = _gh(feature.ws.root, "repo", "view", "--json", "nameWithOwner")
    if not r["ok"]:
        return {"available": False, "reason": "no GitHub remote repository found"}
    return {"available": True, "repo": json.loads(r["out"]).get("nameWithOwner")}


def _require(feature: Feature) -> None:
    av = availability(feature)
    if not av["available"]:
        raise GateError("GitHub unavailable - mark the issue/PR steps as manual: " + av["reason"])


def _issue_number(url: str) -> Optional[int]:
    tail = url.rstrip("/").rsplit("/", 1)[-1]
    return int(tail) if tail.isdigit() else None


def create_issues(feature: Feature, st: Dict[str, Any], dry_run: bool) -> List[Dict[str, Any]]:
    from runtime.approvals.gates import design_status

    if st["required_gates"].get("design") and not design_status(feature, st)["valid"]:
        raise GateError("issues are created only from an approved plan - no valid design approval")
    if not dry_run:
        _require(feature)
    root = feature.ws.root
    created = []
    gh_state = st["github"]
    overview = feature.dir / "overview.md"
    if not gh_state.get("feature_issue"):
        body = overview.read_text(encoding="utf-8") if overview.exists() else st["request"]
        body += f"\n\n---\nhuman-rights: `{feature.id}` (mode {st['mode']})"
        item = {"kind": "feature", "title": f"[{feature.id}] {st['title']}", "body": body}
        if not dry_run:
            r = _gh(root, "issue", "create", "--title", item["title"], "--body", body)
            if not r["ok"]:
                raise HRError("failed to create feature issue: " + r["err"])
            gh_state["feature_issue"] = {"number": _issue_number(r["out"]), "url": r["out"]}
            feature.emit("github_linked", kind="feature_issue", url=r["out"])
        created.append(item)
    parent = (gh_state.get("feature_issue") or {}).get("number")
    for t in feature.task_graph().get("tasks", []):
        if t["id"] in gh_state.get("task_issues", {}):
            continue
        doc = feature.dir / "tasks" / f"{t['id']}.md"
        body = doc.read_text(encoding="utf-8") if doc.exists() else t.get("purpose", "")
        if parent:
            body += f"\n\nParent: #{parent}"
        if t.get("depends_on"):
            body += "\nDepends on: " + ", ".join(t["depends_on"])
        item = {"kind": "task", "task": t["id"], "title": f"[{feature.id}/{t['id']}] {t.get('title', '')}", "body": body}
        if not dry_run:
            r = _gh(root, "issue", "create", "--title", item["title"], "--body", body)
            if not r["ok"]:
                raise HRError(f"failed to create issue for {t['id']}: " + r["err"])
            gh_state.setdefault("task_issues", {})[t["id"]] = {"number": _issue_number(r["out"]), "url": r["out"]}
            feature.emit("github_linked", kind="task_issue", task=t["id"], url=r["out"])
        created.append(item)
    return created


def link(feature: Feature, st: Dict[str, Any], task: Optional[str], issue: Optional[int], pr: Optional[int],
         commit: Optional[str]) -> None:
    key = task or "_feature"
    g = st["github"]
    if issue is not None:
        if task:
            g.setdefault("task_issues", {})[task] = {"number": issue}
        else:
            g["feature_issue"] = {"number": issue}
    if pr is not None:
        g.setdefault("prs", {})[key] = {"number": pr}
    if commit:
        g.setdefault("commits", {}).setdefault(key, [])
        if commit not in g["commits"][key]:
            g["commits"][key].append(commit)
    feature.emit("github_linked", task=task, issue=issue, pr=pr, commit=commit)


def pr_live(feature: Feature, number: int) -> Dict[str, Any]:
    r = _gh(feature.ws.root, "pr", "view", str(number), "--json",
            "number,state,isDraft,mergeable,reviewDecision,headRefOid,baseRefName,url,statusCheckRollup")
    if not r["ok"]:
        return {"number": number, "error": r["err"][:300]}
    data = json.loads(r["out"])
    checks = data.pop("statusCheckRollup", None) or []
    states = [(c.get("conclusion") or c.get("state") or "PENDING").upper() for c in checks]
    data["checks"] = {
        "total": len(states),
        "failing": sum(1 for s in states if s in ("FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED")),
        "pending": sum(1 for s in states if s in ("PENDING", "IN_PROGRESS", "QUEUED", "EXPECTED", "")),
    }
    return data


def sync(feature: Feature, st: Dict[str, Any]) -> Dict[str, Any]:
    _require(feature)
    live = {k: pr_live(feature, v["number"]) for k, v in st["github"].get("prs", {}).items()}
    st["github"]["last_synced_at"] = now()
    feature.emit("github_synced", prs=sorted(live))
    return live


def merge_check(feature: Feature, st: Dict[str, Any]) -> List[str]:
    from runtime.approvals.gates import final_status
    from runtime.common import head_sha

    problems = []
    if st["state"] != "ready_to_merge":
        problems.append(f"state is not ready_to_merge ({st['state']})")
    if st["required_gates"].get("final"):
        fs = final_status(feature, st)
        if not fs["valid"]:
            problems.append("no valid final approval: " + str(fs["reason"] or "not approved"))
    prs = st["github"].get("prs", {})
    if prs:
        av = availability(feature)
        if not av["available"]:
            problems.append("cannot check GitHub state: " + av["reason"])
        else:
            head = head_sha(feature.ws.root)
            for key, v in prs.items():
                d = pr_live(feature, v["number"])
                if "error" in d:
                    problems.append(f"PR #{v['number']}: lookup failed: {d['error']}")
                    continue
                if d.get("state") != "OPEN":
                    problems.append(f"PR #{d['number']} is {d.get('state')}")
                if d.get("isDraft"):
                    problems.append(f"PR #{d['number']} is a draft")
                if d["checks"]["failing"] or d["checks"]["pending"]:
                    problems.append(f"PR #{d['number']} CI: {d['checks']['failing']} failing, {d['checks']['pending']} pending")
                if d.get("mergeable") == "CONFLICTING":
                    problems.append(f"PR #{d['number']} has merge conflicts")
                if head and d.get("headRefOid") != head:
                    problems.append(f"PR #{d['number']} head {str(d.get('headRefOid'))[:10]} differs from local HEAD {head[:10]} (needs push, or unverified commits)")
    return problems
