import contextlib
import io
import json
import unittest

from helpers import Repo
from runtime.state.store import Workspace


class VisibilityTest(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.r.hr("init")
        self.r.hr("new", "Visibility", "--slug", "vis")

    def tearDown(self):
        self.r.cleanup()

    def rec(self, kind, *extra):
        return self.r.hr("metrics", "record", "--kind", kind, *extra)

    def metrics(self):
        return json.loads(self.r.hr("metrics", "--json")[1])

    def test_required_for_the_two_kinds(self):
        for kind in ("escaped_defect", "intent_mismatch"):
            code, out = self.rec(kind)
            self.assertEqual(code, 2, out)
            self.assertIn("--visible-at-approval", out)
            self.assertIn("ask the human", out)
        self.assertEqual(self.metrics()["escaped_defects"], 0)

    def test_value_must_be_yes_or_no(self):
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
            self.rec("escaped_defect", "--visible-at-approval", "maybe")
        self.assertEqual(cm.exception.code, 2)
        self.assertEqual(self.metrics()["escaped_defects"], 0)

    def test_refused_for_other_kinds(self):
        code, out = self.rec("tokens", "--value", "5", "--visible-at-approval", "yes")
        self.assertEqual(code, 2, out)
        self.assertEqual(self.metrics()["tokens"], 0)

    def test_groups_are_reported_separately(self):
        self.assertEqual(self.rec("escaped_defect", "--visible-at-approval", "yes")[0], 0)
        self.assertEqual(self.rec("escaped_defect", "--visible-at-approval", "no", "--value", "2")[0], 0)
        self.assertEqual(self.rec("intent_mismatch", "--visible-at-approval", "yes")[0], 0)
        self.assertEqual(self.rec("intent_mismatch", "--visible-at-approval", "no")[0], 0)
        m = self.metrics()
        self.assertEqual((m["escaped_defects"], m["intent_mismatch"]), (3, 2))
        self.assertEqual(m["escaped_defects_by_visibility"], {"yes": 1, "no": 2, "unknown": 0})
        self.assertEqual(m["intent_mismatch_by_visibility"], {"yes": 1, "no": 1, "unknown": 0})
        self.assertEqual(m["review_misses"], 2)

    def test_records_without_an_answer_are_unknown_and_not_misses(self):
        feature = Workspace(self.r.root).resolve(None)
        feature.emit("metric_recorded", kind="escaped_defect", value=1, note="", actor="agent")
        feature.emit("metric_recorded", kind="intent_mismatch", value=2, note="", actor="agent")
        self.assertEqual(self.rec("escaped_defect", "--visible-at-approval", "yes")[0], 0)
        m = self.metrics()
        self.assertEqual(m["escaped_defects"], 2)
        self.assertEqual(m["escaped_defects_by_visibility"], {"yes": 1, "no": 0, "unknown": 1})
        self.assertEqual(m["intent_mismatch_by_visibility"], {"yes": 0, "no": 0, "unknown": 2})
        self.assertEqual(m["review_misses"], 1)

    def test_text_and_aggregate_output(self):
        self.rec("escaped_defect", "--visible-at-approval", "yes")
        self.rec("intent_mismatch", "--visible-at-approval", "no")
        code, out = self.r.hr("metrics")
        self.assertEqual(code, 0, out)
        self.assertIn("1 visible at approval, 0 not visible, 0 unknown", out)
        self.assertIn("0 visible at approval, 1 not visible, 0 unknown", out)
        self.assertIn("review misses 1", out)
        agg = json.loads(self.r.hr("metrics", "--all", "--json")[1])
        self.assertEqual(agg["review_misses"], 1)
        self.assertEqual(agg["escaped_defects_by_visibility"]["yes"], 1)
        self.assertEqual(agg["intent_mismatch_by_visibility"]["no"], 1)
        code, out = self.r.hr("metrics", "--all")
        self.assertIn("review misses (visible at approval only): 1", out)
        self.assertIn("escaped defects: 1 visible at approval", out)
