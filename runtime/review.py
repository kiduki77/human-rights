from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from runtime.common import EXCLUDE_SPECS, GateError, HRError, fingerprint, git, now
from runtime.state.store import Feature

KINDS = ("unexplained", "duplicate", "unused")
MODES = ("L2", "L3")
SOURCE = "code-review"
TESTER = "tester"
REVIEWER = "hr-code-reviewer"
LINES_RE = re.compile(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*")
PLACE_RE = re.compile(r"^(.*?)(?::\d+(?:\s*-\s*\d+)?)?$")


def load(feature: Feature) -> Dict[str, List[Dict[str, Any]]]:
    data = feature.load("findings", None) or {}
    return {"reviews": data.get("reviews") or [], "findings": data.get("findings") or []}


def report_path(feature: Feature) -> Path:
    return feature.dir / "evidence" / "code-review" / "report.json"


def _norm(path: Any) -> str:
    text = str(path or "").strip().replace("\\", "/")
    return text[2:] if text.startswith("./") else text


def changed(root: Path, base: str, head: str) -> Optional[Dict[str, str]]:
    out = git(root, "-c", "core.quotepath=false", "diff", "--name-status", "--no-renames", base, head, "--", ".",
              *EXCLUDE_SPECS)
    if out is None:
        return None
    files: Dict[str, str] = {}
    for line in out.splitlines():
        status, _, path = line.partition("\t")
        if path.strip():
            files[path.strip()] = status.strip()[:1]
    return files


def latest(feature: Feature) -> Optional[Dict[str, Any]]:
    reviews = load(feature)["reviews"]
    return reviews[-1] if reviews else None


def open_findings(feature: Feature) -> List[Dict[str, Any]]:
    return [x for x in load(feature)["findings"] if not x.get("disposition")]


def _code(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [x for x in items if x.get("source") == SOURCE]


def _tester(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [x for x in items if x.get("source") == TESTER]


def problems(feature: Feature, st: Dict[str, Any], dispositions: bool = False) -> List[str]:
    out: List[str] = []
    fp = fingerprint(feature.ws.root) if st.get("mode") in MODES else {}
    if fp.get("git"):
        last = latest(feature)
        if not last or last.get("code_tree") != fp.get("code_tree"):
            why = "the code changed after the last one" if last else "none is recorded"
            out.append(f"[review] the written code needs a review by an agent that did not write it ({why}). Get "
                       f"the work order with `hr review-brief`, give it to {REVIEWER}, and record its report with "
                       "`hr record-review`")
    if dispositions:
        left = [x["id"] for x in _code(open_findings(feature))]
        if left:
            out.append("[review] findings with no disposition: " + ", ".join(left) + ". Remove the code and run the "
                       "review again, or the human accepts the finding with a reason (in chat, recorded with "
                       "`hr finding accept <id> --reason ... --quote`)")
        unsettled = [f"{x['id']} ({x['test']})" for x in _tester(open_findings(feature))]
        if unsettled:
            out.append("[tester] findings with no disposition: " + ", ".join(unsettled) + ". Fix the defect, re-run "
                       "the test so the tester checks the finding again, and record `hr finding fix <id> --commit "
                       "<sha>`. Or the human decides in chat: `hr finding accept <id> --reason ... --quote` accepts "
                       "it as a risk, `hr finding dismiss <id> --reason ... --quote` says it is not a defect")
    return out


def _context(feature: Feature) -> Tuple[Dict[str, Any], Dict[str, Any], str, Dict[str, str]]:
    st = feature.state()
    if st.get("mode") not in MODES:
        raise HRError(f"the review of the written code runs at L2 and L3 (this feature is {st.get('mode') or 'unclassified'})")
    fp = fingerprint(feature.ws.root)
    if not fp.get("git"):
        raise GateError("the review reads a git diff, and this is not a git repository with a commit")
    if fp.get("dirty"):
        raise GateError("commit first: the review is recorded for one version of the code")
    base = (st.get("git") or {}).get("base_sha")
    files = changed(feature.ws.root, base, fp["commit_sha"]) if base else None
    if files is None:
        raise GateError("the commit this feature started from is not recorded or no longer exists, so there is no "
                        "diff to review")
    return st, fp, base, files


def _untouched(feature: Feature, data: Dict[str, Any], head: str) -> List[Dict[str, Any]]:
    by_id = {r["id"]: r for r in data["reviews"]}
    cache: Dict[str, Optional[Dict[str, str]]] = {}
    out = []
    for x in _code(data["findings"]):
        if x.get("disposition"):
            continue
        sha = (by_id.get(x.get("review")) or {}).get("commit_sha") or ""
        if sha not in cache:
            cache[sha] = changed(feature.ws.root, sha, head) if sha else None
        since = cache[sha]
        if since is not None and x["file"] not in since:
            out.append(x)
    return out


def _place(x: Dict[str, Any]) -> str:
    if x.get("source") == TESTER:
        return f"{x['test']} {x['run']}"
    first, last = x["lines"]
    return f"{x['file']}:{first}" + (f"-{last}" if last != first else "")


def brief(feature: Feature) -> Dict[str, Any]:
    st, fp, base, files = _context(feature)
    data = load(feature)
    rel = feature.dir.relative_to(feature.ws.root).as_posix()
    report = report_path(feature)
    report.parent.mkdir(parents=True, exist_ok=True)
    report_rel = report.relative_to(feature.ws.root).as_posix()
    listing = "\n".join(f"  {status} {path}" for path, status in sorted(files.items())) or "  (no file changed)"
    known = [x for x in _code(data["findings"]) if (x.get("disposition") or {}).get("kind") == "accepted"]
    known += _untouched(feature, data, fp["commit_sha"])
    skip = "\n".join(f"  {x['id']} {_place(x)}: {x['what']}" for x in known)
    prompt = (
        f"You are {REVIEWER}. Review the code written for feature {feature.id} \"{st.get('title', '')}\". "
        "You did not write it.\n"
        f"Repository root: {feature.ws.root}\n\n"
        "What was asked for and approved. Read only these:\n"
        f"  {rel}/.internal/requirements.json\n"
        f"  {rel}/.internal/task-graph.json\n"
        f"  {rel}/design.md\n"
        f"  {rel}/.internal/failures.json (a fix for a failure recorded there is explained)\n"
        f"Do not read {rel}/overview.md, {rel}/verification.md or {rel}/tasks/: they hold the implementer's "
        "account of the work. Do not ask anyone what was done.\n\n"
        f"What was written: `git diff {base[:10]} {fp['commit_sha'][:10]} -- <file>` for each file below "
        "(A added, M changed, D deleted).\n"
        f"{listing}\n\n"
        "Read every file in the list that still exists, the whole file and not only the changed lines.\n\n"
        "Report only these three kinds of finding. Each needs one changed file and the lines in it:\n"
        "  unexplained: a change that no requirement, task or recorded failure explains\n"
        "  duplicate:   code that repeats something the repository already has. Name the existing place in `existing`\n"
        "  unused:      code that nothing uses. Search for its users before you report it\n"
        "Style, naming, formatting and bugs are not findings here.\n"
        + (f"\nAlready recorded. Do not report these again:\n{skip}\n" if skip else "")
        + f"\nWrite {report_rel}:\n"
        f'  {{"by": "{REVIEWER}", "files_read": ["<every file you read>"], "findings": [{{"kind": '
        '"unexplained|duplicate|unused", "file": "<a changed file>", "lines": "<first>-<last>", "what": "<one '
        'sentence: what it is and why nothing explains it>", "existing": "<path:lines, for duplicate only>"}]}\n'
        "`files_read` must hold every listed file that still exists. No finding is a valid result: "
        '`"findings": []`. Do not edit code, do not fix anything, do not run hr.'
    )
    return {"report": report_rel, "base_sha": base, "commit_sha": fp["commit_sha"],
            "files": [{"path": p, "status": s} for p, s in sorted(files.items())], "prompt": prompt}


def _lines(raw: Any) -> Optional[Tuple[int, int]]:
    if isinstance(raw, (list, tuple)) and len(raw) == 2:
        raw = f"{raw[0]}-{raw[1]}"
    m = LINES_RE.fullmatch(str(raw if raw is not None else ""))
    if not m:
        return None
    first = int(m.group(1))
    return first, int(m.group(2) or first)


def _finding(root: Path, files: Dict[str, str], raw: Any) -> Tuple[List[str], Dict[str, Any]]:
    if not isinstance(raw, dict):
        return ["is not an object"], {}
    errors: List[str] = []
    kind = str(raw.get("kind") or "").strip()
    if kind not in KINDS:
        errors.append(f"`kind` must be one of {', '.join(KINDS)}")
    path = _norm(raw.get("file"))
    span = _lines(raw.get("lines"))
    if not path:
        errors.append("has no `file`")
    elif path not in files:
        errors.append(f"`file` {path} is not one of the changed files")
    elif files[path] == "D":
        errors.append(f"`file` {path} was deleted by this change, so it has no lines to point at")
    elif span is None:
        errors.append("has no `lines` (\"<first>-<last>\")")
    else:
        try:
            total = len((root / path).read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            total = 0
        if not 1 <= span[0] <= span[1] <= total:
            errors.append(f"`lines` {span[0]}-{span[1]} is outside {path} ({total} lines)")
    what = str(raw.get("what") or "").strip()
    if not what:
        errors.append("has no `what`")
    existing = str(raw.get("existing") or "").strip()
    if kind == "duplicate":
        there = _norm(PLACE_RE.match(existing).group(1)) if existing else ""
        if not there:
            errors.append("is a duplicate and names no `existing` place")
        elif not (root / there).is_file():
            errors.append(f"`existing` {there} is not a file in the repository")
    row = {"kind": kind, "file": path, "lines": list(span or (0, 0)), "what": what}
    if existing:
        row["existing"] = existing
    return errors, row


def record(feature: Feature, report: Any) -> Dict[str, Any]:
    st, fp, base, files = _context(feature)
    root = feature.ws.root
    if not isinstance(report, dict):
        raise HRError("the report must be a JSON object")
    read = {_norm(p) for p in report.get("files_read") or []}
    present = sorted(p for p, s in files.items() if s != "D")
    unread = [p for p in present if p not in read]
    if unread:
        raise GateError("the report was refused: `files_read` does not hold these changed files: "
                        + ", ".join(unread) + ". The reviewer reads every changed file before it reports")
    rows, errors = [], []
    for i, raw in enumerate(report.get("findings") or [], 1):
        errs, row = _finding(root, files, raw)
        errors += [f"finding {i} {e}" for e in errs]
        rows.append(row)
    if errors:
        raise GateError("the report was refused, nothing is recorded:\n  - " + "\n  - ".join(errors))
    data = load(feature)
    rid = f"REV-{len(data['reviews']) + 1:03d}"
    stamp = now()
    still = {x["id"] for x in _untouched(feature, data, fp["commit_sha"])}
    again = {(r["kind"], r["file"]) for r in rows}
    closed = []
    for x in _code(data["findings"]):
        if x.get("disposition") or x["id"] in still:
            continue
        kind = "reported_again" if (x["kind"], x["file"]) in again else "removed"
        x["disposition"] = {"kind": kind, "review": rid, "at": stamp, "by": "runtime"}
        closed.append(x["id"])
    start = len(data["findings"])
    for n, row in enumerate(rows, start + 1):
        data["findings"].append({"id": f"FND-{n:03d}", "source": SOURCE, "review": rid, **row, "disposition": None})
    review = {"id": rid, "at": stamp, "by": str(report.get("by") or REVIEWER), "base_sha": base,
              "commit_sha": fp["commit_sha"], "code_tree": fp["code_tree"], "files_read": present,
              "findings": [x["id"] for x in data["findings"][start:]]}
    data["reviews"].append(review)
    feature.save("findings", data)
    feature.emit("code_reviewed", review=rid, commit_sha=fp["commit_sha"], code_tree=fp["code_tree"],
                 files=len(present), findings=review["findings"], closed=closed, actor=f"agent:{review['by']}")
    return {"review": review, "new": data["findings"][start:], "closed": closed, "open": sorted(still)}


def _pending(data: Dict[str, List[Dict[str, Any]]], fid: str) -> Dict[str, Any]:
    x = next((f for f in data["findings"] if f["id"] == fid.strip().upper()), None)
    if x is None:
        raise HRError(f"no such finding: {fid}")
    if x.get("disposition"):
        raise HRError(f"{x['id']} already has a disposition: {x['disposition']['kind']}")
    return x


def _decide(feature: Feature, data: Dict[str, List[Dict[str, Any]]], x: Dict[str, Any], disposition: Dict[str, Any],
            actor: str) -> Dict[str, Any]:
    x["disposition"] = {"at": now(), **disposition}
    feature.save("findings", data)
    feature.emit("finding_disposed", finding=x["id"], disposition=disposition["kind"], actor=actor,
                 **{k: v for k, v in disposition.items() if k not in ("kind", "by", "at")})
    return x


def accept(feature: Feature, fid: str, reason: str, by: str, proof: Dict[str, Any]) -> Dict[str, Any]:
    data = load(feature)
    x = _pending(data, fid)
    if not (reason or "").strip():
        raise HRError("--reason is required: " + ("why the human accepts this risk" if x["source"] == TESTER
                                                  else "why the human keeps this code"))
    return _decide(feature, data, x, {"kind": "accepted", "by": by, "reason": reason.strip(), **proof}, f"human:{by}")


def dismiss(feature: Feature, fid: str, reason: str, by: str, proof: Dict[str, Any]) -> Dict[str, Any]:
    data = load(feature)
    x = _pending(data, fid)
    if x["source"] != TESTER:
        raise HRError(f"{x['id']} is a finding of the code review: the code is removed or the human keeps it "
                      "(`hr finding accept`). `dismiss` is for tester findings")
    if not (reason or "").strip():
        raise HRError("--reason is required: why this is not a defect")
    return _decide(feature, data, x, {"kind": "not_defect", "by": by, "reason": reason.strip(), **proof},
                   f"human:{by}")


def _same_text(text: str) -> str:
    return " ".join(str(text).split()).casefold()


def record_tester(feature: Feature, test: Dict[str, Any], run: Dict[str, Any]) -> List[str]:
    data = load(feature)
    ids: List[str] = []
    new: List[str] = []
    for text in run.get("findings") or []:
        same = next((x for x in _tester(data["findings"]) if x["test"] == test["id"]
                     and _same_text(x["what"]) == _same_text(text)
                     and (x.get("disposition") or {}).get("kind") in (None, "accepted", "not_defect")), None)
        if same is None:
            same = {"id": f"FND-{len(data['findings']) + 1:03d}", "source": TESTER, "test": test["id"],
                    "run": run["run_id"], "commit_sha": run.get("commit_sha"), "what": text, "disposition": None}
            data["findings"].append(same)
            new.append(same["id"])
        ids.append(same["id"])
    if new:
        feature.save("findings", data)
        feature.emit("tester_findings_recorded", test_id=test["id"], run_id=run["run_id"], findings=new,
                     actor=run.get("recorded_by"))
    return ids


def recheckable(feature: Feature, test_id: str) -> List[Dict[str, Any]]:
    return [x for x in _tester(open_findings(feature)) if x["test"] == test_id]


def _descends(root: Path, old: str, new: str) -> bool:
    return git(root, "merge-base", "--is-ancestor", old, new) is not None


def fix(feature: Feature, fid: str, commit: Optional[str]) -> Dict[str, Any]:
    data = load(feature)
    x = _pending(data, fid)
    if x["source"] != TESTER:
        raise HRError(f"{x['id']} is a finding of the code review: the next review closes it when the code is "
                      "removed. `fix` is for tester findings")
    root = feature.ws.root
    sha = git(root, "rev-parse", "--verify", "--quiet", f"{commit or 'HEAD'}^{{commit}}")
    if not sha:
        raise HRError(f"no such commit: {commit or 'HEAD'}")
    found = x.get("commit_sha")
    if not found:
        raise GateError(f"{x['id']} was reported with no commit recorded, so no later commit can be shown")
    if sha == found or not _descends(root, found, sha):
        raise GateError(f"{sha[:10]} is not a commit after {found[:10]}, the code {x['run']} tested when it found "
                        f"{x['id']}")
    if not _descends(root, sha, "HEAD"):
        raise GateError(f"{sha[:10]} is not in the history of the current commit")
    runs = feature.test_results().get("runs", [])
    ids = [r["run_id"] for r in runs]
    later = runs[ids.index(x["run"]) + 1:] if x["run"] in ids else []
    check = None
    for run in reversed(later):
        mine = next((c for c in run.get("rechecked") or [] if c.get("finding") == x["id"]), None)
        if (mine and run["test_id"] == x["test"] and not run.get("dirty") and run.get("commit_sha")
                and _descends(root, sha, run["commit_sha"])):
            check = (run, mine)
            break
    if check is None:
        raise GateError(f"no clean re-run of {x['test']} on or after {sha[:10]} checked {x['id']} again. Get the "
                        f"brief with `hr test-brief {x['test']}`: it lists the finding for the tester to re-check, "
                        "then `hr record-agent`")
    run, mine = check
    if mine["present"] or run["status"] != "agent_passed":
        raise GateError(f"{run['run_id']} re-ran {x['test']} after {sha[:10]} and "
                        + ("still saw " + x["id"] if mine["present"] else "did not pass") + ", so it is not fixed")
    return _decide(feature, data, x, {"kind": "fixed", "by": "agent", "commit_sha": sha, "run": run["run_id"]},
                   "agent")
