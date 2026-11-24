import json
import subprocess
import sys
import unittest

from helpers import ONE
from helpers import EXAMPLE, PLUGIN, Repo, install_example_plan

GUARD = PLUGIN / "hooks" / "approval_guard.py"


def guard(tool, **inp):
    proc = subprocess.run([sys.executable, str(GUARD)], input=json.dumps({"tool_name": tool, "tool_input": inp}).encode(),
                          stdout=subprocess.PIPE)
    out = proc.stdout.decode().strip()
    return json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out else "allow"


class GuardTest(unittest.TestCase):
    def test_agent_cannot_approve(self):
        self.assertEqual(guard("Bash", command=".human-rights/hr approve design --by me"), "deny")
        self.assertEqual(guard("Bash", command='python3 "/x/runtime/hr.py" -f FEAT-001 approve final --by me'), "deny")
        self.assertEqual(guard("PowerShell", command=".human-rights\\hr.cmd record-manual TEST-1 passed --by me"), "deny")
        self.assertEqual(guard("Bash", command=".human-rights/hr unblock --by me"), "deny")

    def test_agent_cannot_accept_a_review_finding(self):
        self.assertEqual(guard("Bash", command=".human-rights/hr finding accept FND-001 --reason x --by me"), "deny")
        self.assertEqual(guard("Bash", command='.human-rights/hr finding accept FND-001 --reason x --quote "keep it"'), "allow")
        self.assertEqual(guard("Bash", command=".human-rights/hr finding"), "allow")
        self.assertEqual(guard("Bash", command=".human-rights/hr record-review"), "allow")
        self.assertEqual(guard("Write", file_path="C:/repo/.human-rights/features/FEAT-001-x/.internal/findings.json"), "deny")

    def test_normal_commands_pass(self):
        self.assertEqual(guard("Bash", command=".human-rights/hr status"), "allow")
        self.assertEqual(guard("Bash", command=".human-rights/hr verify --level all"), "allow")
        self.assertEqual(guard("Bash", command="cat .human-rights/features/FEAT-001-x/.internal/state.json"), "allow")

    def test_runtime_files_are_not_hand_written(self):
        p = "C:/repo/.human-rights/features/FEAT-001-x/.internal/state.json"
        self.assertEqual(guard("Write", file_path=p), "deny")
        self.assertEqual(guard("Edit", file_path=p.replace("state.json", "test-results.json")), "deny")
        self.assertEqual(guard("Write", file_path=p.replace("state.json", "task-graph.json")), "allow")
        self.assertEqual(guard("Bash", command="echo {} > .human-rights/features/FEAT-001-x/.internal/state.json"), "deny")

    def test_runtime_files_inside_a_group_are_protected_too(self):
        group = "C:/repo/.human-rights/groups/GRP-001-x/.internal/state.json"
        child = "C:/repo/.human-rights/groups/GRP-001-x/features/FEAT-002-y/.internal/events.jsonl"
        nested = "C:/repo/.human-rights/groups/GRP-001-x/groups/GRP-002-y/features/FEAT-003-z/.internal/test-results.json"
        for p in (group, child, nested):
            self.assertEqual(guard("Write", file_path=p), "deny", p)
        self.assertEqual(guard("Write", file_path=group.replace("state.json", "split.json")), "allow")
        self.assertEqual(guard("Edit", file_path="C:/repo/.human-rights/groups/GRP-001-x/overview.md"), "allow")
        self.assertEqual(guard("Bash", command=f"echo {{}} > {child.replace('C:/repo/', '')}"), "deny")
        self.assertEqual(guard("Bash", command=f"cat {child.replace('C:/repo/', '')}"), "allow")


class DocCheckTest(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.r.hr("init")
        self.r.hr("new", "Multi-vehicle control")
        from helpers import L3_AXES

        self.r.hr("classify", "--axes", L3_AXES, *ONE, "--flags", "vehicle_command")

    def tearDown(self):
        self.r.cleanup()

    def test_unfilled_templates_fail(self):
        fdir = self.r.feature_dir()
        for name in ("overview.md", "requirements.md", "design.md", "verification.md"):
            (fdir / name).write_text((PLUGIN / "templates" / name).read_text(encoding="utf-8"), encoding="utf-8")
        code, out = self.r.hr("doc-check")
        self.assertEqual(code, 3)
        self.assertIn("placeholders", out)

    def test_example_docs_pass_after_render(self):
        install_example_plan(self.r)
        code, out = self.r.hr("render")
        self.assertIn("overview.md", out)
        code, out = self.r.hr("doc-check")
        self.assertEqual(code, 0, out)
        text = (self.r.feature_dir() / "overview.md").read_text(encoding="utf-8")
        self.assertIn("| [TASK-001](tasks/TASK-001.md)", text)
        self.assertIn("not run", text)


class SchemaTest(unittest.TestCase):
    def test_example_matches_schemas(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed")
        for data, schema in (("requirements.json", "requirements"), ("task-graph.json", "task-graph"), ("test-plan.json", "test-plan")):
            jsonschema.validate(json.loads((EXAMPLE / ".internal" / data).read_text(encoding="utf-8")),
                                json.loads((PLUGIN / "schemas" / f"{schema}.schema.json").read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
