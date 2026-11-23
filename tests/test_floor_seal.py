import json
import subprocess
import sys
import unittest

from helpers import L0_AXES, PLUGIN, Repo, no_terminal

RULES = '"migrations/**": L2\n"src/auth/**": L3\n'
WEAKER = '"migrations/**": L0\n'


def hook(tool, **inp):
    proc = subprocess.run([sys.executable, str(PLUGIN / "hooks" / "approval_guard.py")],
                          input=json.dumps({"tool_name": tool, "tool_input": inp}).encode(), stdout=subprocess.PIPE)
    return "deny" if b'"deny"' in proc.stdout else "allow"


class Base(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.r.hr("init")
        self.wf = self.r.root / ".human-rights"
        self.file = self.wf / "floor.yaml"
        self.seal = self.wf / "floor.seal"

    def tearDown(self):
        self.r.cleanup()

    def start(self):
        self.r.hr("new", "Tidy the login card")
        return self.r.hr("classify", "--axes", L0_AXES)

    def refused(self, result):
        code, out = result
        self.assertEqual(code, 3, out)
        self.assertIn("[floor]", out)
        self.assertIn("hr floor accept", out)


class SealTest(Base):
    def test_an_owner_change_records_what_the_floor_is(self):
        self.r.hr("floor", "add", "src/auth/**", "L3", "--by", "owner")
        first = json.loads(self.seal.read_text(encoding="utf-8"))
        self.assertEqual((first["by"], first["via"]), ("owner", "cli"))
        self.r.hr("floor", "add", "migrations/**", "L2", "--by", "owner")
        self.assertNotEqual(json.loads(self.seal.read_text(encoding="utf-8"))["rules_sha256"], first["rules_sha256"])
        code, out = self.start()
        self.assertEqual(code, 0, out)

    def test_layout_and_comments_are_not_a_change(self):
        self.r.floor(RULES)
        self.file.write_bytes(b"# reviewed in March\r\n\r\n'src/auth/**':   L3\r\n\"migrations/**\": L2\r\n")
        code, out = self.start()
        self.assertEqual(code, 0, out)

    def test_no_floor_at_all_is_fine(self):
        code, out = self.start()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.r.hr("transition", "executing")[0], 0)


class ChangedBehindTheOwnerTest(Base):
    def test_a_weakened_file_stops_classification(self):
        self.r.floor(RULES)
        self.file.write_text(WEAKER, encoding="utf-8")
        self.refused(self.start())

    def test_a_removed_file_stops_classification(self):
        self.r.floor(RULES)
        self.file.unlink()
        result = self.start()
        self.refused(result)
        self.assertIn("missing", result[1])

    def test_rules_nobody_recorded_stop_classification(self):
        self.r.write(".human-rights/floor.yaml", RULES)
        self.refused(self.start())

    def test_a_change_during_the_feature_stops_the_next_step(self):
        self.r.floor(RULES)
        self.assertEqual(self.start()[0], 0)
        self.file.write_text(WEAKER, encoding="utf-8")
        self.refused(self.r.hr("transition", "executing"))

    def test_both_files_removed_during_the_feature_stop_the_next_step(self):
        self.r.floor(RULES)
        self.assertEqual(self.start()[0], 0)
        self.file.unlink()
        self.seal.unlink()
        self.refused(self.r.hr("transition", "executing"))

    def test_both_files_removed_between_features_are_found_in_history(self):
        self.r.floor(RULES)
        self.r.commit("add the floor")
        self.file.unlink()
        self.seal.unlink()
        self.r.commit("tidy")
        self.refused(self.start())

    def test_an_unreadable_record_counts_as_a_change(self):
        self.r.floor(RULES)
        self.seal.write_text("{", encoding="utf-8")
        self.refused(self.start())

    def test_the_list_says_so(self):
        self.r.floor(RULES)
        self.file.write_text(WEAKER, encoding="utf-8")
        code, out = self.r.hr("floor")
        self.assertEqual(code, 0, out)
        self.assertIn("[floor]", out)

    def test_add_and_remove_wait_for_the_owner_to_accept(self):
        self.r.floor(RULES)
        self.file.write_text(WEAKER, encoding="utf-8")
        before = self.seal.read_text(encoding="utf-8")
        self.refused(self.r.hr("floor", "add", "docs/**", "L1", "--by", "owner"))
        self.refused(self.r.hr("floor", "remove", "migrations/**", "--by", "owner"))
        self.assertEqual(self.file.read_text(encoding="utf-8"), WEAKER)
        self.assertEqual(self.seal.read_text(encoding="utf-8"), before)


class AcceptTest(Base):
    def setUp(self):
        super().setUp()
        self.r.floor(RULES)
        self.file.write_text(WEAKER, encoding="utf-8")
        self.before = self.seal.read_text(encoding="utf-8")

    def test_accept_needs_a_human(self):
        code, out = self.r.hr("floor", "accept")
        self.assertEqual(code, 2, out)
        self.r.say("ship it")
        code, out = self.r.hr("floor", "accept", "--quote", "yes, I edited the floor")
        self.assertEqual(code, 3, out)
        with no_terminal():
            code, out = self.r.hr("floor", "accept", "--by", "mallory")
        self.assertEqual(code, 3, out)
        self.assertEqual(self.seal.read_text(encoding="utf-8"), self.before)
        self.refused(self.start())

    def test_the_owner_accepts_a_hand_edit(self):
        self.r.say("yes, I edited the floor myself")
        code, out = self.r.hr("floor", "accept", "--quote", "I edited the floor myself")
        self.assertEqual(code, 0, out)
        self.assertIn("L0  migrations/**", out)
        self.assertEqual(json.loads(self.seal.read_text(encoding="utf-8"))["via"], "chat")
        code, out = self.start()
        self.assertEqual(code, 0, out)

    def test_the_owner_accepts_having_no_floor(self):
        self.file.unlink()
        self.seal.unlink()
        self.r.hr("new", "Tidy the login card")
        code, out = self.r.hr("floor", "accept", "--by", "owner")
        self.assertEqual(code, 0, out)
        self.assertIn("0 rules", out)
        code, out = self.r.hr("classify", "--axes", L0_AXES)
        self.assertEqual(code, 0, out)


class HookTest(unittest.TestCase):
    def test_the_record_is_the_owners_too(self):
        self.assertEqual(hook("Write", file_path="C:/repo/.human-rights/floor.seal"), "deny")
        self.assertEqual(hook("Bash", command="rm .human-rights/floor.seal"), "deny")
        self.assertEqual(hook("Read", file_path="C:/repo/.human-rights/floor.seal"), "allow")

    def test_accepting_is_a_human_decision(self):
        self.assertEqual(hook("Bash", command=".human-rights/hr floor accept"), "deny")
        self.assertEqual(hook("Bash", command='.human-rights/hr floor accept --quote "I edited it"'), "allow")


if __name__ == "__main__":
    unittest.main()
