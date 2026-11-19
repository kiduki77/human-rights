import json
import unittest

from helpers import ONE
from helpers import L3_AXES, PASS_CMD, Repo, install_example_plan
from runtime.common import fingerprint
from runtime.state.store import Workspace
from runtime.verification import evidence

AGENT_TEST = {
    "id": "TEST-020", "title": "Browser: vehicle selector", "type": "e2e", "level": "integration",
    "task_ids": ["TASK-004"], "requirement_ids": ["REQ-002"], "command": None, "runner": "agent",
    "environment": "dev stack + browser", "pass_criteria": "both steps observed", "required": True,
    "estimated_seconds": 300,
    "steps": [
        {"do": "Open the GCS and select vehicle B", "expect": "every command button label reads 'B'"},
        {"do": "Enter 0.3 in the interval box", "expect": "the start button is disabled and the range hint shows"},
    ],
}


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

    def edit(self, name, fn):
        path = self.fdir / ".internal" / name
        data = json.loads(path.read_text(encoding="utf-8"))
        fn(data)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def find_test(self, plan, tid):
        return next(t for t in plan["tests"] if t["id"] == tid)

    def feature(self):
        return Workspace(self.r.root).resolve(None)

    def to_executing(self):
        r = self.r
        code, out = r.hr("transition", "awaiting_design_approval")
        self.assertEqual(code, 0, out)
        self.assertEqual(r.hr("approve", "design", "--by", "alice")[0], 0)


class PlanRulesTest(Base):
    def check(self):
        return self.r.hr("plan-check")

    def test_example_plan_passes(self):
        code, out = self.check()
        self.assertEqual(code, 0, out)

    def test_human_test_needs_a_reason_and_step_criteria(self):
        self.edit("test-plan.json", lambda p: self.find_test(p, "TEST-013").pop("human_reason"))
        code, out = self.check()
        self.assertEqual(code, 3, out)
        self.assertIn("TEST-013: run by a human without `human_reason`", out)

        def strip_expect(p):
            t = self.find_test(p, "TEST-013")
            t["human_reason"] = "needs an operator"
            t["steps"][1].pop("expect")
        self.edit("test-plan.json", strip_expect)
        code, out = self.check()
        self.assertIn("TEST-013: step 2 needs both `do` and `expect`", out)

        self.edit("test-plan.json", lambda p: self.find_test(p, "TEST-013").update(steps=[]))
        self.assertIn("needs `steps`", self.check()[1])

    def test_regression_scope_and_flow_flag_are_decided_in_the_plan(self):
        self.edit("test-plan.json", lambda p: p.pop("regression"))
        code, out = self.check()
        self.assertEqual(code, 3)
        self.assertIn("regression: {scope: targeted|full, rationale}", out)
        self.edit("test-plan.json", lambda p: p.update(regression={"scope": "full", "rationale": "shared connection object"}))
        self.edit("task-graph.json", lambda g: g["tasks"][2].pop("changes_flow"))
        code, out = self.check()
        self.assertIn("TASK-003: set `changes_flow`", out)

    def test_static_checks_do_not_count_as_requirement_evidence(self):
        def only_lint(p):
            for t in p["tests"]:
                if "REQ-006" in t.get("requirement_ids", []):
                    t["requirement_ids"].remove("REQ-006")
            p["tests"].append({"id": "TEST-030", "title": "lint", "type": "static", "level": "task", "task_ids": [],
                               "requirement_ids": ["REQ-006"], "command": PASS_CMD, "pass_criteria": "exit 0"})
        self.edit("test-plan.json", only_lint)
        self.edit("task-graph.json", lambda g: [t["requirement_ids"].remove("REQ-006") for t in g["tasks"]
                                                 if "REQ-006" in t.get("requirement_ids", [])])
        code, out = self.check()
        self.assertEqual(code, 3, out)
        self.assertIn("REQ-006", out)

    def test_l2_requires_design_approval_by_default(self):
        r = Repo()
        try:
            axes = json.loads(L3_AXES)
            for k in ("risk", "architecture", "ambiguity", "verification"):
                axes[k]["score"] = 1
            r.hr("init")
            r.hr("new", "Interval field")
            code, out = r.hr("classify", "--axes", json.dumps(axes), *ONE)
            self.assertIn("mode: L2", out)
            self.assertTrue(r.state()["required_gates"]["design"])
            self.assertFalse(r.state()["required_gates"]["final"])
        finally:
            r.cleanup()


class AgentTestFlow(Base):
    def setUp(self):
        super().setUp()
        self.edit("test-plan.json", lambda p: p["tests"].append(dict(AGENT_TEST)))

    def report(self, statuses, evidence_files=True):
        ev = self.fdir / "evidence" / "TEST-020"
        ev.mkdir(parents=True, exist_ok=True)
        steps = []
        for i, status in enumerate(statuses, 1):
            path = ev / f"step-{i}.png"
            if evidence_files:
                path.write_bytes(b"\x89PNG fake screenshot %d" % i)
            steps.append({"status": status, "observed": f"saw the expected result {i}",
                          "evidence": path.relative_to(self.r.root).as_posix() if evidence_files else ""})
        (ev / "report.json").write_text(json.dumps({"by": "hr-tester", "steps": steps, "findings": ["hint text is cut off at 320 px"]}),
                                        encoding="utf-8")

    def test_brief_carries_the_approved_criteria_and_model(self):
        code, out = self.r.hr("test-brief", "TEST-020", "--json")
        self.assertEqual(code, 0, out)
        brief = json.loads(out)
        self.assertIn("PASS ONLY IF: the start button is disabled and the range hint shows", brief["prompt"])
        self.assertEqual(brief["agent"], {"subagent_type": "hr-tester", "model": "sonnet", "effort": "high"})
        self.assertEqual(self.r.hr("test-brief", "TEST-010")[0], 2)

    def test_agent_result_needs_evidence_per_step(self):
        r = self.r
        self.to_executing()
        code, out = r.hr("verify", "--test", "TEST-020")
        self.assertIn("[AGENT] TEST-020", out)

        self.report(["passed", "passed"], evidence_files=False)
        code, out = r.hr("record-agent", "TEST-020")
        self.assertEqual(code, 2)
        self.assertIn("a passed step needs an evidence file", out)

        self.report(["passed"])
        self.assertIn("one result per planned step (2 steps)", r.hr("record-agent", "TEST-020")[1])

        self.report(["passed", "failed"])
        code, out = r.hr("record-agent", "TEST-020")
        self.assertEqual(code, 1, out)
        self.assertIn("failure record FAIL-001", out)

        self.report(["passed", "passed"])
        code, out = r.hr("record-agent", "TEST-020")
        self.assertEqual(code, 0, out)
        self.assertIn("finding: hint text is cut off", out)
        run = self.feature().test_results()["runs"][-1]
        self.assertEqual(run["status"], "agent_passed")
        self.assertTrue(all(s["evidence_sha256"] for s in run["steps"]))
        r.hr("render")
        overview = (self.fdir / "overview.md").read_text(encoding="utf-8")
        self.assertIn("✅ pass (agent-run, per-step evidence)", overview)
        steps = (self.fdir / "verification.md").read_text(encoding="utf-8")
        self.assertIn("| 2 | Enter 0.3 in the interval box | the start button is disabled and the range hint shows |", steps)
        self.assertIn("why a human: judging that a real operator", steps)

    def test_human_result_waits_for_machine_tests(self):
        r = self.r
        self.to_executing()
        code, out = r.hr("record-manual", "TEST-013", "passed", "--by", "bob")
        self.assertEqual(code, 3, out)
        self.assertIn("machine tests come first", out)
        self.assertIn("TEST-020=not_run", out)
        self.assertEqual(r.hr("record-manual", "TEST-013", "failed", "--by", "bob")[0], 0)


class CarryTest(Base):
    def test_result_stays_valid_until_a_covered_path_changes(self):
        r = self.r
        self.to_executing()
        r.hr("verify", "--test", "TEST-012", "TEST-011")
        f = self.feature()

        def status(tid):
            rows = evidence.summarize(f.test_plan(), f.test_results(), fingerprint(r.root))["rows"]
            return next(x for x in rows if x["test"]["id"] == tid)

        self.assertEqual(status("TEST-012")["status"], "passed")
        r.write("docs/notes.md", "unrelated\n")
        r.commit("docs only")
        kept = status("TEST-012")
        self.assertEqual((kept["status"], kept.get("carried")), ("passed", True))
        self.assertEqual(status("TEST-011")["status"], "stale", "no covers: any code change makes it stale")
        r.hr("render")
        self.assertIn("unchanged since", (self.fdir / "overview.md").read_text(encoding="utf-8"))

        r.write("src/link/registry.py", "# changed\n")
        r.commit("touch covered path")
        self.assertEqual(status("TEST-012")["status"], "stale")


class DiagramRulesTest(Base):
    def test_cross_boundary_design_and_flow_tasks_need_diagrams(self):
        r = self.r
        r.hr("render")
        code, out = r.hr("doc-check")
        self.assertEqual(code, 0, out)

        design = self.fdir / "design.md"
        text = design.read_text(encoding="utf-8")
        start, end = text.index("```mermaid"), text.index("```", text.index("```mermaid") + 5) + 3
        design.write_text(text[:start] + text[end:], encoding="utf-8")
        code, out = r.hr("doc-check")
        self.assertEqual(code, 3, out)
        self.assertIn("design.md: this change crosses module or process boundaries", out)
        design.write_text(text, encoding="utf-8")

        task = self.fdir / "tasks" / "TASK-002.md"
        task.write_text(task.read_text(encoding="utf-8").replace("```mermaid", "```text"), encoding="utf-8")
        code, out = r.hr("doc-check")
        self.assertIn("tasks/TASK-002.md: TASK-002 is marked changes_flow", out)


class DecisionsBlockTest(Base):
    def test_overridden_answers_are_shown_first(self):
        def override(req):
            d = req["decisions"][0]
            d.update(answer="2", overrides_user_answer="4", reason="the radio supports two links at once")
        self.edit("requirements.json", override)
        self.r.hr("render")
        overview = (self.fdir / "overview.md").read_text(encoding="utf-8")
        self.assertIn("Changed from your answer - confirm these first", overview)
        self.assertIn("| DEC-001 | Maximum simultaneous vehicles | 4 | **2** | the radio supports two links at once |", overview)
        self.assertLess(overview.index("Changed from your answer"), overview.index("| DEC-002 |"))
        self.assertIn("Assumed for you", overview)


if __name__ == "__main__":
    unittest.main()
