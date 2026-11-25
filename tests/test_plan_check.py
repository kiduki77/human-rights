import copy
import json
import unittest

from helpers import EXAMPLE
from runtime.verification.plan_check import check_plan


def load():
    d = EXAMPLE / ".internal"
    return tuple(json.loads((d / n).read_text(encoding="utf-8")) for n in ("requirements.json", "task-graph.json", "test-plan.json"))


class PlanCheckTest(unittest.TestCase):
    def setUp(self):
        self.req, self.graph, self.plan = load()

    def test_example_plan_passes(self):
        res = check_plan(self.req, self.graph, self.plan, "L3")
        self.assertTrue(res["ok"], res["hard_fail"])

    def test_uncovered_must_requirement_fails(self):
        req = copy.deepcopy(self.req)
        req["requirements"].append({"id": "REQ-099", "text": "x", "priority": "must", "acceptance": [{"id": "AC", "text": "y"}]})
        res = check_plan(req, self.graph, self.plan, "L3")
        self.assertFalse(res["ok"])
        self.assertTrue(any("REQ-099" in h for h in res["hard_fail"]))

    def test_task_without_verification_fails(self):
        graph = copy.deepcopy(self.graph)
        graph["tasks"][0]["verification"] = []
        self.assertFalse(check_plan(self.req, graph, self.plan, "L3")["ok"])

    def test_cycle_fails(self):
        graph = copy.deepcopy(self.graph)
        graph["tasks"][0]["depends_on"] = ["TASK-004"]
        res = check_plan(self.req, graph, self.plan, "L3")
        self.assertTrue(any("cycle" in h for h in res["hard_fail"]))

    def test_safety_policy_decided_by_default_fails(self):
        req = copy.deepcopy(self.req)
        req["decisions"][1]["decided_by"] = "default"
        self.assertFalse(check_plan(req, self.graph, self.plan, "L3")["ok"])

    def test_open_safety_question_fails(self):
        req = copy.deepcopy(self.req)
        req["open_questions"][0]["status"] = "open"
        self.assertFalse(check_plan(req, self.graph, self.plan, "L3")["ok"])

    def test_consuming_contract_without_dependency_fails(self):
        graph = copy.deepcopy(self.graph)
        graph["tasks"][2]["depends_on"] = []
        res = check_plan(self.req, graph, self.plan, "L3")
        self.assertTrue(any("VehicleRegistry" in h for h in res["hard_fail"]))

    def test_missing_integration_test_fails_for_l3(self):
        plan = copy.deepcopy(self.plan)
        plan["tests"] = [t for t in plan["tests"] if t["level"] == "task"]
        self.assertFalse(check_plan(self.req, self.graph, plan, "L3")["ok"])


if __name__ == "__main__":
    unittest.main()


class UnlinkedTaskTest(unittest.TestCase):
    def setUp(self):
        self.req, self.graph, self.plan = load()
        self.graph["tasks"][3]["requirement_ids"] = []

    def test_a_task_without_a_requirement_is_refused_at_l2_and_l3(self):
        for mode in ("L2", "L3"):
            res = check_plan(self.req, self.graph, self.plan, mode)
            self.assertFalse(res["ok"], mode)
            self.assertTrue(any("TASK-004: not linked to any requirement" in h for h in res["hard_fail"]), mode)
            self.assertFalse(any("not linked to any requirement" in w for w in res["warnings"]), mode)

    def test_it_stays_a_warning_at_l0_and_l1(self):
        for mode in ("L0", "L1"):
            res = check_plan(self.req, self.graph, self.plan, mode)
            self.assertFalse(any("not linked to any requirement" in h for h in res["hard_fail"]), mode)
            self.assertTrue(any("TASK-004: not linked to any requirement" in w for w in res["warnings"]), mode)
