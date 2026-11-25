import unittest

from helpers import L3_AXES, ONE, PLUGIN, Repo, install_example_plan

MARK = "<!-- hr:introduces -->"


class IntroducesSectionTest(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.r.hr("init")
        self.r.hr("new", "Multi-vehicle control", "--slug", "multi-drone")
        self.r.hr("classify", "--axes", L3_AXES, *ONE, "--flags", "vehicle_command")
        install_example_plan(self.r)
        self.r.hr("render")
        self.design = self.r.feature_dir() / "design.md"

    def tearDown(self):
        self.r.cleanup()

    def rewrite(self, body):
        text = self.design.read_text(encoding="utf-8")
        start = text.index(MARK)
        end = text.index("\n## ", start)
        self.design.write_text(text[:start] + body + text[end:], encoding="utf-8")

    def test_the_example_passes(self):
        code, out = self.r.hr("doc-check")
        self.assertEqual(code, 0, out)

    def test_a_design_without_the_section_fails_with_a_fix_hint(self):
        text = self.design.read_text(encoding="utf-8")
        start = text.index("## What this design introduces")
        end = text.index("## Other places that use it")
        self.design.write_text(text[:start] + text[end:], encoding="utf-8")
        code, out = self.r.hr("doc-check")
        self.assertEqual(code, 3, out)
        self.assertIn("does not list what the design introduces", out)
        self.assertIn(MARK, out)
        self.assertIn("templates/design.md", out)

    def test_an_empty_section_fails(self):
        self.rewrite(MARK + "\n")
        code, out = self.r.hr("doc-check")
        self.assertEqual(code, 3, out)
        self.assertIn("is empty", out)

    def test_nothing_new_is_a_valid_answer(self):
        self.rewrite(MARK + "\nNothing new: the registry in `src/link/conn.py` already holds one session per vehicle.\n")
        code, out = self.r.hr("doc-check")
        self.assertEqual(code, 0, out)

    def test_the_heading_can_be_in_any_language(self):
        text = self.design.read_text(encoding="utf-8")
        self.design.write_text(text.replace("## What this design introduces", "## 이 설계가 새로 들여오는 것"),
                               encoding="utf-8")
        code, out = self.r.hr("doc-check")
        self.assertEqual(code, 0, out)

    def test_the_section_is_part_of_the_approved_design(self):
        from runtime.approvals.gates import design_artifacts
        from runtime.state.store import Workspace

        feature = Workspace(self.r.root).resolve(None)
        before = design_artifacts(feature)["design.md"]
        self.rewrite(MARK + "\nNothing new: nothing.\n")
        self.assertNotEqual(design_artifacts(feature)["design.md"], before)

    def test_both_templates_carry_the_marker_before_the_impact_section(self):
        for path in ("templates/design.md", "templates/ko/design.md"):
            text = (PLUGIN / path).read_text(encoding="utf-8")
            self.assertIn(MARK, text, path)
            self.assertLess(text.index(MARK), text.index("<!-- hr:impact:start -->"), path)


class PlanReviewerAxisTest(unittest.TestCase):
    def test_the_reviewer_asks_whether_each_new_part_is_needed(self):
        text = (PLUGIN / "agents" / "hr-plan-reviewer.md").read_text(encoding="utf-8")
        row = next(l for l in text.splitlines() if l.startswith("| Need |"))
        self.assertIn("is there a requirement behind it", row)
        self.assertIn("What this design introduces", row)
        self.assertIn("no requirement asks for", text)


if __name__ == "__main__":
    unittest.main()
