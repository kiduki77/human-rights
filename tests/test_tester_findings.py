import json
import unittest

from helpers import L3_AXES, ONE, Repo, git, code_review, install_example_plan, no_terminal
from test_verification_model import AGENT_TEST

TASKS = ("TASK-001", "TASK-002", "TASK-003", "TASK-004")
HINT = "hint text is cut off at 320 px"
CRASH = "double click on start sends two requests"


class Base(unittest.TestCase):
    def setUp(self):
        r = self.r = Repo()
        r.hr("init")
        r.hr("new", "Multi-vehicle control", "--slug", "multi-drone")
        r.hr("classify", "--axes", L3_AXES, *ONE, "--flags", "vehicle_command")
        self.fdir = install_example_plan(r)
        path = self.fdir / ".internal" / "test-plan.json"
        plan = json.loads(path.read_text(encoding="utf-8"))
        plan["tests"].append(dict(AGENT_TEST))
        path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        r.hr("transition", "planning")
        r.hr("transition", "awaiting_design_approval")
        r.hr("approve", "design", "--by", "alice")
        for tid in TASKS:
            r.hr("task", tid, "in_progress")
            r.write(f"src/{tid.lower()}.py", f"# {tid}\n")
            r.commit(f"FEAT-001 {tid}")
            r.hr("task", tid, "implemented")
            r.hr("verify", "--task", tid)
            r.hr("task", tid, "verified")
        r.hr("transition", "verifying_tasks")
        r.hr("transition", "integrating")

    def tearDown(self):
        self.r.cleanup()

    def report(self, findings=(), rechecked=None, statuses=("passed", "passed")):
        ev = self.fdir / "evidence" / "TEST-020"
        ev.mkdir(parents=True, exist_ok=True)
        steps = []
        for i, status in enumerate(statuses, 1):
            (ev / f"step-{i}.png").write_bytes(b"png %d" % i)
            steps.append({"status": status, "observed": f"saw result {i}", "evidence": f"{self.rel(ev)}/step-{i}.png"})
        body = {"by": "hr-tester", "steps": steps, "findings": list(findings)}
        if rechecked is not None:
            body["rechecked"] = rechecked
        (ev / "report.json").write_text(json.dumps(body), encoding="utf-8")

    def rel(self, path):
        return path.relative_to(self.r.root).as_posix()

    def gone(self, fid, present=False):
        ev = self.fdir / "evidence" / "TEST-020"
        (ev / "recheck.png").write_bytes(b"recheck")
        return {"finding": fid, "present": present, "observed": "the hint fits at 320 px",
                "evidence": f"{self.rel(ev)}/recheck.png"}

    def findings(self):
        path = self.fdir / ".internal" / "findings.json"
        return json.loads(path.read_text(encoding="utf-8"))["findings"] if path.exists() else []

    def verification(self):
        self.r.hr("render")
        return (self.fdir / "verification.md").read_text(encoding="utf-8")

    def finish(self):
        r = self.r
        r.hr("verify", "--level", "all")
        r.hr("record-manual", "TEST-013", "passed", "--by", "bob")
        r.hr("impact", "--recheck", "--searched", "target_system")
        return code_review(r)


class RecordTest(Base):
    def test_findings_of_the_report_are_stored_with_their_test_and_run(self):
        self.report([HINT, CRASH, "  "])
        code, out = self.r.hr("record-agent", "TEST-020")
        self.assertEqual(code, 0, out)
        self.assertIn(f"finding: {HINT} (FND-001)", out)
        self.assertIn("each finding needs a disposition", out)
        rows = self.findings()
        self.assertEqual([x["id"] for x in rows], ["FND-001", "FND-002"])
        x = rows[0]
        self.assertEqual((x["source"], x["test"], x["run"], x["what"], x["disposition"]),
                         ("tester", "TEST-020", "RUN-0006", HINT, None))
        self.assertEqual(x["commit_sha"], git(self.r.root, "rev-parse", "HEAD"))
        self.assertEqual(self.r.hr("finding")[1].splitlines()[0], f"FND-001 [open] tester TEST-020 RUN-0006 | {HINT}")

    def test_a_rerun_does_not_record_the_same_finding_again_while_it_is_undecided_or_decided_as_kept(self):
        self.report([HINT])
        self.r.hr("record-agent", "TEST-020")
        self.report([HINT.upper()])
        self.r.hr("record-agent", "TEST-020")
        self.assertEqual(len(self.findings()), 1)
        self.r.hr("finding", "dismiss", "FND-001", "--by", "alice", "--reason", "the hint wraps by design")
        self.report([HINT])
        code, out = self.r.hr("record-agent", "TEST-020")
        self.assertIn("(FND-001)", out)
        self.assertEqual(len(self.findings()), 1)

    def test_findings_show_under_their_test_and_in_the_one_list(self):
        self.report([HINT])
        self.r.hr("record-agent", "TEST-020")
        doc = self.verification()
        self.assertIn("**Reported by the tester outside the steps**", doc)
        self.assertIn(f"- FND-001 (RUN-0006): {HINT}. **nothing yet: decide before final approval**", doc)
        self.assertIn(f"| FND-001 | `TEST-020 (RUN-0006)` | **reported by the tester.** {HINT} | "
                      "**nothing yet: decide before final approval** |", doc)
        self.assertEqual(self.r.hr("doc-check")[0], 0)

    def test_the_korean_documents_show_them_too(self):
        cfg = self.r.root / ".human-rights" / "config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + "\ndocs:\n  language: ko\n", encoding="utf-8")
        self.report([HINT])
        self.r.hr("record-agent", "TEST-020")
        doc = self.verification()
        self.assertIn("테스터가 보고함", doc)
        self.assertIn("테스터가 단계 밖에서 보고한 것", doc)

    def test_a_dirty_run_still_records_its_findings(self):
        self.r.write("src/app.py", "print('edited')\n")
        self.report([HINT])
        code, out = self.r.hr("record-agent", "TEST-020")
        self.assertIn("uncommitted", out)
        self.assertEqual(len(self.findings()), 1)


class DispositionTest(Base):
    def setUp(self):
        super().setUp()
        self.report([HINT, CRASH])
        self.r.hr("record-agent", "TEST-020")

    def settle(self, first="accept", second="dismiss"):
        r = self.r
        self.assertEqual(r.hr("finding", first, "FND-001", "--by", "alice", "--reason", "cosmetic")[0], 0)
        self.assertEqual(r.hr("finding", second, "FND-002", "--by", "alice", "--reason", "the server ignores it")[0], 0)

    def test_final_approval_is_refused_while_a_tester_finding_has_no_disposition(self):
        r = self.finish()
        code, out = self.r.hr("transition", "awaiting_final_approval")
        self.assertEqual(code, 0, out)
        code, out = self.r.hr("approve", "final", "--by", "alice")
        self.assertEqual(code, 3, out)
        self.assertIn("[tester] findings with no disposition: FND-001 (TEST-020), FND-002 (TEST-020)", out)
        self.settle()
        code, out = self.r.hr("approve", "final", "--by", "alice")
        self.assertEqual(code, 0, out)
        doc = self.verification()
        self.assertIn("accepted as a risk by alice: cosmetic", doc)
        self.assertIn("not a defect, by alice: the server ignores it", doc)

    def test_the_code_review_findings_keep_their_own_refusal(self):
        self.finish()
        self.r.hr("transition", "awaiting_final_approval")
        self.settle()
        extra = {"kind": "unused", "file": "src/task-004.py", "lines": "1", "what": "nothing imports this module"}
        code_review(self.r, [extra])
        code, out = self.r.hr("approve", "final", "--by", "alice")
        self.assertEqual(code, 3, out)
        self.assertIn("[review] findings with no disposition: FND-003.", out)
        self.assertNotIn("[tester]", out)

    def test_accepting_a_risk_and_calling_it_no_defect_are_human_decisions(self):
        r = self.r
        with no_terminal():
            for action in ("accept", "dismiss"):
                code, out = r.hr("finding", action, "FND-001", "--by", "alice", "--reason", "cosmetic")
                self.assertEqual(code, 3, out)
        code, out = r.hr("finding", "dismiss", "FND-001", "--by", "alice")
        self.assertEqual(code, 2, out)
        self.assertIn("why this is not a defect", out)
        code, out = r.hr("finding", "accept", "FND-001", "--by", "alice")
        self.assertIn("why the human accepts this risk", out)
        r.say("it is a cosmetic problem, accept FND-001")
        with no_terminal():
            code, out = r.hr("finding", "accept", "FND-001", "--reason", "cosmetic", "--quote", "dismiss it")
            self.assertEqual(code, 3, out)
            code, out = r.hr("finding", "accept", "FND-001", "--reason", "cosmetic", "--quote", "accept FND-001")
        self.assertEqual(code, 0, out)
        d = self.findings()[0]["disposition"]
        self.assertEqual((d["kind"], d["via"], d["by"]), ("accepted", "chat", "test"))

    def test_the_hook_denies_dismiss_without_a_quote(self):
        import subprocess
        import sys
        from helpers import PLUGIN

        def run(cmd):
            payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}).encode("utf-8")
            proc = subprocess.run([sys.executable, str(PLUGIN / "hooks" / "approval_guard.py")], input=payload,
                                  stdout=subprocess.PIPE, check=True)
            return proc.stdout.decode("utf-8")

        self.assertIn("deny", run(".human-rights/hr finding dismiss FND-001 --reason x"))
        self.assertEqual(run('.human-rights/hr finding dismiss FND-001 --reason x --quote "not a bug"'), "")
        self.assertEqual(run(".human-rights/hr finding fix FND-001 --commit abc1234"), "")

    def test_a_code_review_finding_cannot_be_dismissed_and_a_tester_finding_is_not_closed_by_a_review(self):
        r = self.r
        self.finish()
        extra = {"kind": "unused", "file": "src/task-004.py", "lines": "1", "what": "nothing imports this module"}
        code_review(r, [extra])
        code, out = r.hr("finding", "dismiss", "FND-003", "--by", "alice", "--reason", "x")
        self.assertEqual(code, 2, out)
        self.assertIn("finding of the code review", out)
        code, out = r.hr("finding", "fix", "FND-003")
        self.assertEqual(code, 2, out)
        r.write("src/task-004.py", "# TASK-004\nimport nothing\n")
        r.commit("touch the module")
        code_review(r)
        rows = {x["id"]: x["disposition"] for x in self.findings()}
        self.assertIsNone(rows["FND-001"])
        self.assertEqual(rows["FND-003"]["kind"], "removed")


class FixTest(Base):
    def setUp(self):
        super().setUp()
        self.report([HINT])
        self.r.hr("record-agent", "TEST-020")
        self.found = self.findings()[0]["commit_sha"]

    def fix_commit(self):
        self.r.write("src/hint.py", "# wrap the hint\n")
        return self.r.commit("wrap the range hint")

    def rerun(self, fid="FND-001", present=False, statuses=("passed", "passed")):
        self.report([], [self.gone(fid, present)], statuses)
        return self.r.hr("record-agent", "TEST-020")

    def test_the_brief_asks_the_tester_to_check_the_open_finding_again(self):
        code, out = self.r.hr("test-brief", "TEST-020", "--json")
        brief = json.loads(out)["prompt"]
        self.assertIn('"rechecked"', brief)
        self.assertIn(f"FND-001: {HINT}", brief)
        self.r.hr("finding", "dismiss", "FND-001", "--by", "alice", "--reason", "by design")
        self.assertNotIn("rechecked", json.loads(self.r.hr("test-brief", "TEST-020", "--json")[1])["prompt"])

    def test_a_fix_needs_a_later_commit_and_a_passing_rerun_that_no_longer_sees_it(self):
        r = self.r
        code, out = r.hr("finding", "fix", "FND-001", "--commit", "deadbeef")
        self.assertEqual(code, 2, out)
        self.assertIn("no such commit", out)
        code, out = r.hr("finding", "fix", "FND-001", "--commit", self.found)
        self.assertEqual(code, 3, out)
        self.assertIn("is not a commit after", out)
        sha = self.fix_commit()
        code, out = r.hr("finding", "fix", "FND-001", "--commit", sha)
        self.assertEqual(code, 3, out)
        self.assertIn("no clean re-run of TEST-020", out)
        code, out = self.rerun()
        self.assertEqual(code, 0, out)
        self.assertIn("FND-001 re-checked: gone", out)
        code, out = r.hr("finding", "fix", "FND-001", "--commit", sha)
        self.assertEqual(code, 0, out)
        self.assertIn(f"FND-001 fixed in {sha[:10]}", out)
        d = self.findings()[0]["disposition"]
        self.assertEqual((d["kind"], d["by"], d["commit_sha"], d["run"]), ("fixed", "agent", sha, "RUN-0007"))
        self.assertIn(f"fixed in `{sha[:10]}`, and RUN-0007 did not see it again", self.verification())

    def test_a_rerun_that_still_sees_it_or_fails_does_not_make_it_fixed(self):
        r = self.r
        sha = self.fix_commit()
        self.assertEqual(self.rerun(present=True)[0], 0)
        code, out = r.hr("finding", "fix", "FND-001", "--commit", sha)
        self.assertEqual(code, 3, out)
        self.assertIn("still saw FND-001", out)
        code, out = self.rerun(statuses=("passed", "failed"))
        self.assertEqual(code, 1, out)
        code, out = r.hr("finding", "fix", "FND-001", "--commit", sha)
        self.assertIn("did not pass", out)

    def test_a_rerun_on_the_code_that_found_it_proves_nothing(self):
        self.rerun()
        code, out = self.r.hr("finding", "fix", "FND-001", "--commit", "HEAD")
        self.assertEqual(code, 3, out)
        self.assertIn("is not a commit after", out)

    def test_a_rerun_before_the_fix_commit_does_not_count(self):
        self.rerun()
        sha = self.fix_commit()
        code, out = self.r.hr("finding", "fix", "FND-001", "--commit", sha)
        self.assertEqual(code, 3, out)
        self.assertIn("no clean re-run", out)

    def test_a_recheck_must_name_an_open_finding_of_this_test_with_evidence(self):
        r = self.r
        self.report([], [self.gone("FND-009")])
        code, out = r.hr("record-agent", "TEST-020")
        self.assertEqual(code, 2, out)
        self.assertIn("must be a finding of TEST-020 with no disposition (FND-001)", out)
        bad = self.gone("FND-001")
        bad["evidence"] = ""
        self.report([], [bad])
        self.assertIn("reported gone needs an evidence file", r.hr("record-agent", "TEST-020")[1])
        self.report([], [{**self.gone("FND-001"), "present": "no"}])
        self.assertIn("`present` must be true or false", r.hr("record-agent", "TEST-020")[1])
        self.assertEqual(len(self.findings()), 1)

    def test_a_fixed_finding_lets_final_approval_through(self):
        r = self.r
        sha = self.fix_commit()
        self.rerun()
        self.assertEqual(r.hr("finding", "fix", "FND-001", "--commit", sha)[0], 0)
        r.hr("verify", "--level", "all")
        r.hr("record-manual", "TEST-013", "passed", "--by", "bob")
        r.hr("impact", "--recheck", "--searched", "target_system")
        code_review(r)
        self.assertEqual(r.hr("transition", "awaiting_final_approval")[0], 0)
        code, out = r.hr("approve", "final", "--by", "alice")
        self.assertEqual(code, 0, out)

    def test_the_same_defect_after_a_fix_is_a_new_finding(self):
        r = self.r
        sha = self.fix_commit()
        self.rerun()
        r.hr("finding", "fix", "FND-001", "--commit", sha)
        self.report([HINT])
        r.hr("record-agent", "TEST-020")
        self.assertEqual([x["id"] for x in self.findings()], ["FND-001", "FND-002"])
        self.assertIsNone(self.findings()[1]["disposition"])


if __name__ == "__main__":
    unittest.main()
