import json
import unittest

from helpers import L3_AXES, PLUGIN, Repo, git, install_example_plan
from runtime import human, redpill
from runtime.state.store import Workspace
from test_redpill import guard


class ChatBase(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        r = self.r
        r.hr("init")
        r.hr("new", "Multi-vehicle control", "--slug", "multi-drone")
        r.hr("classify", "--axes", L3_AXES, "--flags", "vehicle_command")
        install_example_plan(r)
        r.hr("transition", "planning")

    def tearDown(self):
        self.r.cleanup()

    def ws(self):
        return Workspace(self.r.root)

    def drill(self):
        return redpill.load(self.ws().resolve(None))

    def last_event(self, name):
        return [e for e in self.ws().resolve(None).events() if e["event"] == name][-1]


class QuoteProofTest(ChatBase):
    def test_chat_approval_needs_a_real_fresh_message(self):
        r = self.r
        r.hr("transition", "awaiting_design_approval")
        code, out = r.hr("approve", "design", "--quote", "looks good")
        self.assertEqual(code, 3, out)
        self.assertIn("no human message has been captured", out)

        r.say("hmm, let me think about TASK-002 first")
        code, out = r.hr("approve", "design", "--quote", "looks good")
        self.assertEqual(code, 3, out)
        self.assertIn("does not match", out)

        r.say("Looks   good, go ahead")
        code, out = r.hr("approve", "design", "--quote", "looks good, go ahead")
        self.assertEqual(code, 0, out)
        self.assertIn("via chat", out)
        ap = r.state()["approvals"]["design"]
        self.assertEqual((ap["via"], ap["quote"], ap["approver"]), ("chat", "looks good, go ahead", "test"))
        self.assertEqual(self.last_event("approval_granted")["via"], "chat")

    def test_message_from_before_the_gate_does_not_count(self):
        r = self.r
        r.say("approved")
        path = human.prompts_path(self.ws())
        entry = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
        entry["at"] = "2000-01-01T00:00:00.000000Z"
        path.write_text(json.dumps(entry) + "\n", encoding="utf-8")
        r.hr("transition", "awaiting_design_approval")
        code, out = r.hr("approve", "design", "--quote", "approved")
        self.assertEqual(code, 3, out)
        self.assertIn("predates", out)

    def test_pointing_at_a_real_item_is_review_not_approval(self):
        r = self.r
        r.hr("transition", "awaiting_design_approval")
        r.say("TEST-001 이 검증 방법 좀 이상하지 않아?")
        code, out = r.hr("approve", "design", "--quote", "TEST-001 이 검증 방법 좀 이상하지 않아?", "--flag", "TEST-001")
        self.assertEqual(code, 3, out)
        self.assertIn("not approved: the human pointed out TEST-001", out)
        self.assertEqual(r.state()["state"], "awaiting_design_approval")
        self.assertIn("human review flags: TEST-001", r.hr("status")[1])

        r.say("설명 들어보니 괜찮네, 승인")
        code, out = r.hr("approve", "design", "--quote", "괜찮네, 승인")
        self.assertEqual(code, 0, out)

    def test_prompt_log_is_bounded_and_ignored_by_git(self):
        r = self.r
        for i in range(25):
            r.say(f"message {i}")
        lines = human.prompts_path(self.ws()).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), human.KEEP)
        self.assertEqual(json.loads(lines[-1])["text"], "message 24")
        self.assertNotIn(".local", git(r.root, "status", "--porcelain", "--untracked-files=all"))

    def test_hook_reminds_the_agent_only_at_a_decision_point(self):
        r = self.r
        self.assertEqual(r.say("keep going").strip(), "")
        r.hr("transition", "awaiting_design_approval")
        self.assertIn("waiting for design approval", r.say("let me look"))


class ChatDrillTest(ChatBase):
    def test_pointing_at_the_plant_in_chat_catches_it_and_approves(self):
        r = self.r
        r.say("/hrs:redpill on 1")
        self.assertEqual(r.hr("redpill", "on", "--one-in", "1", "--quote", "/hrs:redpill on 1")[0], 0)
        r.hr("transition", "awaiting_design_approval")
        plant = self.drill()["active"]["id"]

        r.say("좋아 승인")
        code, out = r.hr("approve", "design", "--quote", "좋아 승인")
        self.assertEqual(code, 3, out)
        self.assertIn("tell the agent in chat", out)

        msg = f"{plant} 이거 검증이 이상한데"
        r.say(msg)
        code, out = r.hr("approve", "design", "--quote", msg, "--flag", plant.lower())
        self.assertEqual(code, 0, out)
        self.assertIn("Good catch", out)
        self.assertEqual(r.state()["state"], "executing")
        st = redpill.stats(self.ws().resolve(None))
        self.assertEqual((st["caught"], st["rubber_stamps"]), (1, 1))
        self.assertEqual(self.last_event("redpill_caught")["quote"], msg)

    def test_plant_and_real_concern_together_catch_but_do_not_approve(self):
        r = self.r
        r.hr("redpill", "on", "--one-in", "1")
        r.hr("transition", "awaiting_design_approval")
        plant = self.drill()["active"]["id"]
        msg = f"{plant} 말이 안 되고 TASK-002 범위도 줄여야 할 듯"
        r.say(msg)
        code, out = r.hr("approve", "design", "--quote", msg, "--flag", plant, "TASK-002")
        self.assertEqual(code, 3, out)
        self.assertIn("Good catch", out)
        self.assertIn("pointed out TASK-002", out)
        self.assertIsNone(self.drill()["active"])

    def test_reveal_and_toggle_from_chat(self):
        r = self.r
        r.hr("redpill", "on", "--one-in", "1")
        r.hr("transition", "awaiting_design_approval")
        plant = self.drill()["active"]["id"]
        r.say("모르겠다 정답 보여줘")
        code, out = r.hr("redpill", "reveal", "--quote", "정답 보여줘")
        self.assertIn(plant, out)
        r.say("레드필 꺼줘")
        self.assertEqual(r.hr("redpill", "off", "--quote", "레드필 켜줘")[0], 3)
        self.assertEqual(r.hr("redpill", "off", "--quote", "레드필 꺼줘")[0], 0)
        self.assertFalse(redpill.settings(self.ws())["enabled"])


class ChatOtherDecisionsTest(ChatBase):
    def test_unblock_from_chat(self):
        r = self.r
        r.hr("transition", "blocked", "--reason", "SITL image broken")
        r.say("이미지 고쳤어, 다시 진행해")
        code, out = r.hr("unblock", "--quote", "다시 진행해", "--note", "SITL image fixed")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.last_event("unblocked")["quote"], "다시 진행해")


class InitTest(unittest.TestCase):
    def test_init_sets_language_and_is_idempotent(self):
        r = Repo(use_git=False)
        try:
            code, out = r.hr("init", "--language", "ko")
            self.assertEqual(code, 0, out)
            self.assertIn("report language: ko", out)
            ws = Workspace(r.root)
            self.assertEqual(ws.config()["docs"]["language"], "ko")
            self.assertEqual(ws.config()["docs"]["overview_max_lines"], 120)
            self.assertEqual(r.hr("init")[0], 0)
            self.assertEqual(ws.config()["docs"]["language"], "ko")
            self.assertEqual(r.hr("init", "--language", "fr")[0], 2)
        finally:
            r.cleanup()


class ReclassifyAfterClarifyingTest(unittest.TestCase):
    def test_answers_must_be_scored_before_leaving_clarifying(self):
        r = Repo()
        try:
            axes = json.loads(L3_AXES)
            axes["risk"]["score"] = 1
            axes["architecture"]["score"] = 1
            r.hr("init")
            r.hr("new", "Live map interval", "--slug", "interval")
            r.hr("classify", "--axes", json.dumps(axes))
            self.assertEqual(r.state()["mode"], "L3")
            r.hr("transition", "clarifying")
            code, out = r.hr("transition", "investigating")
            self.assertEqual(code, 3, out)
            self.assertIn("reclassify after clarifying", out)
            axes["ambiguity"] = {"score": 0, "basis": "user answered all four policies", "confirmed": True,
                                 "confidence": "high"}
            code, out = r.hr("classify", "--axes", json.dumps(axes))
            self.assertIn("L3 -> L2", out)
            self.assertEqual(r.hr("transition", "investigating")[0], 0)
        finally:
            r.cleanup()


class LegacyWorkspaceTest(unittest.TestCase):
    def test_old_workflow_dir_is_moved_by_init(self):
        r = Repo()
        try:
            r.hr("init")
            r.hr("new", "Login card", "--slug", "login")
            (r.root / ".human-rights").rename(r.root / ".workflow")
            code, out = r.hr("status")
            self.assertEqual(code, 2)
            self.assertIn("/hrs:init", out)
            code, out = r.hr("init")
            self.assertEqual(code, 0, out)
            self.assertIn("moved from .workflow/", out)
            self.assertFalse((r.root / ".workflow").exists())
            self.assertIn("FEAT-001", r.hr("status")[1])
        finally:
            r.cleanup()

    def test_unrelated_workflow_dir_is_left_alone(self):
        r = Repo(use_git=False)
        try:
            r.write(".workflow/config.yaml", "pipeline: build\n")
            self.assertEqual(r.hr("init")[0], 0)
            self.assertTrue((r.root / ".workflow" / "config.yaml").exists())
            self.assertTrue((r.root / ".human-rights" / "config.yaml").exists())
        finally:
            r.cleanup()


class GuardChatTest(unittest.TestCase):
    def test_quoted_human_decisions_pass_the_guard(self):
        self.assertEqual(guard("Bash", command='.human-rights/hr approve design --quote "looks good"'), "allow")
        self.assertEqual(guard("Bash", command='.human-rights/hr approve design --quote "x" --flag TEST-014'), "allow")
        self.assertEqual(guard("Bash", command='.human-rights/hr redpill on --one-in 5 --quote "turn it on"'), "allow")
        self.assertEqual(guard("Bash", command=".human-rights/hr approve design --by me"), "deny")
        self.assertEqual(guard("Bash", command=".human-rights/hr approve design --by me --quoted"), "deny")

    def test_agent_cannot_forge_the_prompt_log(self):
        self.assertEqual(guard("Write", file_path="C:/r/.human-rights/.local/prompts.jsonl"), "deny")
        self.assertEqual(guard("Bash", command="echo '{}' >> .human-rights/.local/prompts.jsonl"), "deny")


if __name__ == "__main__":
    unittest.main()
