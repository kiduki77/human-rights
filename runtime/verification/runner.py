from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime.common import HRError, fingerprint, now, run_shell, sha256_bytes
from runtime.state.store import Feature


def _next_id(prefix: str, existing: List[Dict[str, Any]]) -> str:
    return f"{prefix}-{len(existing) + 1:04d}"


def _record(feature: Feature, run: Dict[str, Any]) -> None:
    results = feature.test_results()
    results.setdefault("runs", []).append(run)
    feature.save("test_results", results)
    feature.emit(
        "test_finished",
        test_id=run["test_id"],
        status=run["status"],
        commit_sha=run.get("commit_sha"),
        code_tree=run.get("code_tree"),
        dirty=run.get("dirty"),
        environment=run.get("environment"),
        artifact_ref=run.get("log_ref") or run.get("evidence"),
        run_id=run["run_id"],
        worktree_task=run.get("worktree_task"),
        duration_s=run.get("duration_s"),
        actor=run.get("recorded_by", "runner"),
    )


def _execute(job: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    test, cwd = job["test"], job["cwd"]
    before = fingerprint(cwd)
    started = now()
    rc, output, dur = run_shell(test["command"], cwd, timeout)
    after = fingerprint(cwd)
    return {"job": job, "before": before, "after": after, "rc": rc, "output": output, "dur": dur,
            "started": started, "finished": now()}


def run_jobs(feature: Feature, jobs: List[Dict[str, Any]], timeout: int, environment: str,
             max_retries: int, max_parallel: int = 1) -> List[Dict[str, Any]]:
    from runtime.scheduler.dag import test_batches
    from runtime.verification import failures as fail_mod

    root = feature.ws.root
    out: List[Dict[str, Any]] = []
    runnable = []
    for job in jobs:
        if job["test"].get("command"):
            runnable.append(job)
        else:
            from runtime.verification.evidence import runner_of

            if runner_of(job["test"]) == "agent":
                out.append({"test_id": job["test"]["id"], "status": "agent_required",
                            "note": "run by an agent: get the brief with `hr test-brief`, have hr-tester perform "
                                    "it, then `hr record-agent`"})
            else:
                out.append({"test_id": job["test"]["id"], "status": "manual_required",
                            "note": "run by a human, after every script and agent test passes: ask them to "
                                    "report the result in chat, then record it with record-manual --quote"})
    proxies = [dict(j["test"], _job=j) for j in runnable]
    for rnd in test_batches(proxies, max_parallel):
        round_jobs = [p["_job"] for p in rnd]
        if len(round_jobs) == 1:
            results = [_execute(round_jobs[0], timeout)]
        else:
            with ThreadPoolExecutor(max_workers=len(round_jobs)) as pool:
                results = list(pool.map(lambda j: _execute(j, timeout), round_jobs))
        for res in results:
            out.append(_record_result(feature, res, environment, max_retries, len(round_jobs), fail_mod))
    return out


def _record_result(feature: Feature, res: Dict[str, Any], environment: str, max_retries: int,
                   concurrency: int, fail_mod) -> Dict[str, Any]:
    root = feature.ws.root
    test = res["job"]["test"]
    fp, after = res["before"], res["after"]
    run_id = _next_id("RUN", feature.test_results().get("runs", []))
    feature.logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = feature.logs_dir / f"{run_id}-{test['id']}.log"
    where = res["job"].get("worktree_task")
    header = (f"# {test['id']} {test['command']}\n# exit={res['rc']} started={res['started']} cwd={res['job']['cwd']}"
              f" concurrency={concurrency}\n").encode()
    log_path.write_bytes(header + res["output"])
    changed = (fp.get("code_tree"), fp.get("worktree_hash")) != (after.get("code_tree"), after.get("worktree_hash"))
    status = "error" if changed else ("passed" if res["rc"] == 0 else "failed")
    run = {
        "run_id": run_id,
        "test_id": test["id"],
        "status": status,
        "commit_sha": fp["commit_sha"],
        "code_tree": fp["code_tree"],
        "dirty": fp["dirty"],
        "worktree_hash": fp["worktree_hash"],
        "worktree_task": where,
        "environment": environment,
        "recorded_by": "runner",
        "command": test["command"],
        "exit_code": res["rc"],
        "duration_s": round(res["dur"], 2),
        "concurrency": concurrency,
        "log_ref": log_path.relative_to(root).as_posix(),
        "log_sha256": sha256_bytes(header + res["output"]),
        "output_tail": res["output"].decode("utf-8", errors="replace")[-1500:],
        "started_at": res["started"],
        "finished_at": res["finished"],
    }
    _record(feature, run)
    if changed:
        run["note"] = "the code under test changed while this ran; result discarded as error - re-run on a stable tree"
    elif run["dirty"]:
        run["note"] = "ran on uncommitted changes: counts for L0/L1 completion only; commit and re-run for task verification / final approval"
    elif run["status"] == "failed":
        run["failure"] = fail_mod.on_failed(feature, test, run, max_retries)
    else:
        fail_mod.on_passed(feature, test, run)
    return run


def evidence_dir(feature: Feature, test_id: str) -> Path:
    return feature.dir / "evidence" / test_id


def record_agent(feature: Feature, test: Dict[str, Any], report: Dict[str, Any], max_retries: int) -> Dict[str, Any]:
    from runtime.verification import failures as fail_mod

    steps = test.get("steps") or []
    got = report.get("steps")
    if not isinstance(got, list) or len(got) != len(steps):
        raise HRError(f"{test['id']}: the report must have one result per planned step ({len(steps)} steps)")
    base = evidence_dir(feature, test["id"]).resolve()
    results = []
    for i, (plan_step, res) in enumerate(zip(steps, got), 1):
        status = res.get("status")
        if status not in ("passed", "failed"):
            raise HRError(f"{test['id']} step {i}: status must be passed or failed")
        observed = str(res.get("observed") or "").strip()
        if not observed:
            raise HRError(f"{test['id']} step {i}: `observed` is required (what was actually seen)")
        ev = str(res.get("evidence") or "").strip()
        sha = None
        if ev:
            p = (feature.ws.root / ev).resolve() if not Path(ev).is_absolute() else Path(ev).resolve()
            if base not in p.parents or not p.is_file() or p.stat().st_size == 0:
                raise HRError(f"{test['id']} step {i}: evidence must be a non-empty file under "
                              f"{base.relative_to(feature.ws.root).as_posix()}/ (got {ev})")
            sha = sha256_bytes(p.read_bytes())
            ev = p.relative_to(feature.ws.root).as_posix()
        elif status == "passed":
            raise HRError(f"{test['id']} step {i}: a passed step needs an evidence file (screenshot, recording, log)")
        results.append({"n": i, "do": plan_step.get("do"), "expect": plan_step.get("expect"), "status": status,
                        "observed": observed, "evidence": ev or None, "evidence_sha256": sha})
    passed = all(r["status"] == "passed" for r in results)
    fp = fingerprint(feature.ws.root)
    run = {
        "run_id": _next_id("RUN", feature.test_results().get("runs", [])),
        "test_id": test["id"],
        "status": "agent_passed" if passed else "agent_failed",
        "commit_sha": fp["commit_sha"],
        "code_tree": fp["code_tree"],
        "dirty": fp["dirty"],
        "worktree_hash": fp["worktree_hash"],
        "environment": test.get("environment") or "agent",
        "recorded_by": f"agent:{report.get('by') or 'hr-tester'}",
        "steps": results,
        "findings": [str(x) for x in (report.get("findings") or [])],
        "evidence": base.relative_to(feature.ws.root).as_posix(),
        "started_at": report.get("started_at") or now(),
        "finished_at": now(),
    }
    _record(feature, run)
    if run["dirty"]:
        return run
    if passed:
        fail_mod.on_passed(feature, test, run)
    else:
        run["failure"] = fail_mod.on_failed(feature, test, run, max_retries)
    return run


def run_tests(feature: Feature, tests: List[Dict[str, Any]], timeout: int, environment: str,
              max_retries: int, cwd: Optional[Path] = None, worktree_task: Optional[str] = None,
              max_parallel: int = 1) -> List[Dict[str, Any]]:
    jobs = [{"test": t, "cwd": cwd or feature.ws.root, "worktree_task": worktree_task} for t in tests]
    return run_jobs(feature, jobs, timeout, environment, max_retries, max_parallel)


def record_manual(feature: Feature, test: Dict[str, Any], passed: bool, by: str, note: str,
                  evidence: Optional[str], environment: str, max_retries: int,
                  proof: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from runtime.verification import failures as fail_mod

    if not by:
        raise HRError("--by (reviewer) is required")
    fp = fingerprint(feature.ws.root)
    run = {
        "run_id": _next_id("RUN", feature.test_results().get("runs", [])),
        "test_id": test["id"],
        "status": "manual_passed" if passed else "manual_failed",
        "commit_sha": fp["commit_sha"],
        "code_tree": fp["code_tree"],
        "dirty": fp["dirty"],
        "worktree_hash": fp["worktree_hash"],
        "environment": environment,
        "recorded_by": f"human:{by}",
        "note": note,
        "evidence": evidence,
        "started_at": now(),
        "finished_at": now(),
        **(proof or {}),
    }
    _record(feature, run)
    if run["dirty"]:
        return run
    if passed:
        fail_mod.on_passed(feature, test, run)
    else:
        run["failure"] = fail_mod.on_failed(feature, test, run, max_retries)
    return run
