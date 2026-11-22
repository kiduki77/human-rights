import json
import unittest
from unittest import mock

from helpers import L0_AXES, Repo
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
        self.r.write(".human-rights/floor.yaml", RULES)
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


if __name__ == "__main__":
    unittest.main()
