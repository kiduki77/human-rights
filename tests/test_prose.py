import json
import unittest

from helpers import L3_AXES, Repo, install_example_plan
from runtime import prose

CONF = {"mode": "error", "banned": [], "allowed": []}


def words(text):
    return [w for _, w in prose.find(prose.strip_markdown(text), CONF)]


class FindTest(unittest.TestCase):
    def test_english_filler(self):
        self.assertEqual(words("This delivers a seamless, comprehensive experience."), ["seamless", "comprehensive"])
        self.assertEqual(words("Retries stop after 3 failures and the job is marked failed."), [])

    def test_korean_filler(self):
        self.assertEqual(words("이를 통해 원활한 운영이 가능합니다."), ["원활", "이를 통해"])
        self.assertEqual(words("전송 주기를 0.5초에서 10초 사이로 바꿀 수 있다."), [])

    def test_code_generated_blocks_and_placeholders_are_skipped(self):
        text = ("`seamless_mode` is the flag name.\n```\nleverage = 3\n```\n"
                "<!-- hr:status:start -->\n| comprehensive |\n<!-- hr:status:end -->\n[FILL: a seamless thing]\n")
        self.assertEqual(words(text), [])

    def test_em_dash_runs(self):
        self.assertEqual(words("# Title — state\nOne — two.\nThree — four.\n"), [])
        self.assertIn("3 em dashes", words("One — two.\nThree — four.\nFive — six.\n")[0])


class GateTest(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        r = self.r
        r.hr("init")
        r.hr("new", "Multi-vehicle control", "--slug", "multi-drone")
        r.hr("classify", "--axes", L3_AXES, "--flags", "vehicle_command", "--size", "single",
             "--size-reason", "one session model")
        self.fdir = install_example_plan(r)
        r.hr("transition", "planning")

    def tearDown(self):
        self.r.cleanup()

    def add(self, text):
        path = self.fdir / "overview.md"
        path.write_text(path.read_text(encoding="utf-8") + "\n" + text + "\n", encoding="utf-8")

    def test_filler_blocks_the_approval_request(self):
        r = self.r
        self.add("이 변경은 혁신적인 다중 기체 제어를 제공합니다.")
        code, out = r.hr("doc-check")
        self.assertEqual(code, 3, out)
        self.assertIn("overview.md", out)
        self.assertIn("'혁신적'", out)
        code, out = r.hr("transition", "awaiting_design_approval")
        self.assertEqual(code, 3, out)
        self.assertIn("[wording] 1 filler phrase(s)", out)

    def test_plan_text_is_checked_too(self):
        r = self.r
        path = self.fdir / ".internal" / "task-graph.json"
        graph = json.loads(path.read_text(encoding="utf-8"))
        graph["tasks"][0]["purpose"] = "Leverage a robust registry"
        path.write_text(json.dumps(graph), encoding="utf-8")
        code, out = r.hr("doc-check")
        self.assertEqual(code, 3, out)
        self.assertIn("task-graph.json tasks[TASK-001].purpose: 'Leverage'", out)

    def test_config_can_relax_or_extend(self):
        r = self.r
        cfg = r.root / ".human-rights" / "config.yaml"
        self.add("The seamless handover is the product name.")
        text = cfg.read_text(encoding="utf-8")
        cfg.write_text(text.replace("allowed_phrases: []", "allowed_phrases: [seamless]")
                       .replace("banned_phrases: []", "banned_phrases: [handover]"), encoding="utf-8")
        code, out = r.hr("doc-check")
        self.assertIn("'handover'", out)
        self.assertNotIn("'seamless'", out)
        cfg.write_text(text.replace("prose_check: error", "prose_check: warn"), encoding="utf-8")
        self.assertEqual(r.hr("doc-check")[0], 0)
        self.assertEqual(r.hr("transition", "awaiting_design_approval")[0], 0)


if __name__ == "__main__":
    unittest.main()
