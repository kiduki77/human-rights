import json
import unittest

from helpers import ONE
from helpers import L3_AXES, Repo, install_example_plan
from runtime import docs, redpill
from runtime.state.store import Workspace
from test_redpill import StubRng


class KoreanDocsTest(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.r.hr("init", "--language", "ko")
        self.r.hr("new", "다중 기체 제어", "--slug", "multi-drone")
        self.r.hr("classify", "--axes", L3_AXES, *ONE, "--flags", "vehicle_command")

    def tearDown(self):
        self.r.cleanup()

    def test_scaffold_uses_korean_templates_with_title(self):
        code, out = self.r.hr("scaffold", "codebase", "overview")
        self.assertEqual(code, 0, out)
        text = (self.r.feature_dir() / "details" / "codebase.md").read_text(encoding="utf-8")
        self.assertIn("| # | 발견 | 근거 (경로:줄 / 심볼 / 실행 결과) | 상태 |", text)
        self.assertIn("# 코드 조사 — 다중 기체 제어", text)
        self.assertNotIn("Finding", text)

    def test_task_docs_are_prefilled_in_korean(self):
        install_example_plan(self.r)
        code, out = self.r.hr("scaffold", "tasks", "--overwrite")
        self.assertEqual(code, 0, out)
        text = (self.r.feature_dir() / "tasks" / "TASK-001.md").read_text(encoding="utf-8")
        self.assertIn("아직 구현하지 않음.", text)
        self.assertIn("| 미실행 |", text)
        self.assertNotIn("[FILL: 작업 제목]", text)

    def test_rendered_tables_and_plants_are_korean(self):
        r = self.r
        install_example_plan(r)
        r.hr("redpill", "on", "--one-in", "1", "--author", "builtin")
        r.hr("transition", "planning")
        r.hr("transition", "awaiting_design_approval")
        f = Workspace(r.root).resolve(None)
        overview = (r.feature_dir() / "overview.md").read_text(encoding="utf-8")
        self.assertIn("| 항목 | 값 |", overview)
        self.assertIn("**설계 승인 대기**", overview)
        self.assertIn("| 요구사항 | 테스트 | 실행 주체 | 통과 기준 | 결과 | 근거 |", overview)
        self.assertIn("⏳ 미실행", overview)
        self.assertNotIn("not run", overview)
        redpill.on_enter_state(f, "awaiting_design_approval", rng=StubRng(0.1))
        docs.render(f)
        act = redpill.load(f)["active"]
        self.assertIn("입력 검증을 잠시 끄고", act["row"])
        self.assertIn("| 낮음 | 계획됨 |", act["row"])
        self.assertIn(act["row"], (r.feature_dir() / "overview.md").read_text(encoding="utf-8"))
        self.assertEqual(r.hr("doc-check")[0], 0)


class AgentSettingsTest(unittest.TestCase):
    def test_presets_and_agent_call_params(self):
        r = Repo(use_git=False)
        try:
            code, out = r.hr("init")
            self.assertIn("hr-plan-reviewer  model opus", out)
            s = json.loads(r.hr("agents", "--json")[1])
            self.assertEqual(s["plan_reviewer"]["agent_call"], {"model": "opus", "effort": "high"})
            r.hr("init", "--agents", "inherit")
            s = json.loads(r.hr("agents", "--json")[1])
            self.assertEqual({k: v["agent_call"] for k, v in s.items()},
                             {"investigator": {}, "plan_reviewer": {}, "code_reviewer": {}, "task_worker": {},
                              "tester": {}, "redpill_author": {}})
            r.hr("init", "--agents", "economy")
            s = json.loads(r.hr("agents", "--json")[1])
            self.assertEqual(s["investigator"]["agent_call"], {"model": "haiku"})
            self.assertEqual(Workspace(r.root).config()["agents"]["preset"], "economy")
            self.assertEqual(r.hr("init", "--agents", "turbo")[0], 2)
        finally:
            r.cleanup()

    def test_hand_edited_typo_is_reported(self):
        r = Repo(use_git=False)
        try:
            r.hr("init")
            cfg = r.root / ".human-rights" / "config.yaml"
            cfg.write_text(cfg.read_text(encoding="utf-8").replace("task_worker_model: sonnet", "task_worker_model: sonet"),
                           encoding="utf-8")
            code, out = r.hr("agents")
            self.assertIn("[!] unknown model 'sonet'", out)
        finally:
            r.cleanup()


if __name__ == "__main__":
    unittest.main()
