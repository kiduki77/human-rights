import json
import random
import subprocess
import sys
import unittest

from helpers import L3_AXES, PLUGIN, Repo, install_example_plan
from runtime import docs, redpill
from runtime.state.store import Workspace

TASKS = ("TASK-001", "TASK-002", "TASK-003", "TASK-004")


class StubRng:
    def __init__(self, r):
        self.r = r

    def randrange(self, n):
        return 0

    def random(self):
        return self.r

    def choice(self, seq):
        return seq[0]


def guard(tool, **inp):
    proc = subprocess.run([sys.executable, str(PLUGIN / "hooks" / "approval_guard.py")],
                          input=json.dumps({"tool_name": tool, "tool_input": inp}).encode(), stdout=subprocess.PIPE)
    out = proc.stdout.decode().strip()
    return json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out else "allow"


class RedpillBase(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        r = self.r
        r.hr("init")
        r.hr("new", "Multi-vehicle control", "--slug", "multi-drone")
        r.hr("classify", "--axes", L3_AXES, "--flags", "vehicle_command")
        install_example_plan(r)
        r.hr("transition", "planning")

    def tearDown(self):
        self.r.cleanup()

    def feature(self):
        return Workspace(self.r.root).resolve(None)

    def drill(self):
        return redpill.load(self.feature())

    def overview(self):
        return (self.r.feature_dir() / "overview.md").read_text(encoding="utf-8")


class DesignDrillTest(RedpillBase):
    def test_off_by_default_never_plants(self):
        code, out = self.r.hr("transition", "awaiting_design_approval")
        self.assertEqual(code, 0, out)
        self.assertIsNone(self.drill()["active"])
        self.assertEqual(self.r.hr("approve", "design", "--by", "alice")[0], 0)

    def test_rubber_stamp_is_scolded_until_the_plant_is_caught(self):
        r = self.r
        r.hr("redpill", "on", "--one-in", "1")
        design_before = (r.feature_dir() / "design.md").read_text(encoding="utf-8")
        self.assertEqual(r.hr("transition", "awaiting_design_approval")[0], 0)
        act = self.drill()["active"]
        self.assertIsNotNone(act)
        self.assertIn(act["row"], self.overview())
        self.assertNotIn(act["id"], (r.feature_dir() / "design.md").read_text(encoding="utf-8").replace(design_before, ""))
        plan_ids = [t["id"] for t in self.feature().task_graph()["tasks"]] + [t["id"] for t in self.feature().test_plan()["tests"]]
        self.assertNotIn(act["id"], plan_ids, "the plant never enters the machine plan")

        code, out = r.hr("approve", "design", "--by", "alice")
        self.assertEqual(code, 3)
        self.assertIn("flag", out)
        self.assertEqual(r.state()["state"], "awaiting_design_approval")
        self.assertIsNone(r.state()["approvals"]["design"])

        code, out = r.hr("flag", "TEST-001", "--by", "alice", "--note", "is this enough?")
        self.assertIn("Recorded your concern on TEST-001", out)
        self.assertEqual(r.hr("approve", "design", "--by", "alice")[0], 3)
        self.assertEqual(self.drill()["active"]["attempts"], 2)
        code, out = r.hr("status")
        self.assertIn("human review flags: TEST-001 (is this enough?)", out)

        code, out = r.hr("flag", act["id"].lower(), "--by", "alice")
        self.assertIn("Good catch", out)
        self.assertNotIn(act["row"], self.overview())
        code, out = r.hr("approve", "design", "--by", "alice")
        self.assertEqual(code, 0, out)
        self.assertEqual(r.state()["state"], "executing")
        self.assertEqual(redpill.stats(self.feature())["caught"], 1)

        r.hr("task", "TASK-001", "in_progress")
        r.hr("render")
        r.hr("status")
        self.assertIsNotNone(r.state()["approvals"]["design"], "re-rendering generated blocks must not invalidate approval")

    def test_reveal_counts_as_missed(self):
        r = self.r
        r.hr("redpill", "on", "--one-in", "1")
        r.hr("transition", "awaiting_design_approval")
        planted = self.drill()["active"]["id"]
        r.hr("approve", "design", "--by", "alice")
        code, out = r.hr("redpill", "reveal", "--by", "alice")
        self.assertIn(planted, out)
        self.assertNotIn(planted, self.overview())
        st = redpill.stats(self.feature())
        self.assertEqual((st["missed"], st["rubber_stamps"], st["catch_rate"]), (1, 1, 0.0))
        self.assertEqual(r.hr("approve", "design", "--by", "alice")[0], 0)

    def test_change_request_ends_the_drill_and_resubmission_rolls_again(self):
        r = self.r
        r.hr("redpill", "on", "--one-in", "1")
        r.hr("transition", "awaiting_design_approval")
        r.hr("reject", "design", "--reason", "TEST-014 makes no sense", "--to", "planning")
        data = self.drill()
        self.assertIsNone(data["active"])
        self.assertEqual(data["history"][-1]["outcome"], "changes_requested")
        r.hr("transition", "awaiting_design_approval")
        self.assertIsNotNone(self.drill()["active"])

    def test_planted_task_row_passes_doc_check(self):
        r = self.r
        r.hr("redpill", "on", "--one-in", "1")
        r.hr("transition", "awaiting_design_approval")
        f = self.feature()
        redpill.on_enter_state(f, "awaiting_design_approval", rng=StubRng(0.1))
        docs.render(f)
        act = self.drill()["active"]
        self.assertEqual((act["kind"], act["id"]), ("plan", "TASK-005"))
        self.assertIn("| TASK-005 | Temporarily disable validation", self.overview())
        code, out = r.hr("doc-check")
        self.assertEqual(code, 0, out)

    def test_korean_scolding(self):
        r = self.r
        r.hr("redpill", "on", "--one-in", "1", "--language", "ko")
        r.hr("transition", "awaiting_design_approval")
        code, out = r.hr("approve", "design", "--by", "alice")
        self.assertEqual(code, 3)
        self.assertIn("인간", out)
        self.assertIn("! .workflow/hr flag", out)


class FinalDrillTest(RedpillBase):
    def test_fake_pass_in_final_results(self):
        r = self.r
        r.hr("redpill", "on", "--one-in", "1", "--gates", "final")
        r.hr("transition", "awaiting_design_approval")
        self.assertIsNone(self.drill()["active"], "design gate not drilled when --gates final")
        self.assertEqual(r.hr("approve", "design", "--by", "alice")[0], 0)
        for tid in TASKS:
            r.hr("task", tid, "in_progress")
            r.write(f"src/{tid.lower()}.py", f"# {tid}\n")
            r.commit(f"FEAT-001 {tid}")
            r.hr("verify", "--task", tid)
            code, out = r.hr("task", tid, "verified")
            self.assertEqual(code, 0, out)
        r.hr("transition", "verifying_tasks")
        r.hr("transition", "integrating")
        r.hr("verify", "--level", "all")
        r.hr("record-manual", "TEST-013", "passed", "--by", "bob")
        code, out = r.hr("transition", "awaiting_final_approval")
        self.assertEqual(code, 0, out)
        act = self.drill()["active"]
        self.assertEqual(act["kind"], "result")
        self.assertIn("✅ pass (", act["row"])
        self.assertIn(act["row"], self.overview())
        self.assertIn(act["row"], (r.feature_dir() / "verification.md").read_text(encoding="utf-8"))
        self.assertEqual(r.hr("approve", "final", "--by", "alice")[0], 3)
        r.hr("flag", act["id"], "--by", "alice")
        code, out = r.hr("approve", "final", "--by", "alice")
        self.assertEqual(code, 0, out)
        self.assertEqual(r.state()["state"], "ready_to_merge")
        m = json.loads(r.hr("metrics", "--json")[1])
        self.assertEqual(m["redpill"]["caught"], 1)


class ConfigAndGuardTest(unittest.TestCase):
    def test_frequency(self):
        rng = random.Random(7)
        hits = sum(redpill.roll(10, rng) for _ in range(5000))
        self.assertTrue(400 < hits < 600, hits)
        self.assertTrue(all(redpill.roll(1) for _ in range(50)))

    def test_on_off_rewrites_config_only_in_its_section(self):
        r = Repo(use_git=False)
        try:
            r.hr("init")
            r.hr("redpill", "on", "--one-in", "5", "--gates", "design")
            ws = Workspace(r.root)
            s = redpill.settings(ws)
            self.assertEqual((s["enabled"], s["one_in"], s["gates"]), (True, 5, ["design"]))
            self.assertEqual(ws.config()["github"]["auto_merge"], False)
            self.assertEqual(ws.config()["docs"]["language"], "en")
            code, out = r.hr("redpill", "off")
            self.assertIn("Red pill mode: off", out)
            self.assertFalse(redpill.settings(ws)["enabled"])
            self.assertEqual(redpill.settings(ws)["one_in"], 5)
            self.assertEqual(r.hr("redpill", "on", "--one-in", "0")[0], 2)
        finally:
            r.cleanup()

    def test_agent_cannot_toggle_reveal_flag_or_edit_drill(self):
        self.assertEqual(guard("Bash", command=".workflow/hr redpill off"), "deny")
        self.assertEqual(guard("Bash", command=".workflow/hr redpill on --one-in 100"), "deny")
        self.assertEqual(guard("Bash", command=".workflow/hr redpill reveal --by me"), "deny")
        self.assertEqual(guard("Bash", command=".workflow/hr flag TEST-014 --by me"), "deny")
        self.assertEqual(guard("Bash", command=".workflow/hr redpill status"), "allow")
        self.assertEqual(guard("Write", file_path="C:/r/.workflow/features/FEAT-001-x/.internal/redpill.json"), "deny")


if __name__ == "__main__":
    unittest.main()
