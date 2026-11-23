import json
import unittest

from helpers import ONE
from helpers import L0_AXES, L3_AXES, Repo, install_example_plan

TASKS = ("TASK-001", "TASK-002", "TASK-003", "TASK-004")


class L0Test(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.r.hr("init")

    def tearDown(self):
        self.r.cleanup()

    def test_direct_change_completes_without_approval(self):
        r = self.r
        self.assertEqual(r.hr("new", "Center login card", "--slug", "login-card")[0], 0)
        code, out = r.hr("classify", "--axes", L0_AXES)
        self.assertIn("mode: L0", out)
        self.assertEqual(r.hr("transition", "executing")[0], 0)
        r.write("src/LoginCard.css", ".card { margin: 0 auto; }\n")
        code, out = r.hr("verify", "--adhoc", 'python -c "pass"', "--title", "lint")
        self.assertEqual(code, 0, out)
        self.assertEqual(r.hr("transition", "verifying_tasks")[0], 0)
        code, out = r.hr("transition", "completed")
        self.assertEqual(code, 0, out)
        st = r.state()
        self.assertEqual(st["state"], "completed")
        self.assertIsNone(st["approvals"]["design"])
        self.assertFalse(st["required_gates"]["design"])

    def test_l0_cannot_complete_without_any_verification(self):
        r = self.r
        r.hr("new", "Center login card")
        r.hr("classify", "--axes", L0_AXES)
        r.hr("transition", "executing")
        r.hr("transition", "verifying_tasks")
        code, out = r.hr("transition", "completed")
        self.assertEqual(code, 3)
        self.assertIn("no required tests", out)


class L3Test(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.r.hr("init")
        self.r.hr("new", "Multi-vehicle control", "--slug", "multi-drone")
        code, out = self.r.hr("classify", "--axes", L3_AXES, *ONE, "--flags", "vehicle_command")
        assert "mode: L3" in out, out

    def tearDown(self):
        self.r.cleanup()

    def _to_design_approval(self, fail_tests=()):
        install_example_plan(self.r, fail_tests)
        self.assertEqual(self.r.hr("transition", "clarifying")[0], 0)
        self.r.hr("classify", "--axes", L3_AXES, *ONE, "--flags", "vehicle_command", "--note", "after clarifying")
        self.assertEqual(self.r.hr("transition", "planning")[0], 0)
        code, out = self.r.hr("transition", "awaiting_design_approval")
        self.assertEqual(code, 0, out)

    def _implement_all(self):
        r = self.r
        for tid in TASKS:
            r.hr("task", tid, "in_progress")
            r.write(f"src/{tid.lower()}.py", f"# {tid}\n")
            r.commit(f"FEAT-001 {tid}")
            r.hr("task", tid, "implemented")
            code, out = r.hr("verify", "--task", tid)
            self.assertEqual(code, 0, out)
            code, out = r.hr("task", tid, "verified")
            self.assertEqual(code, 0, out)

    def test_ambiguous_safety_request_is_not_implemented_before_policy(self):
        r = self.r
        install_example_plan(r)
        fdir = r.feature_dir()
        req = json.loads((fdir / ".internal/requirements.json").read_text(encoding="utf-8"))
        req["open_questions"][0]["status"] = "open"
        (fdir / ".internal/requirements.json").write_text(json.dumps(req), encoding="utf-8")
        r.hr("transition", "clarifying")
        code, out = r.hr("transition", "executing")
        self.assertEqual(code, 3)
        self.assertIn("unresolved", out)
        code, out = r.hr("transition", "planning")
        code, out = r.hr("transition", "awaiting_design_approval")
        self.assertEqual(code, 3, out)

    def test_plan_with_gap_is_blocked_before_approval(self):
        r = self.r
        fdir = install_example_plan(r)
        graph = json.loads((fdir / ".internal/task-graph.json").read_text(encoding="utf-8"))
        graph["tasks"][3]["verification"] = []
        (fdir / ".internal/task-graph.json").write_text(json.dumps(graph), encoding="utf-8")
        r.hr("transition", "planning")
        code, out = r.hr("transition", "awaiting_design_approval")
        self.assertEqual(code, 3)
        self.assertIn("no verification method", out)

    def test_cannot_execute_without_design_approval(self):
        self._to_design_approval()
        code, out = self.r.hr("transition", "executing")
        self.assertEqual(code, 3)
        self.assertIn("design approval", out)

    def test_design_change_after_approval_invalidates(self):
        r = self.r
        self._to_design_approval()
        code, out = r.hr("approve", "design", "--by", "alice")
        self.assertEqual(code, 0, out)
        self.assertEqual(r.state()["state"], "executing")
        design = r.feature_dir() / "design.md"
        design.write_text(design.read_text(encoding="utf-8") + "\nSneaky change.\n", encoding="utf-8")
        code, out = r.hr("status")
        self.assertIn("design approval invalidated", out)
        st = r.state()
        self.assertEqual(st["state"], "planning")
        self.assertIsNone(st["approvals"]["design"])

    def test_full_governed_flow_and_sha_bound_final_approval(self):
        r = self.r
        self._to_design_approval()
        r.hr("approve", "design", "--by", "alice")
        self._implement_all()
        self.assertEqual(r.hr("transition", "verifying_tasks")[0], 0)
        self.assertEqual(r.hr("transition", "integrating")[0], 0)

        code, out = r.hr("verify", "--level", "all")
        self.assertIn("[HUMAN] TEST-013", out)
        code, out = r.hr("transition", "awaiting_final_approval")
        self.assertEqual(code, 3, "manual safety test not recorded yet")
        self.assertIn("TEST-013", out)

        r.hr("record-manual", "TEST-013", "passed", "--by", "bob", "--evidence", "https://example.com/rec.mp4")
        code, out = r.hr("transition", "awaiting_final_approval")
        self.assertEqual(code, 3, "no second search for other users of what changed")
        self.assertIn("[impact]", out)
        self.assertNotIn("TEST-013", out)
        code, out = r.hr("impact", "--recheck", "--searched", "target_system,session")
        self.assertEqual(code, 0, out)
        code, out = r.hr("transition", "awaiting_final_approval")
        self.assertEqual(code, 0, out)
        code, out = r.hr("transition", "ready_to_merge")
        self.assertEqual(code, 3, "L3 must not reach merge without final approval")

        code, out = r.hr("approve", "final", "--by", "alice")
        self.assertEqual(code, 0, out)
        self.assertEqual(r.state()["state"], "ready_to_merge")

        (r.feature_dir() / "overview.md").write_text("# edited\n", encoding="utf-8")
        r.commit("docs only")
        r.hr("status")
        self.assertIsNotNone(r.state()["approvals"]["final"])

        r.write("src/task-002.py", "# changed after approval\n")
        r.commit("late change")
        code, out = r.hr("status")
        self.assertIn("final approval invalidated", out)
        st = r.state()
        self.assertEqual(st["state"], "integrating")
        self.assertIsNone(st["approvals"]["final"])
        code, out = r.hr("transition", "awaiting_final_approval")
        self.assertEqual(code, 3, "old results are stale after the code change")
        self.assertIn("stale", out)

    def test_repeated_integration_failure_escalates_to_human(self):
        r = self.r
        self._to_design_approval(fail_tests=("TEST-011",))
        r.hr("approve", "design", "--by", "alice")
        self._implement_all()
        r.hr("transition", "verifying_tasks")
        r.hr("transition", "integrating")
        for _ in range(3):
            code, out = r.hr("verify", "--test", "TEST-011")
            self.assertEqual(code, 1)
        self.assertIn("escalated", out)
        st = r.state()
        self.assertEqual(st["state"], "blocked")
        self.assertEqual(st["block_kind"], "escalation")
        fails = json.loads((r.feature_dir() / ".internal/failures.json").read_text(encoding="utf-8"))["failures"]
        self.assertEqual(fails[0]["test_id"], "TEST-011")
        self.assertEqual(fails[0]["retry_count"], 3)
        self.assertEqual(fails[0]["suspect_tasks"], ["TASK-003"])
        code, out = r.hr("transition", "integrating")
        self.assertEqual(code, 3, "the agent cannot release an escalation")
        self.assertEqual(r.hr("unblock", "--by", "alice", "--note", "fix TASK-003")[0], 0)
        self.assertEqual(r.state()["state"], "integrating")
        code, out = r.hr("failures", "--classify", "FAIL-001", "--cause-type", "implementation", "--fix-task", "TASK-003")
        self.assertIn("rework_required", out)

    def test_resume_detects_unrecorded_commit_and_event_tampering(self):
        r = self.r
        r.hr("resume")
        r.write("src/other.py", "x = 1\n")
        r.commit("someone else's commit")
        code, out = r.hr("resume")
        self.assertIn("HEAD moved", out)
        events = r.feature_dir() / ".internal/events.jsonl"
        lines = events.read_text(encoding="utf-8").splitlines()
        tampered = json.loads(lines[1])
        tampered["mode"] = "L0"
        lines[1] = json.dumps(tampered)
        events.write_text("\n".join(lines) + "\n", encoding="utf-8")
        code, out = r.hr("check")
        self.assertEqual(code, 3)
        self.assertIn("hash mismatch", out)


class NoGitTest(unittest.TestCase):
    def test_l3_needs_git_for_verified(self):
        r = Repo(use_git=False)
        try:
            r.hr("init")
            r.hr("new", "Multi-vehicle control")
            r.hr("classify", "--axes", L3_AXES, *ONE, "--flags", "vehicle_command")
            install_example_plan(r)
            r.hr("transition", "planning")
            r.hr("transition", "awaiting_design_approval")
            r.hr("approve", "design", "--by", "alice")
            r.hr("verify", "--task", "TASK-001")
            code, out = r.hr("task", "TASK-001", "verified")
            self.assertEqual(code, 3)
            self.assertIn("committed code", out)
        finally:
            r.cleanup()


if __name__ == "__main__":
    unittest.main()
