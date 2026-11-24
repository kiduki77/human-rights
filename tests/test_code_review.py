import json
import unittest

from helpers import L0_AXES, L3_AXES, ONE, Repo, code_review, install_example_plan, no_terminal

TASKS = ("TASK-001", "TASK-002", "TASK-003", "TASK-004")
EXTRA = {"kind": "unexplained", "file": "src/cache.py", "lines": "1-3", "what": "a cache layer no requirement asks for"}
COPY = {"kind": "duplicate", "file": "src/util.py", "lines": "2", "what": "repeats the greeting", "existing": "src/app.py:1"}


class ReviewRecordTest(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.r.hr("init")
        self.r.hr("new", "Multi-vehicle control", "--slug", "multi-drone")
        self.r.hr("classify", "--axes", L3_AXES, *ONE, "--flags", "vehicle_command")
        self.r.write("src/cache.py", "class Cache:\n    def get(self, key):\n        return None\n")
        self.r.write("src/util.py", "def greet():\n    print('hello')\n")
        self.sha = self.r.commit("feature code")

    def tearDown(self):
        self.r.cleanup()

    def findings(self):
        path = self.r.feature_dir() / ".internal" / "findings.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"reviews": [], "findings": []}

    def test_the_work_order_lists_the_diff_and_keeps_the_implementers_account_out(self):
        code, out = self.r.hr("review-brief", "--json")
        self.assertEqual(code, 0, out)
        brief = json.loads(out)
        self.assertEqual(brief["files"], [{"path": "src/cache.py", "status": "A"}, {"path": "src/util.py", "status": "A"}])
        self.assertEqual(brief["agent"], {"subagent_type": "hr-code-reviewer", "model": "opus", "effort": "high"})
        self.assertTrue(brief["report"].endswith("evidence/code-review/report.json"))
        self.assertIn("requirements.json", brief["prompt"])
        self.assertIn("Do not read", brief["prompt"])
        self.assertNotIn(".human-rights/config.yaml", brief["prompt"])

    def test_small_changes_get_no_review(self):
        r = Repo()
        try:
            r.hr("init")
            r.hr("new", "Center login card")
            r.hr("classify", "--axes", L0_AXES)
            code, out = r.hr("review-brief")
            self.assertEqual(code, 2, out)
            self.assertIn("L2 and L3", out)
        finally:
            r.cleanup()

    def test_uncommitted_code_is_not_reviewed(self):
        self.r.write("src/util.py", "def greet():\n    print('hi')\n")
        code, out = self.r.hr("review-brief")
        self.assertEqual(code, 3, out)
        self.assertIn("commit first", out)

    def test_a_report_that_skipped_a_changed_file_is_refused(self):
        code, out = code_review(self.r, skip=("src/util.py",))
        self.assertEqual(code, 3, out)
        self.assertIn("src/util.py", out)
        self.assertEqual(self.findings()["reviews"], [])

    def test_a_finding_needs_a_changed_file_and_lines_inside_it(self):
        bad = [
            ({**EXTRA, "lines": ""}, "has no `lines`"),
            ({**EXTRA, "lines": "2-9"}, "outside src/cache.py (3 lines)"),
            ({**EXTRA, "file": "src/app.py"}, "not one of the changed files"),
            ({**EXTRA, "file": ""}, "has no `file`"),
            ({**EXTRA, "kind": "ugly"}, "`kind` must be one of"),
            ({**EXTRA, "what": " "}, "has no `what`"),
            ({**COPY, "existing": ""}, "names no `existing` place"),
            ({**COPY, "existing": "src/nowhere.py:1-4"}, "is not a file in the repository"),
        ]
        for finding, message in bad:
            code, out = code_review(self.r, [finding])
            self.assertEqual(code, 3, out)
            self.assertIn(message, out)
        self.assertEqual(self.findings()["reviews"], [], "a refused report records nothing")

    def test_no_finding_is_a_valid_result(self):
        code, out = code_review(self.r)
        self.assertEqual(code, 0, out)
        self.assertIn("REV-001", out)
        data = self.findings()
        self.assertEqual(data["reviews"][0]["commit_sha"], self.sha)
        self.assertEqual(data["reviews"][0]["files_read"], ["src/cache.py", "src/util.py"])
        self.assertEqual(data["findings"], [])

    def test_findings_are_recorded_and_shown_to_the_human(self):
        install_example_plan(self.r)
        code, out = code_review(self.r, [EXTRA, COPY])
        self.assertEqual(code, 0, out)
        self.assertIn("FND-001 [unexplained] src/cache.py:1-3", out)
        self.assertIn("no disposition yet: FND-001, FND-002", out)
        code, out = self.r.hr("finding")
        self.assertIn("FND-002 [open] duplicate src/util.py:2", out)
        self.r.hr("render")
        doc = (self.r.feature_dir() / "verification.md").read_text(encoding="utf-8")
        self.assertIn("read 2 changed file(s)", doc)
        self.assertIn("| FND-001 | `src/cache.py:1-3` | **nothing asks for it.** a cache layer no requirement asks for "
                      "| **nothing yet: decide before final approval** |", doc)
        self.assertIn("(already at `src/app.py:1`)", doc)
        self.assertEqual(self.r.hr("doc-check")[0], 0)

    def test_a_verification_document_without_the_block_fails_the_document_check(self):
        install_example_plan(self.r)
        path = self.r.feature_dir() / "verification.md"
        path.write_text(path.read_text(encoding="utf-8").replace("<!-- hr:review:start -->", ""), encoding="utf-8")
        code, out = self.r.hr("doc-check")
        self.assertIn("hr:review", out)

    def test_removed_code_is_closed_by_the_next_review(self):
        r = self.r
        code_review(r, [EXTRA, COPY])
        (r.root / "src/cache.py").unlink()
        r.commit("drop the cache")
        code, out = r.hr("review-brief")
        self.assertIn("Already recorded", out)
        self.assertIn("FND-002 src/util.py:2", out)
        self.assertNotIn("FND-001", out)
        code, out = code_review(r)
        self.assertEqual(code, 0, out)
        self.assertIn("closed, because their code changed and was reviewed again: FND-001", out)
        rows = {x["id"]: x["disposition"] for x in self.findings()["findings"]}
        self.assertEqual((rows["FND-001"]["kind"], rows["FND-001"]["review"]), ("removed", "REV-002"))
        self.assertIsNone(rows["FND-002"], "its file did not change, so nothing removed it")

    def test_code_that_changed_and_is_found_again_is_not_called_removed(self):
        r = self.r
        code_review(r, [EXTRA])
        r.write("src/cache.py", "class Cache:\n    def get(self, key):\n        return 0\n")
        r.commit("still a cache")
        code, out = code_review(r, [EXTRA])
        self.assertEqual(code, 0, out)
        rows = {x["id"]: x["disposition"] for x in self.findings()["findings"]}
        self.assertEqual(rows["FND-001"]["kind"], "reported_again")
        self.assertIsNone(rows["FND-002"])

    def test_a_second_review_of_the_same_code_closes_nothing(self):
        code_review(self.r, [EXTRA])
        code, out = code_review(self.r)
        self.assertEqual(code, 0, out)
        self.assertIsNone(self.findings()["findings"][0]["disposition"])

    def test_keeping_the_code_is_a_human_decision_with_a_reason(self):
        r = self.r
        code_review(r, [EXTRA, COPY])
        code, out = r.hr("finding", "accept", "FND-001", "--by", "alice")
        self.assertEqual(code, 2, out)
        self.assertIn("--reason", out)
        with no_terminal():
            code, out = r.hr("finding", "accept", "FND-001", "--by", "alice", "--reason", "needed next sprint")
        self.assertEqual(code, 3, "an agent cannot accept its own extra code")
        code, out = r.hr("finding", "accept", "FND-404", "--by", "alice", "--reason", "x")
        self.assertEqual(code, 2, out)
        code, out = r.hr("finding", "accept", "fnd-001", "--by", "alice", "--reason", "needed next sprint")
        self.assertEqual(code, 0, out)
        d = self.findings()["findings"][0]["disposition"]
        self.assertEqual((d["kind"], d["by"], d["reason"]), ("accepted", "alice", "needed next sprint"))
        code, out = r.hr("finding", "accept", "FND-001", "--by", "alice", "--reason", "again")
        self.assertEqual(code, 2, out)
        code, out = r.hr("review-brief")
        self.assertIn("FND-001 src/cache.py:1-3", out)

    def test_acceptance_in_chat_needs_the_humans_words(self):
        r = self.r
        code_review(r, [EXTRA])
        r.say("keep FND-001, the cache is for the next release")
        with no_terminal():
            code, out = r.hr("finding", "accept", "FND-001", "--reason", "for the next release", "--quote", "delete it")
            self.assertEqual(code, 3, out)
            code, out = r.hr("finding", "accept", "FND-001", "--reason", "for the next release", "--quote", "keep FND-001")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.findings()["findings"][0]["disposition"]["via"], "chat")


class ReviewGateTest(unittest.TestCase):
    def setUp(self):
        r = self.r = Repo()
        r.hr("init")
        r.hr("new", "Multi-vehicle control", "--slug", "multi-drone")
        r.hr("classify", "--axes", L3_AXES, *ONE, "--flags", "vehicle_command")
        install_example_plan(r)
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
        r.hr("verify", "--level", "all")
        r.hr("record-manual", "TEST-013", "passed", "--by", "bob")
        r.hr("impact", "--recheck", "--searched", "target_system")

    def tearDown(self):
        self.r.cleanup()

    def test_final_approval_waits_for_the_review_and_for_every_finding(self):
        r = self.r
        code, out = r.hr("transition", "awaiting_final_approval")
        self.assertEqual(code, 3, out)
        self.assertIn("[review]", out)
        self.assertIn("none is recorded", out)
        finding = {"kind": "unused", "file": "src/task-004.py", "lines": "1", "what": "nothing imports this module"}
        code, out = code_review(r, [finding])
        self.assertEqual(code, 0, out)
        code, out = r.hr("transition", "awaiting_final_approval")
        self.assertEqual(code, 0, out)
        self.assertIn("FND-001", (r.feature_dir() / "verification.md").read_text(encoding="utf-8"))
        code, out = r.hr("approve", "final", "--by", "alice")
        self.assertEqual(code, 3, out)
        self.assertIn("findings with no disposition: FND-001", out)
        code, out = r.hr("finding", "accept", "FND-001", "--by", "alice", "--reason", "TASK-005 will import it")
        self.assertEqual(code, 0, out)
        code, out = r.hr("approve", "final", "--by", "alice")
        self.assertEqual(code, 0, out)
        self.assertEqual(r.state()["state"], "ready_to_merge")
        r.hr("render")
        self.assertIn("kept by alice: TASK-005 will import it",
                      (r.feature_dir() / "verification.md").read_text(encoding="utf-8"))

    def test_a_review_of_older_code_does_not_count(self):
        r = self.r
        code_review(r)
        r.write("src/task-004.py", "# TASK-004\nextra = 1\n")
        r.commit("one more line")
        code, out = r.hr("transition", "awaiting_final_approval")
        self.assertEqual(code, 3, out)
        self.assertIn("the code changed after the last one", out)


if __name__ == "__main__":
    unittest.main()
