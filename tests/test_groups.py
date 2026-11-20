import json
import unittest

from helpers import L0_AXES, L3_AXES, PASS_CMD, Repo, install_example_plan

SPLIT = {
    "summary": "Account access",
    "source": {"kind": "request"},
    "children": [
        {"key": "signup", "title": "Sign up", "outcome": "A visitor can create an account with email and password",
         "verify_alone": "API test: POST /signup creates a user and rejects a duplicate email", "expected_mode": "L2"},
        {"key": "login", "title": "Log in", "outcome": "A registered user can log in and stay logged in",
         "verify_alone": "API test: POST /login returns a session, and a wrong password is rejected",
         "depends_on": ["signup"], "expected_mode": "L2"},
        {"key": "reset", "title": "Password reset", "outcome": "A user who forgot the password can set a new one",
         "verify_alone": "API test: a reset token changes the password once", "depends_on": ["signup"],
         "expected_mode": "L2"},
    ],
    "shared_decisions": [
        {"id": "GDEC-001", "question": "How is a session kept?", "answer": "Server-side session cookie",
         "decided_by": "user"},
    ],
    "excluded": [{"item": "Social login", "reason": "Not requested for this release"}],
}
GROUP_PLAN = {
    "tests": [
        {"id": "GTEST-001", "title": "Sign up, log in, reset, log in again", "type": "e2e", "level": "integration",
         "runner": "command", "command": PASS_CMD, "pass_criteria": "exit 0", "children": ["signup", "login", "reset"],
         "required": True},
    ],
}
L2_AXES = json.loads(L3_AXES)
for _k in ("risk", "architecture", "ambiguity", "verification"):
    L2_AXES[_k]["score"] = 1
L2_AXES = json.dumps(L2_AXES)


class GroupBase(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.r.hr("init")
        self.r.hr("new", "Add login", "--slug", "login")

    @property
    def gdir(self):
        return self.r.feature_dir("FEAT-001")

    def tearDown(self):
        self.r.cleanup()

    def write(self, name, data):
        (self.gdir / ".internal" / name).write_text(json.dumps(data, indent=2), encoding="utf-8")

    def to_splitting(self):
        r = self.r
        self.assertEqual(r.hr("size", "compound", "--reason", "sign up, log in and reset ship separately")[0], 0)
        code, out = r.hr("transition", "splitting")
        self.assertEqual(code, 0, out)
        self.write("split.json", SPLIT)
        self.write("test-plan.json", GROUP_PLAN)
        r.hr("scaffold")

    def approve(self):
        r = self.r
        self.to_splitting()
        code, out = r.hr("transition", "awaiting_split_approval")
        self.assertEqual(code, 0, out)
        code, out = r.hr("approve", "split", "--by", "alice")
        self.assertEqual(code, 0, out)
        return out

    def finish(self, fid):
        r = self.r
        r.hr("classify", "-f", fid, "--axes", L0_AXES)
        self.assertEqual(r.hr("transition", "-f", fid, "executing")[0], 0)
        r.hr("verify", "-f", fid, "--adhoc", PASS_CMD)
        self.assertEqual(r.hr("transition", "-f", fid, "verifying_tasks")[0], 0)
        code, out = r.hr("transition", "-f", fid, "completed")
        self.assertEqual(code, 0, out)
        return out


class SizeDecisionTest(GroupBase):
    def test_l2_and_above_need_a_size_decision(self):
        r = self.r
        r.hr("classify", "--axes", L2_AXES)
        code, out = r.hr("transition", "planning")
        self.assertEqual(code, 3, out)
        self.assertIn("decide the size", out)
        code, out = r.hr("classify", "--axes", L2_AXES, "--size", "single")
        self.assertEqual(code, 2, out)
        self.assertIn("--size-reason", out)
        r.hr("classify", "--axes", L2_AXES, "--size", "single", "--size-reason", "one endpoint, one screen")
        self.assertEqual(r.hr("transition", "planning")[0], 0)

    def test_small_requests_skip_the_size_decision(self):
        r = self.r
        r.hr("classify", "--axes", L0_AXES)
        code, out = r.hr("transition", "executing")
        self.assertEqual(code, 0, out)

    def test_compound_cannot_be_planned_as_one_feature(self):
        r = self.r
        r.hr("classify", "--axes", L2_AXES, "--size", "compound", "--size-reason", "three separate results")
        code, out = r.hr("transition", "planning")
        self.assertEqual(code, 3)
        self.assertIn("judged compound", out)
        code, out = r.hr("transition", "splitting")
        self.assertEqual(code, 0, out)
        self.assertIn("FEAT-001-login is now GRP-001-login", out)
        st = r.state()
        self.assertEqual((st["kind"], st["feature_id"]), ("group", "GRP-001-login"))
        wf = r.root / ".human-rights"
        self.assertTrue((wf / "groups" / "GRP-001-login" / ".internal" / "state.json").is_file())
        self.assertFalse((wf / "features" / "FEAT-001-login").exists())
        self.assertEqual(json.loads((wf / "active.json").read_text(encoding="utf-8"))["feature_id"], "GRP-001-login")
        problems = [line for line in r.hr("check")[1].splitlines() if line.startswith("  - ")]
        self.assertEqual(problems, ["  - [docs] overview.md is missing"])

    def test_a_group_with_no_features_can_become_one_feature_again(self):
        r = self.r
        r.hr("size", "compound", "--reason", "looked like three results")
        r.hr("transition", "splitting")
        code, out = r.hr("transition", "clarifying")
        self.assertEqual(code, 0, out)
        self.assertIn("GRP-001-login is now FEAT-001-login", out)
        wf = r.root / ".human-rights"
        self.assertTrue((wf / "features" / "FEAT-001-login" / ".internal" / "state.json").is_file())
        self.assertFalse((wf / "groups" / "GRP-001-login").exists())
        self.assertEqual(r.state()["kind"], "feature")

    def test_reclassify_after_clarifying_asks_for_the_size_again(self):
        r = self.r
        r.hr("classify", "--axes", L2_AXES, "--size", "single", "--size-reason", "looks like one screen")
        r.hr("transition", "clarifying")
        r.hr("classify", "--axes", L2_AXES)
        code, out = r.hr("transition", "planning")
        self.assertEqual(code, 3, out)
        self.assertIn("decide the size", out)
        r.hr("classify", "--axes", L2_AXES, "--size", "compound", "--size-reason", "the answers added reset and SSO")
        self.assertEqual(r.hr("transition", "splitting")[0], 0)

    def test_splitting_needs_the_compound_decision(self):
        code, out = self.r.hr("transition", "splitting")
        self.assertEqual(code, 3)
        self.assertIn("--size compound", out)


class SplitRulesTest(GroupBase):
    def check(self):
        return self.r.hr("split-check")

    def test_valid_split_passes(self):
        self.to_splitting()
        code, out = self.check()
        self.assertEqual(code, 0, out)

    def test_each_feature_must_be_verifiable_on_its_own(self):
        self.to_splitting()
        bad = json.loads(json.dumps(SPLIT))
        bad["children"][1].pop("verify_alone")
        bad["children"][2]["depends_on"] = ["nope"]
        bad.pop("excluded")
        self.write("split.json", bad)
        code, out = self.check()
        self.assertEqual(code, 3, out)
        self.assertIn("login: missing `verify_alone`", out)
        self.assertIn("reset: unknown dependency 'nope'", out)
        self.assertIn("needs `excluded`", out)

    def test_group_needs_a_check_that_crosses_features(self):
        self.to_splitting()
        plan = json.loads(json.dumps(GROUP_PLAN))
        plan["tests"][0]["children"] = ["signup"]
        self.write("test-plan.json", plan)
        code, out = self.check()
        self.assertEqual(code, 3, out)
        self.assertIn("no required test names two or more features", out)
        self.write("test-plan.json", {"tests": []})
        self.assertIn("at least one required test of the features working together", self.check()[1])

    def test_document_source_needs_page_references(self):
        self.to_splitting()
        doc = json.loads(json.dumps(SPLIT))
        doc["source"] = {"kind": "document", "path": "docs/spec.pptx"}
        doc["children"][0]["code_status"] = "exists"
        self.write("split.json", doc)
        code, out = self.check()
        self.assertEqual(code, 3, out)
        self.assertIn("login: no `sources`", out)
        self.assertIn("list `unread` parts", out)
        self.assertIn("signup: the code already does this", out)

    def test_one_child_is_not_a_group(self):
        self.to_splitting()
        one = json.loads(json.dumps(SPLIT))
        one["children"] = one["children"][:1]
        self.write("split.json", one)
        self.assertIn("at least two `children`", self.check()[1])


class GroupFlowTest(GroupBase):
    def test_approval_creates_waiting_features_in_order(self):
        out = self.approve()
        self.assertIn("created: FEAT-002-signup", out)
        r = self.r
        self.assertEqual(r.state("GRP-001")["state"], "delivering")
        self.assertEqual(r.state("FEAT-003")["state"], "proposed")
        self.assertEqual(r.state("FEAT-003")["parent"], "GRP-001-login")
        group = r.root / ".human-rights" / "groups" / "GRP-001-login"
        self.assertEqual(sorted(p.name for p in (group / "features").iterdir()),
                         ["FEAT-002-signup", "FEAT-003-login", "FEAT-004-reset"])
        self.assertFalse((r.root / ".human-rights" / "features" / "FEAT-002-signup").exists())

        code, out = r.hr("start", "-f", "FEAT-003")
        self.assertEqual(code, 3, out)
        self.assertIn("depends on signup", out)

        code, out = r.hr("start", "-f", "GRP-001")
        self.assertEqual(code, 0, out)
        self.assertIn("FEAT-002-signup started", out)
        self.assertIn("group decision GDEC-001: How is a session kept? -> Server-side session cookie", out)
        self.assertEqual(r.state("FEAT-002")["state"], "triaging")

        code, out = r.hr("list")
        self.assertIn("  GRP-001-login  group  delivering", out)
        self.assertIn("*   FEAT-002-signup", out)

    def test_one_feature_at_a_time_then_group_checks(self):
        self.approve()
        r = self.r
        r.hr("start", "-f", "GRP-001")
        code, out = r.hr("transition", "-f", "GRP-001", "integrating")
        self.assertEqual(code, 3, out)
        self.assertIn("features not finished", out)

        out = self.finish("FEAT-002")
        self.assertIn("2 feature(s) left", out)
        r.hr("start", "-f", "GRP-001")
        self.assertEqual(r.state("FEAT-003")["state"], "triaging")
        code, out = r.hr("start", "-f", "FEAT-004")
        self.assertEqual(code, 3, out)
        self.assertIn("still in progress", out)

        self.finish("FEAT-003")
        r.hr("start", "-f", "GRP-001")
        out = self.finish("FEAT-004")
        self.assertIn("every feature is finished", out)

        self.assertEqual(r.hr("transition", "-f", "GRP-001", "integrating")[0], 0)
        code, out = r.hr("transition", "-f", "GRP-001", "completed")
        self.assertEqual(code, 3, out)
        self.assertIn("GTEST-001 = not_run", out)
        r.commit("work")
        self.assertEqual(r.hr("verify", "-f", "GRP-001")[0], 0)
        code, out = r.hr("transition", "-f", "GRP-001", "completed")
        self.assertEqual(code, 0, out)

    def test_changing_the_split_after_approval_needs_approval_again(self):
        self.approve()
        r = self.r
        more = json.loads(json.dumps(SPLIT))
        more["children"] = [c for c in more["children"] if c["key"] != "reset"]
        more["children"].append({"key": "logout", "title": "Log out", "outcome": "A user can end the session",
                                 "verify_alone": "API test: the session is rejected after logout",
                                 "depends_on": ["login"]})
        self.write("split.json", more)
        plan = json.loads(json.dumps(GROUP_PLAN))
        plan["tests"][0]["children"] = ["signup", "login", "logout"]
        self.write("test-plan.json", plan)
        code, out = r.hr("status", "-f", "GRP-001")
        self.assertIn("split approval invalidated", out)
        self.assertEqual(r.state("GRP-001")["state"], "splitting")
        code, out = r.hr("start", "-f", "FEAT-002")
        self.assertEqual(code, 3, out)

        r.hr("transition", "-f", "GRP-001", "awaiting_split_approval")
        code, out = r.hr("approve", "split", "-f", "GRP-001", "--by", "alice")
        self.assertEqual(code, 0, out)
        self.assertIn("created: FEAT-005-logout", out)
        self.assertIn("cancelled: FEAT-004-reset", out)
        self.assertEqual(r.state("FEAT-004")["state"], "cancelled")

    def test_a_child_can_split_again(self):
        self.approve()
        r = self.r
        r.hr("start", "-f", "GRP-001")
        r.hr("size", "-f", "FEAT-002", "compound", "--reason", "email sign up and invite sign up")
        self.assertEqual(r.hr("transition", "-f", "FEAT-002", "splitting")[0], 0)
        st = r.state("FEAT-002")
        self.assertEqual((st["kind"], st["parent"]), ("group", "GRP-001-login"))
        group = r.root / ".human-rights" / "groups" / "GRP-001-login"
        self.assertTrue((group / "groups" / "GRP-002-signup" / ".internal" / "state.json").is_file())
        self.assertEqual(r.state("GRP-001")["children"][0], {"key": "signup", "feature_id": "GRP-002-signup"})
        code, out = r.hr("list")
        self.assertIn("  GRP-002-signup  group  splitting", out)

    def test_a_group_with_features_cannot_become_one_feature(self):
        self.approve()
        r = self.r
        more = json.loads(json.dumps(SPLIT))
        more["summary"] = "Account access, revised"
        self.write("split.json", more)
        r.hr("status", "-f", "GRP-001")
        self.assertEqual(r.state("GRP-001")["state"], "splitting")
        code, out = r.hr("transition", "-f", "GRP-001", "clarifying")
        self.assertEqual(code, 3, out)
        self.assertIn("already has features", out)

    def test_the_old_feat_id_still_finds_the_group(self):
        self.approve()
        code, out = self.r.hr("status", "-f", "FEAT-001")
        self.assertEqual(code, 0, out)
        self.assertIn("GRP-001-login", out)

    def test_split_approval_comes_from_chat(self):
        r = self.r
        self.to_splitting()
        r.hr("transition", "awaiting_split_approval")
        hint = r.say("목록 좋아. 승인할게")
        self.assertIn("approval of the split into features", hint)
        code, out = r.hr("approve", "split", "--quote", "승인할게")
        self.assertEqual(code, 0, out)
        r.hr("transition", "-f", "GRP-001", "splitting")

    def test_rejecting_the_split_goes_back_to_splitting(self):
        r = self.r
        self.to_splitting()
        r.hr("transition", "awaiting_split_approval")
        code, out = r.hr("reject", "split", "--reason", "merge reset into login", "--by", "alice")
        self.assertEqual(code, 0, out)
        self.assertEqual(r.state()["state"], "splitting")


class GroupDocsTest(GroupBase):
    def test_overview_shows_features_decisions_and_exclusions(self):
        self.approve()
        r = self.r
        r.hr("render", "-f", "GRP-001")
        text = (self.gdir / "overview.md").read_text(encoding="utf-8")
        self.assertIn("flowchart LR", text)
        self.assertIn("f1 --> f2", text)
        self.assertIn("| 2 | **Log in** (`login`)<br>FEAT-003-login |", text)
        child = r.feature_dir("FEAT-003")
        (child / "overview.md").write_text("# Log in\n", encoding="utf-8")
        r.hr("render", "-f", "GRP-001")
        text = (self.gdir / "overview.md").read_text(encoding="utf-8")
        self.assertIn("<br>[FEAT-003-login](features/FEAT-003-login/overview.md) |", text)
        self.assertIn("| GDEC-001 | How is a session kept? | Server-side session cookie | you |", text)
        self.assertIn("| Social login | Not requested for this release | - |", text)
        self.assertIn("| signup, login, reset | GTEST-001", text)
        self.assertIn("0 of 3 features done", text)
        for line in text.splitlines():
            if line.startswith("[FILL") or "[FILL" in line:
                text = text.replace(line, "filled in")
        (self.gdir / "overview.md").write_text(text, encoding="utf-8")
        code, out = r.hr("doc-check", "-f", "GRP-001")
        self.assertEqual(code, 0, out)

    def test_unread_parts_of_a_document_are_listed_for_the_human(self):
        self.to_splitting()
        doc = json.loads(json.dumps(SPLIT))
        doc["source"] = {"kind": "document", "path": "docs/spec.pptx",
                         "unread": [{"ref": "p.13", "reason": "the formula is an image"}]}
        for c in doc["children"]:
            c["sources"] = ["p.92"]
        self.write("split.json", doc)
        self.r.hr("render")
        text = (self.gdir / "overview.md").read_text(encoding="utf-8")
        self.assertIn("Not read - check these yourself", text)
        self.assertIn("| p.13 | the formula is an image |", text)
        self.assertIn("`docs/spec.pptx`", text)

    def test_korean_group_overview(self):
        r = Repo()
        try:
            r.hr("init", "--language", "ko")
            r.hr("new", "로그인 추가", "--slug", "login")
            r.hr("size", "compound", "--reason", "가입과 로그인은 따로 검증된다")
            r.hr("transition", "splitting")
            gdir = r.feature_dir()
            (gdir / ".internal" / "split.json").write_text(json.dumps(SPLIT), encoding="utf-8")
            (gdir / ".internal" / "test-plan.json").write_text(json.dumps(GROUP_PLAN), encoding="utf-8")
            r.hr("scaffold")
            r.hr("render")
            text = (gdir / "overview.md").read_text(encoding="utf-8")
            self.assertIn("| 모드 | 묶음 |", text)
            self.assertIn("단독 검증 방법", text)
            self.assertIn("요청에 있지만 여기서 만들지 않는 것", text)
        finally:
            r.cleanup()


class MigrationTest(GroupBase):
    def old_layout(self):
        r = self.r
        wf = r.root / ".human-rights"
        group = wf / "groups" / "GRP-001-login"
        for child in sorted((group / "features").iterdir()):
            st = json.loads((child / ".internal" / "state.json").read_text(encoding="utf-8"))
            st["parent"] = "FEAT-001-login"
            (child / ".internal" / "state.json").write_text(json.dumps(st), encoding="utf-8")
            child.rename(wf / "features" / child.name)
        (group / "features").rmdir()
        st = json.loads((group / ".internal" / "state.json").read_text(encoding="utf-8"))
        st["feature_id"] = "FEAT-001-login"
        (group / ".internal" / "state.json").write_text(json.dumps(st), encoding="utf-8")
        group.rename(wf / "features" / "FEAT-001-login")
        (wf / "groups").rmdir()
        (wf / "active.json").write_text(json.dumps({"feature_id": "FEAT-001-login"}), encoding="utf-8")
        return wf

    def test_an_old_workspace_keeps_working_and_migrates(self):
        self.approve()
        r = self.r
        integrity = r.hr("check", "-f", "GRP-001")[1]
        self.assertNotIn("event", integrity)
        wf = self.old_layout()
        code, out = r.hr("list")
        self.assertEqual(code, 0, out)
        self.assertIn("old layout", out)
        self.assertIn("* FEAT-001-login  group  delivering", out)

        code, out = r.hr("migrate", "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("features/FEAT-001-login -> groups/GRP-001-login", out)
        self.assertIn("features/FEAT-003-login -> groups/GRP-001-login/features/FEAT-003-login", out)
        self.assertTrue((wf / "features" / "FEAT-001-login").is_dir())

        code, out = r.hr("migrate")
        self.assertEqual(code, 0, out)
        group = wf / "groups" / "GRP-001-login"
        self.assertEqual(sorted(p.name for p in (group / "features").iterdir()),
                         ["FEAT-002-signup", "FEAT-003-login", "FEAT-004-reset"])
        self.assertEqual(list((wf / "features").iterdir()), [])
        self.assertEqual(r.state("GRP-001")["feature_id"], "GRP-001-login")
        self.assertEqual(r.state("FEAT-002")["parent"], "GRP-001-login")
        self.assertEqual(json.loads((wf / "active.json").read_text(encoding="utf-8"))["feature_id"], "GRP-001-login")
        self.assertEqual(r.hr("check", "-f", "GRP-001")[1], integrity)
        self.assertNotIn("event", r.hr("check", "-f", "FEAT-002")[1])
        self.assertIn("layout is current", r.hr("migrate")[1])
        self.assertNotIn("old layout", r.hr("list")[1])

        code, out = r.hr("start", "-f", "GRP-001")
        self.assertEqual(code, 0, out)
        self.assertIn("FEAT-002-signup started (part of GRP-001-login)", out)


class OrdinaryFeatureUnaffectedTest(unittest.TestCase):
    def test_feature_cannot_use_group_transitions(self):
        r = Repo()
        try:
            r.hr("init")
            r.hr("new", "Multi-vehicle control", "--slug", "multi-drone")
            r.hr("classify", "--axes", L3_AXES, "--flags", "vehicle_command", "--size", "single",
                 "--size-reason", "one session model")
            install_example_plan(r)
            r.hr("transition", "planning")
            code, out = r.hr("transition", "delivering")
            self.assertEqual(code, 3, out)
        finally:
            r.cleanup()


if __name__ == "__main__":
    unittest.main()
