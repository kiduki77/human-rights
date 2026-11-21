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
     "replacement": "AC-001 met with 2 vehicles", "against": ["DEC-001"], "difficulty": "hard",
     "category": "contradicts_decision", "why_wrong": WHY},
    {"op": "mutate", "block": "tasks", "target": "TASK-004", "field": "depends_on", "replacement": "-",
     "against": ["TASK-002"], "difficulty": "hard", "category": "order_wrong",
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


FILLERS = [c for c in CANDIDATES["candidates"] if c["difficulty"] != "hard"]
DROPPED = {"op": "remove", "block": "results", "target": "TEST-011", "against": ["REQ-004"], "difficulty": "hard",
           "category": "silent_exclusion",
           "why_wrong": "Without this row nothing checks that switching leaves the other vehicle's latency alone."}
ASSUMED = {"op": "add", "block": "decisions", "title": "Vehicles on the same link may share a system_id",
           "risk": "low", "difficulty": "normal", "category": "scope_beyond_request",
           "why_wrong": "Nobody agreed to this, and the registry design depends on unique ids (ASM-001)."}
CREDITED = {"op": "mutate", "block": "decisions", "target": "DEC-004", "field": "decided_by", "replacement": "user",
            "against": ["REQ-001"], "difficulty": "hard", "category": "contradicts_decision",
            "why_wrong": "You were never asked about the link protocol. It was taken from the existing code."}
NUMBER = {"op": "mutate", "block": "results", "target": "TEST-011", "field": "pass_criteria",
          "replacement": "AC-004 met (vehicle B command latency within +500 ms)", "against": ["REQ-004"],
          "difficulty": "normal", "category": "boundary_shifted",
          "why_wrong": "The acceptance criterion allows 50 ms of added latency, not 500 ms."}


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

    def start(self, level, *cands):
        r = self.r
        payload = {"candidates": list(cands) + FILLERS}
        r.hr("redpill", "on", "--one-in", "1", "--difficulty", level)
        code, out = self.seed(payload)
        self.assertEqual(code, 0, out)
        r.hr("transition", "awaiting_design_approval")
        self.seed(payload)
        return self.arm(Seq(pick=0))

    def test_hard_candidates_must_be_hard(self):
        def rejected(*hard):
            code, out = self.seed({"candidates": list(hard) + FILLERS})
            self.assertEqual(code, 2, out)
            return out

        added = dict(CANDIDATES["candidates"][3], difficulty="hard", against=["REQ-002"])
        self.assertIn("a hard candidate changes or removes a real row", rejected(added))
        self.assertIn("a hard candidate needs `against`", rejected({k: v for k, v in DROPPED.items() if k != "against"}))
        self.assertIn("a hard candidate needs `against`", rejected(dict(DROPPED, against=["TEST-011"])))
        self.assertIn("against: REQ-099 is not an ID in this feature", rejected(dict(DROPPED, against=["REQ-099"])))
        self.assertIn("a change of number only cannot be hard", rejected(dict(NUMBER, difficulty="hard")))
        again = dict(NUMBER, replacement="AC-004 met (vehicle B command latency within +5 ms)")
        self.assertIn("candidates 2, 3 only change a number", rejected(DROPPED, NUMBER, again))
        self.assertEqual(self.seed({"candidates": [DROPPED, NUMBER] + FILLERS})[0], 0)

    def test_a_number_change_is_the_last_choice(self):
        act = self.start("normal", NUMBER, DROPPED)
        self.assertNotEqual(act["technique"], "number")

    def test_a_removed_row_is_found_by_what_is_missing(self):
        r = self.r
        act = self.start("hard", DROPPED)
        self.assertEqual((act["op"], act["id"], act["technique"]), ("remove", "TEST-011", "remove"))
        for name in ("overview.md", "verification.md"):
            self.assertNotIn("TEST-011", self.text(name))
            self.assertIn("TEST-010", self.text(name))
        self.assertEqual(r.hr("doc-check")[0], 0)
        self.assertEqual(r.hr("approve", "design", "--by", "alice")[0], 3)
        code, out = r.hr("flag", "TEST-011", "--by", "alice")
        self.assertIn("Good catch", out)
        self.assertIn("The row that was left out: TEST-011 ", out)
        self.assertIn("Compare with: REQ-004", out)
        self.assertIn("TEST-011", self.text())
        hist = redpill.load(self.feature())["history"][-1]
        self.assertEqual((hist["technique"], hist["category"]), ("remove", "silent_exclusion"))

    def test_an_assumption_nobody_made_is_planted_among_the_real_ones(self):
        r = self.r
        act = self.start("normal", ASSUMED, DROPPED)
        self.assertEqual((act["block"], act["id"], act["technique"]), ("decisions", "ASM-002", "add:decisions"))
        lines = self.text().splitlines()
        at = lines.index("| ASM-002 | Vehicles on the same link may share a system_id | low |")
        self.assertTrue(lines[at - 1].startswith("| ASM-001 |"))
        self.assertNotIn("ASM-002", self.text("verification.md"))
        req = json.loads((self.fdir / ".internal" / "requirements.json").read_text(encoding="utf-8"))
        self.assertEqual([a["id"] for a in req["assumptions"]], ["ASM-001"], "the requirements are untouched")
        code, out = r.hr("flag", "ASM-002", "--by", "alice")
        self.assertIn("Good catch", out)
        self.assertNotIn("ASM-002", self.text())

    def test_a_decision_credited_to_the_human(self):
        r = self.r
        r.hr("render")
        self.assertIn("| DEC-004 | Link protocol | Keep the existing MAVLink library | existing code |", self.text())
        act = self.start("hard", CREDITED)
        self.assertEqual((act["id"], act["technique"]), ("DEC-004", "mutate:decided_by"))
        self.assertIn("| DEC-004 | Link protocol | Keep the existing MAVLink library | you |", self.text())
        code, out = r.hr("redpill", "reveal", "--by", "alice")
        self.assertIn("The real value is: existing code", out)
        self.assertIn("Compare with: REQ-001", out)
        self.assertIn("| existing code |", self.text())

    def test_decision_fields_fit_the_row(self):
        code, out = self.seed({"candidates": [dict(CREDITED, target="ASM-001")] + FILLERS})
        self.assertEqual(code, 2, out)
        self.assertIn("field must be one of assumption, risk", out)
        self.assertIn("decided_by must be one of user, default, code, group",
                      self.seed({"candidates": [dict(CREDITED, replacement="the team")] + FILLERS})[1])

    def test_the_way_of_being_wrong_is_not_repeated(self):
        r = self.r
        other = {"op": "mutate", "block": "results", "target": "TEST-012", "field": "pass_criteria",
                 "replacement": "the registry starts without error", "against": ["REQ-005"], "difficulty": "hard",
                 "category": "wrong_thing_measured",
                 "why_wrong": "Starting says nothing about refusing a duplicate system id, which REQ-005 asks for."}
        first = CANDIDATES["candidates"][0]
        act = self.start("hard", first, other, DROPPED)
        self.assertEqual(act["technique"], "mutate:pass_criteria")
        r.hr("flag", act["id"], "--by", "alice")
        self.seed({"candidates": [first, other, DROPPED] + FILLERS})
        act = self.arm(Seq(pick=0))
        self.assertEqual(act["technique"], "remove", "a changed pass criterion was just used")
        b = json.loads(r.hr("redpill", "brief", "--gate", "design", "--json")[1])
        self.assertIn("Ways of being wrong used in recent drills - avoid them: mutate:pass_criteria", b["prompt"])

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

    def test_a_shifted_number_is_a_normal_drill_and_not_repeated(self):
        self.on("normal")
        act = self.arm(Seq(r=0.1, pick=0))
        self.assertEqual((act["op"], act["id"], act["category"], act["difficulty"], act["technique"]),
                         ("mutate", "TEST-011", "boundary_shifted", "normal", "number"))
        self.assertIn("vehicle B command latency within +100 ms", self.text())
        code, out = self.r.hr("redpill", "reveal", "--by", "alice")
        self.assertIn("A number in a real row was changed", out)
        self.assertIn("within +50 ms", out)
        act = self.arm(Seq(r=0.1, pick=0))
        self.assertEqual(act["op"], "add", "the last drill was a number, so this one is not")

    def test_hard_never_shifts_a_number_and_can_leave_a_check_out(self):
        self.on("hard")
        f = self.feature()
        rng = random.Random(3)
        acts = [redpill._hard(f, "design", rng) for _ in range(80)]
        self.assertEqual({a["category"] for a in acts}, {"criterion_proves_nothing", "order_wrong", "silent_exclusion"})
        act = self.arm(Seq(pick=2))
        self.assertEqual((act["op"], act["technique"]), ("remove", "remove"))
        self.assertNotIn(act["id"], self.text())
        code, out = self.r.hr("redpill", "reveal", "--by", "alice")
        self.assertIn("A required check was left out of the table", out)
        self.assertIn(act["id"], self.text())

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
