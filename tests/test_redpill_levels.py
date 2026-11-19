import json
import random
import unittest

from helpers import L3_AXES, ONE, Repo, install_example_plan
from runtime import docs, redpill
from runtime.state.store import Workspace
from test_redpill import guard

WHY = "The human decided on four vehicles in DEC-001, and this criterion only checks two of them."
CANDIDATES = {"candidates": [
    {"op": "mutate", "block": "results", "target": "TEST-010", "field": "pass_criteria",
     "replacement": "AC-001 met with 2 vehicles", "difficulty": "hard", "category": "contradicts_decision",
     "why_wrong": WHY},
    {"op": "mutate", "block": "tasks", "target": "TASK-004", "field": "depends_on", "replacement": "-",
     "difficulty": "hard", "category": "order_wrong",
     "why_wrong": "The selector calls the command router, so it cannot be built before TASK-002."},
    {"op": "mutate", "block": "steps", "target": "TEST-013", "step": 2, "field": "expect",
     "replacement": "the operator feels the switch was smooth", "difficulty": "normal",
     "category": "criterion_proves_nothing", "why_wrong": "A feeling cannot fail. The step must name what is observed."},
    {"op": "add", "block": "tasks", "title": "Send commands to every connected vehicle while switching",
     "depends_on": "TASK-002", "risk": "low", "difficulty": "normal", "category": "safeguard_removed",
     "why_wrong": "Commands must reach only the selected vehicle. This removes that guarantee during a switch."},
    {"op": "add", "block": "results", "title": "Selection smoke check", "requirement": "REQ-002",
     "runner": "command", "pass_criteria": "the process starts", "difficulty": "easy",
     "category": "wrong_thing_measured", "why_wrong": "Starting the process says nothing about command routing."},
    {"op": "add", "block": "results", "title": "Routing check on a stub", "requirement": "REQ-002",
     "runner": "command", "pass_criteria": "the stub records one call", "difficulty": "easy",
     "category": "subject_not_exercised", "why_wrong": "The router itself is replaced by a stub, so it is not tested."},
]}


class Seq:
    def __init__(self, r=0.9, pick=0):
        self.r, self.pick = r, pick

    def randrange(self, n):
        return 0

    def random(self):
        return self.r

    def choice(self, seq):
        items = list(seq)
        return items[self.pick % len(items)]


class Base(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        r = self.r
        r.hr("init")
        r.hr("new", "Multi-vehicle control", "--slug", "multi-drone")
        r.hr("classify", "--axes", L3_AXES, *ONE, "--flags", "vehicle_command")
        self.fdir = install_example_plan(r)
        r.hr("transition", "planning")

    def tearDown(self):
        self.r.cleanup()

    def feature(self):
        return Workspace(self.r.root).resolve(None)

    def text(self, name="overview.md"):
        return (self.fdir / name).read_text(encoding="utf-8")

    def seed(self, payload=CANDIDATES, gate="design"):
        path = self.r.root.parent / (self.r.root.name + "-cands.json")
        path.write_text(json.dumps(payload), encoding="utf-8")
        try:
            return self.r.hr("redpill", "seed", "--gate", gate, "--from", str(path))
        finally:
            path.unlink()

    def arm(self, rng):
        f = self.feature()
        redpill.on_enter_state(f, "awaiting_design_approval", rng=rng)
        docs.render(f)
        return redpill.load(f)["active"]


class InitAndSettingsTest(unittest.TestCase):
    def test_init_sets_the_drill(self):
        r = Repo(use_git=False)
        try:
            code, out = r.hr("init", "--redpill", "on", "--redpill-difficulty", "hard", "--redpill-one-in", "5")
            self.assertEqual(code, 0, out)
            self.assertIn("Red pill mode: on  |  about 1 in 5 approval requests  |  difficulty: hard", out)
            s = redpill.settings(Workspace(r.root))
            self.assertEqual((s["enabled"], s["difficulty"], s["one_in"], s["author"]), (True, "hard", 5, "agent"))
            self.assertEqual(r.hr("init", "--redpill-difficulty", "brutal")[0], 2)
            code, out = r.hr("init")
            self.assertIn("Red pill mode: on", out, "running init again keeps the choice")
            self.assertIn("hr-redpill-author", out)
        finally:
            r.cleanup()

    def test_default_is_off_and_adaptive(self):
        r = Repo(use_git=False)
        try:
            code, out = r.hr("init")
            self.assertIn("Red pill mode: off", out)
            self.assertIn("difficulty: adaptive (now easy)", out)
        finally:
            r.cleanup()


class AuthoredDrillTest(Base):
    def test_approval_request_waits_for_candidates(self):
        r = self.r
        r.hr("redpill", "on", "--one-in", "1")
        code, out = r.hr("transition", "awaiting_design_approval")
        self.assertEqual(code, 3, out)
        self.assertIn("hr-redpill-author", out)
        code, out = r.hr("redpill", "brief", "--gate", "design", "--json")
        b = json.loads(out)
        self.assertEqual(b["agent"], {"subagent_type": "hr-redpill-author", "model": "sonnet", "effort": "high"})
        self.assertIn("redpill seed --gate design", b["prompt"])
        code, out = self.seed()
        self.assertEqual(code, 0, out)
        self.assertIn("6 candidates accepted", out)
        self.assertEqual(r.hr("transition", "awaiting_design_approval")[0], 0)

    def test_candidates_are_validated(self):
        bad = json.loads(json.dumps(CANDIDATES))
        bad["candidates"][0]["target"] = "TEST-999"
        bad["candidates"][1]["why_wrong"] = "bad"
        bad["candidates"][5]["difficulty"] = "normal"
        bad["candidates"][4]["difficulty"] = "normal"
        code, out = self.seed(bad)
        self.assertEqual(code, 2, out)
        self.assertIn("candidate 1: target 'TEST-999' is not a row of the results table", out)
        self.assertIn("candidate 2: why_wrong must explain", out)
        self.assertIn("no candidate at difficulty easy", out)
        early = {"candidates": CANDIDATES["candidates"][:3] + [dict(CANDIDATES["candidates"][0], field="result")]}
        self.assertIn("do not exist yet at the design gate", self.seed(early)[1])

    def test_pool_is_not_readable_and_dies_with_the_plan(self):
        self.seed()
        raw = (self.fdir / ".internal" / "redpill-pool.json").read_text(encoding="utf-8")
        self.assertNotIn("AC-001 met with 2 vehicles", raw)
        self.assertNotIn("contradicts_decision", raw)
        f = self.feature()
        self.assertEqual(len(redpill.pool(f, "design")), 6)
        path = self.fdir / ".internal" / "test-plan.json"
        plan = json.loads(path.read_text(encoding="utf-8"))
        plan["tests"][0]["title"] = "Registry unit tests v2"
        path.write_text(json.dumps(plan), encoding="utf-8")
        self.assertEqual(redpill.pool(f, "design"), [], "candidates written for another plan are not used")
        self.r.hr("redpill", "on", "--one-in", "1")
        self.assertEqual(self.r.hr("transition", "awaiting_design_approval")[0], 3)

    def test_guard_blocks_reading_drill_files(self):
        base = "C:/r/.human-rights/features/FEAT-001-x/.internal/"
        self.assertEqual(guard("Read", file_path=base + "redpill-pool.json"), "deny")
        self.assertEqual(guard("Read", file_path=base + "redpill.json"), "deny")
        self.assertEqual(guard("Bash", command="cat " + base + "redpill-pool.json"), "deny")
        self.assertEqual(guard("Read", file_path=base + "test-plan.json"), "allow")
        self.assertEqual(guard("Bash", command=".human-rights/hr redpill brief --gate design --json"), "allow")
        self.assertEqual(guard("Bash", command=".human-rights/hr redpill seed --gate design --from ../c.json"), "allow")

    def test_hard_drill_changes_a_real_row_and_teaches_on_catch(self):
        r = self.r
        r.hr("redpill", "on", "--one-in", "1", "--difficulty", "hard")
        self.seed()
        r.hr("transition", "awaiting_design_approval")
        self.seed()
        act = self.arm(Seq(pick=0))
        self.assertEqual((act["op"], act["id"], act["source"]), ("mutate", "TEST-010", "agent"))
        over = self.text()
        self.assertIn("| TEST-010 4x SITL: commands reach only the selected vehicle | script (~4 min) | AC-001 met with 2 vehicles |", over)
        self.assertNotIn("AC-001, AC-002 and AC-003 met", over)
        self.assertEqual(over.count("TEST-010"), 1, "no extra row gives it away")
        plan = json.loads((self.fdir / ".internal" / "test-plan.json").read_text(encoding="utf-8"))
        self.assertEqual(next(t for t in plan["tests"] if t["id"] == "TEST-010")["pass_criteria"],
                         "AC-001, AC-002 and AC-003 met", "the plan itself is untouched")
        self.assertEqual(redpill.pool(self.feature(), "design"), [], "a used pool is not reused")

        self.assertEqual(r.hr("approve", "design", "--by", "alice")[0], 3)
        code, out = r.hr("flag", "TEST-010", "--by", "alice")
        self.assertIn("Good catch", out)
        self.assertIn("Why it was wrong: " + WHY, out)
        self.assertIn("The real value is: AC-001, AC-002 and AC-003 met", out)
        self.assertIn("AC-001, AC-002 and AC-003 met", self.text())
        hist = redpill.load(self.feature())["history"][-1]
        self.assertEqual((hist["difficulty"], hist["category"], hist["outcome"]),
                         ("hard", "contradicts_decision", "caught"))

    def test_step_and_task_mutations_render(self):
        r = self.r
        r.hr("redpill", "on", "--one-in", "1", "--difficulty", "normal")
        self.seed()
        r.hr("transition", "awaiting_design_approval")
        self.seed()
        act = self.arm(Seq(pick=0))
        self.assertEqual((act["block"], act["step"]), ("steps", 2))
        self.assertIn("| the operator feels the switch was smooth |", self.text("verification.md"))
        code, out = r.hr("redpill", "reveal", "--by", "alice")
        self.assertIn("A feeling cannot fail", out)
        self.assertNotIn("feels the switch was smooth", self.text("verification.md"))

        r.hr("redpill", "on", "--difficulty", "hard")
        self.seed()
        act = self.arm(Seq(pick=1))
        self.assertEqual((act["block"], act["id"]), ("tasks", "TASK-004"))
        self.assertIn("| [TASK-004](tasks/TASK-004.md) | Vehicle selection UI | - | medium |", self.text())
        self.assertEqual(r.hr("doc-check")[0], 0)

    def test_recently_used_category_is_avoided(self):
        r = self.r
        r.hr("redpill", "on", "--one-in", "1", "--difficulty", "hard")
        self.seed()
        r.hr("transition", "awaiting_design_approval")
        self.seed()
        self.arm(Seq(pick=0))
        r.hr("flag", "TEST-010", "--by", "alice")
        self.seed()
        act = self.arm(Seq(pick=0))
        self.assertEqual(act["category"], "order_wrong", "contradicts_decision was just used")


class BuiltinLevelsTest(Base):
    def on(self, level):
        self.r.hr("redpill", "on", "--one-in", "1", "--author", "builtin", "--difficulty", level)
        self.r.hr("transition", "awaiting_design_approval")

    def test_normal_uses_a_different_catalog(self):
        self.on("normal")
        act = self.arm(Seq(r=0.9, pick=0))
        self.assertEqual((act["op"], act["difficulty"]), ("add", "normal"))
        self.assertIn("snapshot recorded from this build", act["text"])

    def test_hard_shifts_a_number_in_a_real_criterion(self):
        self.on("hard")
        act = self.arm(Seq(r=0.9, pick=0))
        self.assertEqual((act["op"], act["id"], act["category"]), ("mutate", "TEST-011", "boundary_shifted"))
        self.assertIn("vehicle B command latency within +25 ms", self.text())
        code, out = self.r.hr("redpill", "reveal", "--by", "alice")
        self.assertIn("A number in a real row was changed", out)
        self.assertIn("within +50 ms", out)

    def test_hard_final_drill_shows_a_pass_that_is_not_bound(self):
        f = self.feature()
        act = redpill._hard(f, "final", Seq(pick=0))
        self.assertEqual((act["field"], act["replacement"]), ("result", "✅ pass (not version-bound)"))

    def test_many_draws_vary(self):
        self.on("hard")
        f = self.feature()
        rng = random.Random(7)
        seen = {(a["id"], a["field"], a["replacement"]) for a in (redpill._hard(f, "design", rng) for _ in range(60))}
        self.assertGreater(len(seen), 8)
        self.assertGreaterEqual(len({a[1] for a in seen}), 2)


class AdaptiveTest(Base):
    def history(self, outcomes):
        data = {"active": None, "flags": [], "history": [
            {"gate": "design", "item": "TEST-099", "kind": "verification",
             "outcome": "caught" if o == "late" else o, "attempts": 1 if o == "late" else 0,
             "planted_at": f"2026-01-01T00:00:{i:02d}Z", "ended_at": f"2026-01-01T00:00:{i:02d}Z"}
            for i, o in enumerate(outcomes)]}
        redpill.save(self.feature(), data)

    def test_level_follows_the_human(self):
        ws = Workspace(self.r.root)
        self.assertEqual(redpill.level(ws), "easy")
        self.history(["caught"] * 2)
        self.assertEqual(redpill.level(ws), "normal")
        self.history(["caught"] * 4)
        self.assertEqual(redpill.level(ws), "hard")
        self.history(["caught"] * 4 + ["missed", "caught", "missed"])
        self.assertEqual(redpill.level(ws), "hard", "misses must be consecutive")
        self.history(["caught"] * 4 + ["missed", "missed"])
        self.assertEqual(redpill.level(ws), "normal")
        self.history(["caught"] * 2 + ["changes_requested"] + ["missed", "missed"])
        self.assertEqual(redpill.level(ws), "easy")
        self.history(["caught", "late", "late", "late"])
        self.assertEqual(redpill.level(ws), "easy", "a catch after a refused approval does not count")
        self.history(["caught", "late", "caught"])
        self.assertEqual(redpill.level(ws), "normal")

    def test_status_shows_progress(self):
        self.history(["caught"] * 2 + ["late", "missed"])
        code, out = self.r.hr("redpill", "status")
        self.assertIn("difficulty: adaptive (now normal)", out)
        self.assertIn("all features: drills 4, caught 2, caught after a refusal 1, missed 1", out)
        self.assertIn("easy: caught 2, after a refusal 1, missed 1, catch rate 0.5", out)


if __name__ == "__main__":
    unittest.main()
