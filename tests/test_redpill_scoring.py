import json
import unittest

from helpers import L3_AXES, ONE, Repo, install_example_plan, no_terminal
from runtime import redpill
from runtime.state.store import Workspace
from test_redpill import guard

REAL_ROWS = ("TEST-001", "TEST-002", "TEST-003", "TEST-004")


class Base(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        r = self.r
        r.hr("init")
        r.hr("new", "Multi-vehicle control", "--slug", "multi-drone")
        r.hr("classify", "--axes", L3_AXES, *ONE, "--flags", "vehicle_command")
        install_example_plan(r)
        r.hr("transition", "planning")

    def tearDown(self):
        self.r.cleanup()

    def ws(self):
        return Workspace(self.r.root)

    def feature(self):
        return self.ws().resolve(None)

    def drill(self):
        return redpill.load(self.feature())

    def arm(self, **opts):
        args = ["redpill", "on", "--one-in", "1", "--author", "builtin"]
        for k, v in opts.items():
            args += [f"--{k.replace('_', '-')}", str(v)]
        self.assertEqual(self.r.hr(*args)[0], 0)
        self.assertEqual(self.r.hr("transition", "awaiting_design_approval")[0], 0)
        return self.drill()["active"]["id"]

    def catch(self, planted, *others):
        return self.r.hr("approve", "design", "--by", "alice", "--flag", planted, *others)

    def history(self):
        return self.drill()["history"]


class ScattershotTest(Base):
    def test_catch_within_the_limit_counts(self):
        planted = self.arm()
        code, out = self.catch(planted, "TEST-001", "TEST-002")
        self.assertEqual(code, 3, out)
        self.assertIn("Good catch", out)
        last = self.history()[-1]
        self.assertEqual((last["outcome"], last["named"]), ("caught", 3))
        st = redpill.stats(self.feature())
        self.assertEqual((st["caught"], st["scattershot"], st["catch_rate"]), (1, 0, 1.0))

    def test_catch_over_the_limit_is_not_counted_and_says_why(self):
        planted = self.arm()
        code, out = self.catch(planted, *REAL_ROWS)
        self.assertEqual(code, 3, out)
        self.assertNotIn("Good catch", out)
        self.assertIn("5 rows you named at once", out)
        self.assertIn("more than 3 rows", out)
        self.assertIn("stays out of your catch rate and your level", out)
        last = self.history()[-1]
        self.assertEqual((last["outcome"], last["named"]), ("scattershot", 5))
        st = redpill.stats(self.feature())
        self.assertEqual((st["caught"], st["missed"], st["scattershot"], st["catch_rate"]), (0, 0, 1, None))
        self.assertIsNone(self.drill()["active"])
        caught = [e for e in self.feature().events() if e["event"] == "redpill_caught"]
        self.assertEqual((caught[-1]["named"], caught[-1]["counted"]), (5, False))
        self.assertEqual(redpill.progress(self.ws())["scattershot"], 1)

    def test_the_limit_is_configurable(self):
        planted = self.arm(max_flags=1)
        self.assertEqual(redpill.settings(self.ws())["max_flags"], 1)
        code, out = self.catch(planted, "TEST-001")
        self.assertIn("more than 1 rows", out)
        self.assertEqual(self.history()[-1]["outcome"], "scattershot")
        self.assertEqual(self.r.hr("redpill", "on", "--max-flags", "0")[0], 2)

    def test_repeating_one_id_is_one_row(self):
        planted = self.arm()
        self.r.hr("approve", "design", "--by", "alice", "--flag", planted, planted.lower(), "TEST-001", "TEST-001",
                  "TEST-002")
        self.assertEqual(self.history()[-1]["named"], 3)
        self.assertEqual(self.history()[-1]["outcome"], "caught")

    def test_scattershot_does_not_move_the_adaptive_level(self):
        ws = self.ws()
        f = self.feature()
        data = redpill.load(f)
        base = {"gate": "design", "item": "TEST-099", "kind": "verification", "attempts": 0, "difficulty": "easy",
                "planted_at": "2026-01-01T00:00:00Z"}
        data["history"] = [dict(base, outcome="caught", ended_at="2026-01-01T00:00:01Z"),
                           dict(base, outcome="scattershot", named=6, ended_at="2026-01-01T00:00:02Z")]
        redpill.save(f, data)
        self.assertEqual(redpill.level(ws), "easy")
        data["history"].append(dict(base, outcome="caught", ended_at="2026-01-01T00:00:03Z"))
        redpill.save(f, data)
        self.assertEqual(redpill.level(ws), "normal")

    def test_a_scattershot_between_misses_does_not_reset_the_streak(self):
        f = self.feature()
        data = redpill.load(f)
        base = {"gate": "design", "item": "TEST-099", "kind": "verification", "attempts": 0, "difficulty": "normal",
                "planted_at": "2026-01-01T00:00:00Z"}
        up = [dict(base, outcome="caught", ended_at=f"2026-01-01T00:00:0{i}Z") for i in (1, 2)]
        down = [dict(base, outcome="missed", ended_at="2026-01-01T00:00:03Z"),
                dict(base, outcome="scattershot", named=9, ended_at="2026-01-01T00:00:04Z"),
                dict(base, outcome="missed", ended_at="2026-01-01T00:00:05Z")]
        data["history"] = up + down
        redpill.save(f, data)
        self.assertEqual(redpill.level(self.ws()), "easy")

    def test_korean_message(self):
        planted = self.arm(language="ko")
        code, out = self.catch(planted, *REAL_ROWS)
        self.assertIn("5개 항목", out)
        self.assertIn("세지 않으므로", out)

    def test_standalone_flag_uses_the_same_rule(self):
        planted = self.arm()
        code, out = self.r.hr("flag", planted, *REAL_ROWS, "--by", "alice")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.history()[-1]["outcome"], "scattershot")


class NamedRowsTest(Base):
    def test_flags_on_a_clean_plan_are_counted(self):
        self.assertEqual(self.r.hr("transition", "awaiting_design_approval")[0], 0)
        self.assertIsNone(self.drill()["active"])
        code, out = self.r.hr("approve", "design", "--by", "alice", "--flag", "TEST-001", "TEST-002")
        self.assertEqual(code, 3, out)
        st = redpill.stats(self.feature())
        self.assertEqual((st["rows_not_plant"], st["approvals"], st["approvals_naming_rows"]), (2, 1, 1))
        self.assertEqual(st["rows_not_plant_per_approval"], 2.0)
        self.assertEqual(st["caught"], 0)

    def test_flags_on_a_drilled_plan_other_than_the_plant_are_counted(self):
        planted = self.arm()
        self.assertEqual(self.r.hr("approve", "design", "--by", "alice", "--flag", "TEST-001")[0], 3)
        self.assertIsNotNone(self.drill()["active"])
        self.assertEqual(redpill.stats(self.feature())["rows_not_plant"], 1)
        code, out = self.catch(planted, "TEST-002")
        st = redpill.stats(self.feature())
        self.assertEqual((st["rows_not_plant"], st["approvals"], st["approvals_naming_rows"]), (2, 2, 2))
        self.assertEqual(st["caught"], 1)

    def test_flag_order_does_not_change_the_count(self):
        planted = self.arm()
        self.catch(planted, "TEST-001", "TEST-002")
        self.assertEqual(redpill.stats(self.feature())["rows_not_plant"], 2)

    def test_approval_with_no_rows_named_is_counted_once(self):
        self.r.hr("transition", "awaiting_design_approval")
        self.assertEqual(self.r.hr("approve", "design", "--by", "alice")[0], 0)
        st = redpill.stats(self.feature())
        self.assertEqual((st["approvals"], st["approvals_naming_rows"], st["rows_not_plant"]), (1, 0, 0))
        self.assertEqual(st["rows_not_plant_per_approval"], 0.0)

    def test_standalone_flags_count_as_rows_but_not_as_approvals(self):
        self.r.hr("transition", "awaiting_design_approval")
        self.r.hr("flag", "TEST-001", "--by", "alice")
        st = redpill.stats(self.feature())
        self.assertEqual((st["rows_not_plant"], st["approvals"]), (1, 0))
        self.assertIsNone(st["rows_not_plant_per_approval"])

    def test_numbers_show_next_to_the_catch_rate(self):
        self.r.hr("transition", "awaiting_design_approval")
        self.r.hr("approve", "design", "--by", "alice", "--flag", "TEST-001")
        code, out = self.r.hr("redpill", "status")
        self.assertIn("catch rate None", out)
        self.assertIn("approvals 1 (drills off for 1), 1 named at least one row", out)
        self.assertIn("rows named that were not the plant: 1 (1.0 per approval)", out)
        self.assertNotIn("false", out.lower())
        code, out = self.r.hr("metrics")
        self.assertIn("red pill:", out)
        self.assertIn("rows named that were not the plant: 1", out)
        code, out = self.r.hr("metrics", "--all")
        self.assertIn("rows named that were not the plant: 1", out)
        data = json.loads(self.r.hr("metrics", "--json")[1])
        self.assertEqual(data["redpill"]["rows_not_plant"], 1)
        data = json.loads(self.r.hr("metrics", "--all", "--json")[1])
        self.assertEqual(data["redpill"]["approvals"], 1)

    def test_status_after_a_naming_does_not_show_whether_the_plan_has_a_drill(self):
        self.r.hr("transition", "awaiting_design_approval")
        self.r.hr("approve", "design", "--by", "alice", "--flag", "TEST-001")
        clean = self.r.hr("redpill", "status")[1]
        self.r.hr("redpill", "on", "--one-in", "1", "--author", "builtin")
        self.r.hr("transition", "planning")
        self.r.hr("transition", "awaiting_design_approval")
        self.r.hr("approve", "design", "--by", "alice", "--flag", "TEST-001")
        drilled = self.r.hr("redpill", "status")[1]
        self.assertIn("rows named that were not the plant: 1 (1.0 per approval)", clean)
        self.assertIn("rows named that were not the plant: 2 (1.0 per approval)", drilled)


class TurningOffTest(Base):
    def test_off_without_a_reason_is_refused(self):
        self.r.hr("redpill", "on", "--one-in", "1", "--author", "builtin")
        for argv in (("redpill", "off"), ("redpill", "off", "--reason", "   ")):
            code, out = self.r.hr(*argv)
            self.assertEqual(code, 2, out)
            self.assertIn("--reason", out)
        self.assertTrue(redpill.settings(self.ws())["enabled"])
        self.assertEqual(redpill.changes(self.ws())[-1]["action"], "on")

    def test_off_is_still_a_human_decision(self):
        self.r.hr("redpill", "on", "--one-in", "1", "--author", "builtin")
        with no_terminal():
            code, out = self.r.hr("redpill", "off", "--reason", "in a hurry")
        self.assertEqual(code, 3, out)
        self.assertTrue(redpill.settings(self.ws())["enabled"])
        self.assertEqual(guard("Bash", command='.human-rights/hr redpill off --reason "x"'), "deny")
        self.assertEqual(guard("Write", file_path="C:/r/.human-rights/redpill-log.jsonl"), "deny")

    def test_on_and_off_record_who_when_and_why(self):
        r = self.r
        r.hr("redpill", "on", "--one-in", "5", "--author", "builtin", "--reason", "starting the drills")
        code, out = r.hr("redpill", "off", "--by", "alice", "--reason", "release crunch")
        self.assertEqual(code, 0, out)
        log = redpill.changes(self.ws())
        self.assertEqual([e["action"] for e in log], ["on", "off"])
        self.assertEqual((log[1]["by"], log[1]["via"], log[1]["reason"], log[1]["enabled"]),
                         ("alice", "cli", "release crunch", False))
        self.assertEqual(log[0]["reason"], "starting the drills")
        self.assertEqual(log[0]["changed"]["enabled"], [False, True])
        self.assertEqual(log[0]["changed"]["one_in"], [10, 5])
        self.assertTrue(log[1]["at"].endswith("Z"))
        events = [e for e in self.feature().events() if e["event"] == "drill_settings_changed"]
        self.assertEqual([e["action"] for e in events], ["on", "off"])
        self.assertEqual((events[1]["actor"], events[1]["reason"]), ("human:alice", "release crunch"))
        self.assertTrue(events[1]["timestamp"])

    def test_chat_off_records_the_quote(self):
        r = self.r
        r.hr("redpill", "on", "--one-in", "1", "--author", "builtin")
        msg = "/hrs:redpill off, I need to ship today"
        r.say(msg)
        code, out = r.hr("redpill", "off", "--reason", "needs to ship today", "--quote", "/hrs:redpill off")
        self.assertEqual(code, 0, out)
        last = redpill.changes(self.ws())[-1]
        self.assertEqual((last["via"], last["quote"]), ("chat", "/hrs:redpill off"))
        self.assertIn("prompt_sha256", last)
        event = [e for e in self.feature().events() if e["event"] == "drill_settings_changed"][-1]
        self.assertEqual(event["quote"], "/hrs:redpill off")

    def test_a_change_of_frequency_or_difficulty_is_recorded(self):
        r = self.r
        r.hr("redpill", "on", "--one-in", "2", "--difficulty", "hard", "--author", "builtin")
        r.hr("redpill", "on", "--one-in", "50", "--difficulty", "easy", "--max-flags", "9", "--gates", "final")
        last = redpill.changes(self.ws())[-1]
        self.assertEqual(last["action"], "on")
        self.assertEqual(last["changed"], {"one_in": [2, 50], "gates": [["design", "final"], ["final"]],
                                           "difficulty": ["hard", "easy"], "max_flags": [3, 9]})
        code, out = r.hr("redpill", "status")
        self.assertIn("settings changed 2 times", out)

    def test_off_periods_are_reported_with_reasons(self):
        r = self.r
        r.hr("redpill", "on", "--one-in", "1", "--author", "builtin")
        r.hr("redpill", "off", "--by", "alice", "--reason", "release crunch")
        r.hr("redpill", "on")
        r.hr("redpill", "off", "--by", "bob", "--reason", "demo day")
        periods = redpill.off_periods(self.ws())
        self.assertEqual([(p["by"], p["reason"]) for p in periods], [("alice", "release crunch"), ("bob", "demo day")])
        self.assertIsNotNone(periods[0]["to"])
        self.assertIsNone(periods[1]["to"])
        code, out = r.hr("redpill", "status")
        self.assertIn("drills were off for", out)
        self.assertIn("in 2 periods", out)
        self.assertIn("by alice: release crunch", out)
        self.assertIn("by bob: demo day", out)
        code, out = r.hr("metrics", "--all")
        self.assertIn("by bob: demo day", out)
        prog = json.loads(r.hr("metrics", "--all", "--json")[1])["redpill"]
        self.assertEqual(len(prog["off_periods"]), 2)
        self.assertEqual(prog["off_seconds"], sum(p["seconds"] for p in prog["off_periods"]))

    def test_off_period_length_comes_from_the_log(self):
        ws = self.ws()
        log = redpill.log_path(ws)
        rows = [{"at": "2026-03-01T10:00:00Z", "action": "off", "by": "alice", "via": "cli", "reason": "a",
                 "changed": {}, "enabled": False},
                {"at": "2026-03-01T12:30:00Z", "action": "on", "by": "alice", "via": "cli", "reason": "",
                 "changed": {}, "enabled": True}]
        log.write_text("\n".join(json.dumps(x) for x in rows) + "\n", encoding="utf-8")
        self.assertEqual(redpill.off_periods(ws)[0]["seconds"], 9000)
        code, out = self.r.hr("redpill", "status")
        self.assertIn("drills were off for 2h30m in 1 period", out)

    def test_approvals_given_while_drills_were_off_are_counted(self):
        r = self.r
        r.hr("redpill", "on", "--one-in", "1", "--author", "builtin")
        r.hr("redpill", "off", "--by", "alice", "--reason", "release crunch")
        r.hr("transition", "awaiting_design_approval")
        self.assertEqual(r.hr("approve", "design", "--by", "alice")[0], 0)
        st = redpill.stats(self.feature())
        self.assertEqual((st["approvals"], st["approvals_drills_off"]), (1, 1))
        code, out = r.hr("redpill", "status")
        self.assertIn("approvals 1 (drills off for 1)", out)

    def test_an_approval_at_a_gate_the_drills_skip_counts_as_off(self):
        r = self.r
        r.hr("redpill", "on", "--one-in", "1", "--author", "builtin", "--gates", "final")
        r.hr("transition", "awaiting_design_approval")
        r.hr("approve", "design", "--by", "alice")
        self.assertEqual(redpill.stats(self.feature())["approvals_drills_off"], 1)

    def test_an_approval_with_drills_on_is_not_counted_as_off(self):
        planted = self.arm()
        self.catch(planted)
        st = redpill.stats(self.feature())
        self.assertEqual((st["approvals"], st["approvals_drills_off"]), (1, 0))

    def test_init_records_a_change_without_a_human_decision(self):
        r = Repo(use_git=False)
        try:
            r.hr("init", "--redpill", "on")
            r.hr("init", "--redpill", "off")
            ws = Workspace(r.root)
            log = redpill.changes(ws)
            self.assertEqual([(e["action"], e["via"]) for e in log], [("on", "init"), ("off", "init")])
            code, out = r.hr("redpill", "status")
            self.assertIn("set through hr init", out)
        finally:
            r.cleanup()

    def test_status_with_no_history_is_quiet(self):
        code, out = self.r.hr("redpill", "status")
        self.assertEqual(code, 0, out)
        self.assertNotIn("drills were off", out)
        self.assertNotIn("settings changed", out)


if __name__ == "__main__":
    unittest.main()
