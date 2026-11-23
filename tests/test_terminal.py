import subprocess
import sys
import unittest

from helpers import L3_AXES, ONE, PLUGIN, Repo, install_example_plan, no_terminal
from runtime import redpill
from runtime.state.store import Workspace

BY = ("--by", "mallory")
DECISIONS = (
    ("approve", "design", *BY),
    ("record-manual", "TEST-013", "passed", *BY),
    ("unblock", *BY),
    ("flag", "TASK-001", *BY),
    ("floor", "add", "src/auth/**", "L3", *BY),
    ("floor", "remove", "src/pay/**", *BY),
    ("floor", "accept", *BY),
    ("redpill", "on"),
    ("redpill", "on", *BY),
    ("redpill", "off"),
    ("redpill", "reveal", *BY),
)
IMPORTED = "import sys; sys.path.insert(0, sys.argv.pop(1)); from runtime.cli import main; sys.exit(main(sys.argv[1:]))"


class Base(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        r = self.r
        r.hr("init")
        r.hr("new", "Multi-vehicle control", "--slug", "multi-drone")
        r.hr("classify", "--axes", L3_AXES, *ONE, "--flags", "vehicle_command")
        install_example_plan(r)
        r.hr("transition", "planning")
        r.hr("transition", "awaiting_design_approval")
        r.hr("floor", "add", "src/pay/**", "L2", "--by", "owner")
        self.floor_file = r.root / ".human-rights" / "floor.yaml"
        self.floor = self.floor_file.read_text(encoding="utf-8")

    def tearDown(self):
        self.r.cleanup()

    def untouched(self):
        self.assertIsNone(self.r.state()["approvals"]["design"])
        self.assertEqual(self.r.state()["state"], "awaiting_design_approval")
        self.assertEqual(self.floor_file.read_text(encoding="utf-8"), self.floor)
        self.assertFalse(redpill.settings(Workspace(self.r.root))["enabled"])


class NoTerminalTest(Base):
    def test_a_decision_without_a_quote_is_refused(self):
        with no_terminal():
            for argv in DECISIONS:
                code, out = self.r.hr(*argv)
                self.assertEqual(code, 3, (argv, out))
                self.assertIn("terminal", out, argv)
        self.untouched()

    def test_a_quote_needs_no_terminal(self):
        self.r.say("looks good, go ahead")
        with no_terminal():
            code, out = self.r.hr("approve", "design", "--quote", "looks good")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.r.state()["approvals"]["design"]["via"], "chat")

    def test_a_change_request_stays_open(self):
        with no_terminal():
            code, out = self.r.hr("reject", "design", "--reason", "TASK-002 is too wide")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.r.state()["state"], "clarifying")

    def test_at_a_terminal_by_is_enough(self):
        code, out = self.r.hr("approve", "design", "--by", "owner")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.r.state()["approvals"]["design"]["via"], "cli")


class EntryPointTest(Base):
    def run_piped(self, *head):
        proc = subprocess.run([sys.executable, *head, "--root", str(self.r.root), "approve", "design", *BY],
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return proc.returncode, proc.stdout.decode("utf-8", "replace")

    def test_every_way_of_starting_the_runtime_is_refused(self):
        for head in ((str(PLUGIN / "runtime" / "hr.py"),), ("-c", IMPORTED, str(PLUGIN))):
            code, out = self.run_piped(*head)
            self.assertEqual(code, 3, (head, out))
            self.assertIn("terminal", out, head)
        self.untouched()


if __name__ == "__main__":
    unittest.main()
