import json
import subprocess
import sys
import unittest
from unittest import mock

import helpers
from helpers import L0_AXES, L3_AXES, ONE, Repo
from runtime.config import DEFAULTS, parse_simple_yaml
from runtime.routing import floor
from runtime.routing.router import route
from runtime.state.store import Workspace

AXES = ("ambiguity", "scope", "architecture", "risk", "verification", "dependency")
RULES = '"migrations/**": L2\n"src/auth/**": L3\n"**/secrets/*": L3\n'


def axes(**scores):
    return {k: {"score": scores.get(k, 0), "basis": "test", "confirmed": True, "confidence": "high"} for k in AXES}


def hit(pattern, level, *paths):
    return {"pattern": pattern, "level": level, "paths": list(paths)}


class QuotedKeysTest(unittest.TestCase):
    def test_quoted_glob_keys_parse_without_pyyaml(self):
        text = '# owner rules\n"**/secrets/*": L3\n\'migrations/**\': L2   # keep\nplain/**: L1\n'
        self.assertEqual(parse_simple_yaml(text), {"**/secrets/*": "L3", "migrations/**": "L2", "plain/**": "L1"})


class RouteFloorTest(unittest.TestCase):
    def test_floor_raises_the_scored_level_and_says_from_what(self):
        r = route(axes(), [], DEFAULTS, [hit("src/auth/**", "L3", "src/auth/login.py")])
        self.assertEqual(r["mode"], "L3")
        self.assertEqual(r["floor"]["raised_from"], "L0")
        self.assertIn("owner floor `src/auth/**` (L3) raised L0 -> L3: src/auth/login.py", r["reasons"])
        self.assertEqual([g["gate"] for g in r["gates"]], ["design", "final"])

    def test_the_highest_hit_wins(self):
        r = route(axes(), [], DEFAULTS, [hit("a/**", "L1", "a/x"), hit("b/**", "L2", "b/y")])
        self.assertEqual((r["mode"], r["floor"]["raised_from"]), ("L2", "L0"))

    def test_floor_below_the_scored_level_changes_nothing(self):
        r = route(axes(risk=3), [], DEFAULTS, [hit("docs/**", "L2", "docs/a.md")])
        self.assertEqual(r["mode"], "L3")
        self.assertIsNone(r["floor"]["raised_from"])
        self.assertEqual(len(r["floor"]["hits"]), 1)
        self.assertFalse(any("floor" in x for x in r["reasons"]))

    def test_no_hits_leaves_an_empty_record(self):
        self.assertEqual(route(axes(), [], DEFAULTS)["floor"], {"hits": [], "raised_from": None})


class FloorFileTest(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.r.hr("init")
        self.ws = Workspace(self.r.root)

    def tearDown(self):
        self.r.cleanup()

    def test_missing_file_is_an_empty_floor(self):
        self.assertEqual(floor.load(self.ws), {})

    def test_quoted_globs_load_without_pyyaml(self):
        self.r.write(".human-rights/floor.yaml", RULES)
        with mock.patch.dict("sys.modules", {"yaml": None}):
            self.assertEqual(floor.load(self.ws), {"migrations/**": "L2", "src/auth/**": "L3", "**/secrets/*": "L3"})

    def test_a_bad_level_names_the_file_and_the_key(self):
        self.r.write(".human-rights/floor.yaml", '"src/auth/**": L9\n')
        with self.assertRaises(Exception) as cm:
            floor.load(self.ws)
        self.assertIn("floor.yaml", str(cm.exception))
        self.assertIn("src/auth/**", str(cm.exception))

    def test_hits_match_globs_and_declared_directories(self):
        rules = {"src/auth/**": "L3", "**/secrets/*": "L3"}
        got = floor.hits(rules, ["src/auth/login.py", "src/auth/", "src/auth", "cfg/secrets/key", "src/app.py"])
        self.assertEqual([(h["pattern"], h["paths"]) for h in got],
                         [("**/secrets/*", ["cfg/secrets/key"]),
                          ("src/auth/**", ["src/auth/login.py", "src/auth/", "src/auth"])])


class ClassifyFloorTest(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.r.hr("init")
        self.r.floor(RULES)
        self.r.hr("new", "Tidy the login card")

    def tearDown(self):
        self.r.cleanup()

    def test_declared_floored_path_raises_l0_to_l2_with_a_design_gate(self):
        code, out = self.r.hr("classify", "--axes", L0_AXES, "--paths", "migrations/0001.sql,src/app.py")
        self.assertEqual(code, 0, out)
        self.assertIn("mode: L2", out)
        self.assertIn("raised L0 -> L2", out)
        st = self.r.state()
        self.assertTrue(st["required_gates"]["design"])
        self.assertEqual(st["routing"]["floor"]["raised_from"], "L0")
        self.assertEqual(st["routing"]["declared_paths"], ["migrations/0001.sql", "src/app.py"])
        events = (self.r.feature_dir() / ".internal" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        classified = [json.loads(e) for e in events if json.loads(e)["event"] == "classified"][-1]
        self.assertEqual(classified["floor"]["hits"][0]["pattern"], "migrations/**")
        self.assertEqual(classified["floor"]["raised_from"], "L0")

    def test_unfloored_paths_stay_l0(self):
        code, out = self.r.hr("classify", "--axes", L0_AXES, "--paths", "src/app.py")
        self.assertIn("mode: L0", out)
        self.assertIsNone(self.r.state()["routing"]["floor"]["raised_from"])

    def test_classify_sees_a_floored_file_already_in_the_diff(self):
        self.r.write("src/auth/login.py", "x = 1\n")
        code, out = self.r.hr("classify", "--axes", L0_AXES)
        self.assertIn("mode: L3", out)

    def test_omitting_paths_keeps_the_declared_ones(self):
        self.r.hr("classify", "--axes", L0_AXES, "--paths", "src/auth/login.py")
        code, out = self.r.hr("classify", "--axes", L0_AXES)
        self.assertIn("mode: L3", out)
        code, out = self.r.hr("classify", "--axes", L0_AXES, "--paths", "src/app.py")
        self.assertIn("mode: L0", out)


class GuardTest(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.r.hr("init")
        self.r.floor(RULES)
        self.r.hr("new", "Tidy the login card")
        self.r.hr("classify", "--axes", L0_AXES)
        self.r.hr("transition", "executing")

    def tearDown(self):
        self.r.cleanup()

    def test_gate_that_became_required_after_execution_started_is_not_skipped(self):
        r = self.r
        r.write("src/app.py", "print('changed')\n")
        r.commit("work")
        l2 = json.loads(L0_AXES)
        l2["scope"]["score"] = 2
        code, out = r.hr("classify", "--axes", json.dumps(l2))
        self.assertIn("mode: L2", out)
        self.assertEqual(r.hr("verify", "--adhoc", 'python -c "pass"', "--title", "lint")[0], 0)
        code, out = r.hr("transition", "verifying_tasks")
        self.assertEqual(code, 3, out)
        self.assertIn("design", out)
        self.assertIn("approval", out)

    def test_floored_file_committed_after_verifying_is_refused_at_completed(self):
        r = self.r
        self.assertEqual(r.hr("verify", "--adhoc", 'python -c "pass"', "--title", "lint")[0], 0)
        self.assertEqual(r.hr("transition", "verifying_tasks")[0], 0)
        r.write("src/auth/login.py", "ok = True\n")
        r.commit("sneak")
        code, out = r.hr("transition", "completed")
        self.assertEqual(code, 3, out)
        self.assertIn("[floor]", out)
        self.assertIn("src/auth/login.py", out)
        self.assertIn("src/auth/**", out)
        self.assertIn("L3", out)
        self.assertIn("--paths", out)

    def test_floored_file_blocks_every_step_after_executing(self):
        r = self.r
        r.write("migrations/0001.sql", "select 1;\n")
        code, out = r.hr("transition", "verifying_tasks")
        self.assertEqual(code, 3, out)
        self.assertIn("[floor]", out)

    def test_reclassifying_clears_the_floor_but_then_the_design_gate_applies(self):
        r = self.r
        self.assertEqual(r.hr("verify", "--adhoc", 'python -c "pass"', "--title", "lint")[0], 0)
        self.assertEqual(r.hr("transition", "verifying_tasks")[0], 0)
        r.write("src/auth/login.py", "ok = True\n")
        r.commit("sneak")
        code, out = r.hr("classify", "--axes", L0_AXES, "--paths", "src/auth/login.py")
        self.assertIn("mode: L3", out)
        code, out = r.hr("transition", "completed")
        self.assertEqual(code, 3, out)
        self.assertNotIn("[floor]", out)
        self.assertIn("design", out)

    def test_a_rewritten_history_does_not_hide_the_diff(self):
        r = self.r
        r.write("src/other.py", "x = 1\n")
        r.commit("a commit the feature started from")
        r.hr("new", "Second change")
        helpers.git(r.root, "commit", "-q", "--amend", "-m", "rewritten")
        r.write("src/auth/login.py", "ok = True\n")
        r.commit("not a descendant of the start commit")
        code, out = r.hr("classify", "--axes", L0_AXES, "-f", "FEAT-002")
        self.assertIn("mode: L3", out)

    def test_floor_below_the_mode_is_not_a_problem(self):
        r = self.r
        r.hr("classify", "--axes", L3_AXES, *ONE, "--flags", "vehicle_command")
        r.write("migrations/0001.sql", "select 1;\n")
        code, out = r.hr("transition", "verifying_tasks")
        self.assertNotIn("[floor]", out)


class FloorCommandTest(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.r.hr("init")
        self.floor_file = self.r.root / ".human-rights" / "floor.yaml"

    def tearDown(self):
        self.r.cleanup()

    def test_changing_the_floor_needs_a_human(self):
        code, out = self.r.hr("floor", "add", "src/auth/**", "L3")
        self.assertEqual(code, 2, out)
        self.assertIn("--by", out)
        self.assertFalse(self.floor_file.exists())

    def test_a_quote_that_is_not_in_the_humans_message_is_refused(self):
        self.r.say("sounds fine")
        code, out = self.r.hr("floor", "add", "src/auth/**", "L3", "--quote", "gate the auth code")
        self.assertEqual(code, 3, out)
        self.assertFalse(self.floor_file.exists())

    def test_add_and_remove_with_a_quote(self):
        r = self.r
        r.say("Please always gate src/auth at L3")
        code, out = r.hr("floor", "add", "src/auth/**", "L3", "--quote", "always gate src/auth at L3")
        self.assertEqual(code, 0, out)
        self.assertIn("decided by test via chat", out)
        self.assertEqual(floor.load(Workspace(r.root)), {"src/auth/**": "L3"})
        self.assertIn('"src/auth/**": L3', self.floor_file.read_text(encoding="utf-8"))

        r.say("make migrations L2 too")
        self.assertEqual(r.hr("floor", "add", "migrations/**", "L2", "--quote", "migrations L2")[0], 0)
        r.say("lower auth to L2")
        code, out = r.hr("floor", "add", "src/auth/**", "L2", "--quote", "lower auth to L2")
        self.assertIn("(was L3)", out)

        r.say("drop the migrations rule")
        code, out = r.hr("floor", "remove", "migrations/**", "--quote", "drop the migrations rule")
        self.assertEqual(code, 0, out)
        self.assertEqual(floor.load(Workspace(r.root)), {"src/auth/**": "L2"})

    def test_the_human_can_run_it_directly_with_by(self):
        code, out = self.r.hr("floor", "add", "src/auth/**", "L3", "--by", "alice")
        self.assertEqual(code, 0, out)
        self.assertIn("decided by alice via cli", out)

    def test_bad_input_is_refused_before_anything_is_written(self):
        self.assertEqual(self.r.hr("floor", "add", "src/auth/**", "L7", "--by", "alice")[0], 2)
        self.assertEqual(self.r.hr("floor", "add", "src/auth/**", "--by", "alice")[0], 2)
        self.assertEqual(self.r.hr("floor", "remove", "nope/**", "--by", "alice")[0], 2)
        self.assertFalse(self.floor_file.exists())

    def test_list_shows_the_rules_and_what_the_active_feature_touches(self):
        r = self.r
        self.assertIn("no floor", r.hr("floor")[1])
        r.floor(RULES)
        r.hr("new", "Tidy")
        r.write("migrations/0001.sql", "select 1;\n")
        code, out = r.hr("floor")
        self.assertEqual(code, 0, out)
        self.assertIn("L3  src/auth/**", out)
        self.assertIn("touched by FEAT-001-tidy: migrations/0001.sql", out)


def hook(tool, **inp):
    proc = subprocess.run([sys.executable, str(helpers.PLUGIN / "hooks" / "approval_guard.py")],
                          input=json.dumps({"tool_name": tool, "tool_input": inp}).encode(), stdout=subprocess.PIPE)
    out = proc.stdout.decode().strip()
    if not out:
        return "allow", ""
    decision = json.loads(out)["hookSpecificOutput"]
    return decision["permissionDecision"], decision["permissionDecisionReason"]


class FloorHookTest(unittest.TestCase):
    def test_agent_cannot_edit_the_floor_file(self):
        for tool, key in (("Write", "file_path"), ("Edit", "file_path"), ("MultiEdit", "file_path"),
                          ("NotebookEdit", "notebook_path")):
            for p in ("C:/repo/.human-rights/floor.yaml", "C:\\repo\\.human-rights\\floor.yaml",
                      "C:/repo/.workflow/floor.yaml"):
                decision, reason = hook(tool, **{key: p})
                self.assertEqual(decision, "deny", (tool, p))
                self.assertIn("hr floor", reason)

    def test_agent_cannot_write_it_from_a_shell(self):
        for tool in ("Bash", "PowerShell"):
            for cmd in ("echo '\"src/**\": L0' > .human-rights/floor.yaml",
                        "sed -i 's/L3/L0/' .human-rights/floor.yaml",
                        "Set-Content .human-rights\\floor.yaml ''",
                        "rm .workflow/floor.yaml"):
                self.assertEqual(hook(tool, command=cmd)[0], "deny", cmd)

    def test_reading_the_floor_is_fine(self):
        self.assertEqual(hook("Read", file_path="C:/repo/.human-rights/floor.yaml")[0], "allow")
        self.assertEqual(hook("Bash", command="cat .human-rights/floor.yaml")[0], "allow")
        self.assertEqual(hook("Bash", command=".human-rights/hr floor")[0], "allow")
        self.assertEqual(hook("Bash", command=".human-rights/hr classify --axes @a.json --paths src/auth/x.py")[0], "allow")

    def test_floor_changes_are_human_decisions(self):
        for cmd in (".human-rights/hr floor add src/auth/** L3", ".human-rights/hr floor remove src/auth/**",
                    'python3 "/x/runtime/hr.py" floor add "src/**" L2 --by me'):
            decision, reason = hook("Bash", command=cmd)
            self.assertEqual(decision, "deny", cmd)
            self.assertIn("`floor add`" if "add" in cmd else "`floor remove`", reason)
        self.assertEqual(hook("Bash", command='.human-rights/hr floor add "src/**" L2 --quote "gate src"')[0], "allow")
        self.assertEqual(hook("PowerShell", command='.human-rights\\hr.cmd floor remove "src/**" --quote "drop it"')[0], "allow")


if __name__ == "__main__":
    unittest.main()
