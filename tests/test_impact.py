import copy
import json
import unittest

from helpers import EXAMPLE, L0_AXES, L3_AXES, ONE, Repo, install_example_plan
from runtime.verification.plan_check import check_plan


def load():
    d = EXAMPLE / ".internal"
    return tuple(json.loads((d / n).read_text(encoding="utf-8")) for n in ("requirements.json", "task-graph.json", "test-plan.json"))


class ImpactPlanTest(unittest.TestCase):
    def setUp(self):
        self.req, self.graph, self.plan = load()

    def hard(self, req, mode="L3"):
        return check_plan(req, self.graph, self.plan, mode)["hard_fail"]

    def consumer(self, **change):
        req = copy.deepcopy(self.req)
        req["impact"]["consumers"] = [{"id": "IMP-900", "where": "src/x.py", "evidence": "src/x.py:1-9", **change}]
        return req

    def test_the_example_states_its_impact(self):
        self.assertEqual(self.hard(self.req), [])

    def test_a_planned_feature_without_impact_fails(self):
        req = copy.deepcopy(self.req)
        del req["impact"]
        for mode in ("L2", "L3"):
            self.assertTrue(any("needs `impact`" in h for h in self.hard(req, mode)), mode)

    def test_small_changes_need_none(self):
        req = copy.deepcopy(self.req)
        del req["impact"]
        for mode in ("L0", "L1"):
            self.assertFalse(any("impact" in h for h in self.hard(req, mode)), mode)

    def test_the_concept_and_the_search_terms_are_required(self):
        req = copy.deepcopy(self.req)
        req["impact"]["concept"] = " "
        req["impact"]["searched"] = []
        hard = self.hard(req)
        self.assertTrue(any("`concept`" in h for h in hard))
        self.assertTrue(any("`searched`" in h for h in hard))

    def test_a_search_that_found_nothing_is_allowed(self):
        req = copy.deepcopy(self.req)
        req["impact"]["consumers"] = []
        self.assertEqual(self.hard(req), [])

    def test_a_place_checked_but_not_changed_needs_a_test(self):
        hard = self.hard(self.consumer(relation="check"))
        self.assertTrue(any("IMP-900" in h and "name a test" in h for h in hard), hard)
        self.assertEqual(self.hard(self.consumer(relation="check", tests=["TEST-012"])), [])

    def test_an_unknown_or_static_test_does_not_cover_it(self):
        hard = self.hard(self.consumer(relation="check", tests=["TEST-404"]))
        self.assertTrue(any("unknown test TEST-404" in h for h in hard), hard)
        plan = copy.deepcopy(self.plan)
        next(t for t in plan["tests"] if t["id"] == "TEST-012")["type"] = "static"
        hard = check_plan(self.consumer(relation="check", tests=["TEST-012"]), self.graph, plan, "L3")["hard_fail"]
        self.assertTrue(any("IMP-900" in h and "static" in h for h in hard), hard)

    def test_a_place_that_changes_needs_a_task(self):
        self.assertTrue(any("name the task" in h for h in self.hard(self.consumer(relation="change"))))
        self.assertTrue(any("unknown task TASK-404" in h for h in self.hard(self.consumer(relation="change", tasks=["TASK-404"]))))
        self.assertEqual(self.hard(self.consumer(relation="change", tasks=["TASK-001"])), [])

    def test_a_place_left_alone_needs_a_reason(self):
        self.assertTrue(any("why it is not affected" in h for h in self.hard(self.consumer(relation="unrelated"))))
        self.assertEqual(self.hard(self.consumer(relation="unrelated", reason="read-only report")), [])

    def test_every_row_needs_a_place_evidence_and_a_known_relation(self):
        req = copy.deepcopy(self.req)
        req["impact"]["consumers"] = [{"id": "IMP-900", "relation": "maybe"}]
        hard = self.hard(req)
        for part in ("`where`", "`evidence`", "`relation`"):
            self.assertTrue(any(part in h for h in hard), part)


class ImpactFlowTest(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.r.hr("init")

    def tearDown(self):
        self.r.cleanup()

    def planned(self):
        r = self.r
        r.hr("new", "Multi-vehicle control", "--slug", "multi-drone")
        r.hr("classify", "--axes", L3_AXES, *ONE, "--flags", "vehicle_command")
        install_example_plan(r)
        r.hr("transition", "planning")

    def test_the_design_shows_the_table(self):
        self.planned()
        code, out = self.r.hr("render")
        self.assertEqual(code, 0, out)
        design = (self.r.feature_dir() / "design.md").read_text(encoding="utf-8")
        self.assertIn("which vehicle a command is sent to", design)
        self.assertIn("| src/telemetry/log.py | writes the target of each command to the flight log | checked, not changed "
                      "| TEST-012 | src/telemetry/log.py:12-30 |", design)
        self.assertIn("not affected | out of scope", design)

    def test_a_design_without_the_block_fails_the_document_check(self):
        self.planned()
        path = self.r.feature_dir() / "design.md"
        path.write_text(path.read_text(encoding="utf-8").replace("<!-- hr:impact:start -->", ""), encoding="utf-8")
        code, out = self.r.hr("doc-check")
        self.assertIn("hr:impact", out)

    def test_a_plan_without_impact_does_not_reach_approval(self):
        self.planned()
        path = self.r.feature_dir() / ".internal" / "requirements.json"
        req = json.loads(path.read_text(encoding="utf-8"))
        del req["impact"]
        path.write_text(json.dumps(req), encoding="utf-8")
        code, out = self.r.hr("transition", "awaiting_design_approval")
        self.assertEqual(code, 3, out)
        self.assertIn("needs `impact`", out)

    def test_classification_records_the_search(self):
        r = self.r
        r.hr("new", "Number the waypoint pins")
        code, out = r.hr("classify", "--axes", L0_AXES)
        self.assertEqual(code, 0, out)
        self.assertIn("no search for other places", out)
        code, out = r.hr("classify", "--axes", L0_AXES, "--concept", "the waypoint's display number",
                         "--searched", "waypoint,sequence,displayNumber", "--consumers", "src/ui/AltitudeCard.tsx")
        self.assertEqual(code, 0, out)
        self.assertIn("other places that use the waypoint's display number: src/ui/AltitudeCard.tsx", out)
        probe = r.state()["routing"]["probe"]
        self.assertEqual(probe["searched"], ["waypoint", "sequence", "displayNumber"])
        code, out = r.hr("classify", "--axes", L0_AXES)
        self.assertEqual(r.state()["routing"]["probe"], probe)

    def test_consumers_without_search_terms_are_refused(self):
        self.r.hr("new", "Number the waypoint pins")
        code, out = self.r.hr("classify", "--axes", L0_AXES, "--consumers", "src/ui/AltitudeCard.tsx")
        self.assertEqual(code, 2, out)
        self.assertIn("--searched", out)

    def test_the_second_search_is_bound_to_the_code(self):
        r = self.r
        self.planned()
        code, out = r.hr("impact", "--recheck")
        self.assertEqual(code, 2, out)
        r.write("src/link/registry.py", "x = 1\n")
        code, out = r.hr("impact", "--recheck", "--searched", "target_system")
        self.assertEqual(code, 3, out)
        self.assertIn("commit first", out)
        sha = r.commit("registry")
        code, out = r.hr("impact", "--recheck", "--searched", "target_system,session")
        self.assertEqual(code, 0, out)
        self.assertEqual(r.state()["impact_recheck"]["commit_sha"], sha)
        r.hr("render")
        design = (r.feature_dir() / "design.md").read_text(encoding="utf-8")
        self.assertIn("Searched again after the code was written", design)
        r.write("src/link/registry.py", "x = 2\n")
        r.commit("registry again")
        r.hr("render")
        design = (r.feature_dir() / "design.md").read_text(encoding="utf-8")
        self.assertIn("has to run again", design)


if __name__ == "__main__":
    unittest.main()
