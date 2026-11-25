import json
import re
import unittest

from helpers import L3_AXES, ONE, Repo, install_example_plan
from runtime import docs, redpill
from runtime.state.store import Workspace
from test_redpill_levels import CANDIDATES, FILLERS, Seq

START, END = "<!-- hr:focus:start -->", "<!-- hr:focus:end -->"


def focus_of(text):
    return text.split(START)[1].split(END)[0]


def ids_in(text):
    return set(re.findall(r"\*\*([A-Z]+-\d+)\*\*", text))


def mutate(block, target, field, replacement, **extra):
    return dict({"op": "mutate", "block": block, "target": target, "field": field, "replacement": replacement,
                 "difficulty": "normal", "category": "unsafe_shortcut",
                 "why_wrong": "A plant for the focus tests, long enough to pass validation."}, **extra)


def add(block, title, **extra):
    return dict({"op": "add", "block": block, "title": title, "difficulty": "normal", "category": "unsafe_shortcut",
                 "why_wrong": "A plant for the focus tests, long enough to pass validation."}, **extra)


class FocusBase(unittest.TestCase):
    language = None

    def setUp(self):
        self.r = Repo()
        r = self.r
        if self.language:
            r.hr("init", "--language", self.language)
        else:
            r.hr("init")
        r.hr("new", "Multi-vehicle control", "--slug", "multi-drone")
        r.hr("classify", "--axes", L3_AXES, *ONE, "--flags", "vehicle_command")
        self.fdir = install_example_plan(r)
        r.hr("transition", "planning")

    def tearDown(self):
        self.r.cleanup()

    def feature(self):
        return Workspace(self.r.root).resolve(None)

    def overview(self):
        return (self.fdir / "overview.md").read_text(encoding="utf-8")

    def focus(self):
        return focus_of(self.overview())

    def plant(self, cand):
        r = self.r
        r.hr("redpill", "on", "--one-in", "1", "--difficulty", cand["difficulty"])
        payload = json.dumps({"candidates": [cand] + FILLERS + CANDIDATES["candidates"][:1]})
        path = r.root.parent / (r.root.name + "-cands.json")
        path.write_text(payload, encoding="utf-8")
        try:
            self.assertEqual(r.hr("redpill", "seed", "--gate", "design", "--from", str(path))[0], 0)
            r.hr("transition", "awaiting_design_approval")
            self.assertEqual(r.hr("redpill", "seed", "--gate", "design", "--from", str(path))[0], 0)
        finally:
            path.unlink()
        f = self.feature()
        redpill.on_enter_state(f, "awaiting_design_approval", rng=Seq(pick=0))
        docs.render(f)
        act = redpill.load(f)["active"]
        return act


class PlainRenderTest(FocusBase):
    def test_lists_the_rows_a_reader_should_slow_down_on(self):
        self.r.hr("render")
        focus = self.focus()
        self.assertIn("`vehicle_command` (vehicle command targeting or flight control): what does approving this "
                      "let happen?", focus)
        self.assertEqual(ids_in(focus), {"TASK-002", "TASK-003", "DEC-004"})
        self.assertIn("**DEC-004** Link protocol: not decided by you (existing code)", focus)
        self.assertIn("high risk task", focus)
        for quiet in ("DEC-001", "DEC-002", "DEC-003", "ASM-001", "TASK-001", "TASK-004"):
            self.assertNotIn(quiet, focus)

    def test_flags_come_first_then_the_highest_risk(self):
        self.r.hr("render")
        lines = [l for l in self.focus().splitlines() if l.startswith("- ")]
        self.assertTrue(lines[0].startswith("- `vehicle_command`"))
        self.assertTrue(lines[-1].startswith("- **DEC-004**"))

    def test_the_wording_is_a_pointer_not_a_verdict(self):
        self.r.hr("render")
        focus = self.focus().lower()
        for word in ("wrong", "error", "bad", "reject", "must"):
            self.assertNotIn(word, focus.replace("not because it is wrong", ""))

    def test_an_answer_that_was_overridden_is_listed_with_its_reason(self):
        path = self.fdir / ".internal" / "requirements.json"
        req = json.loads(path.read_text(encoding="utf-8"))
        for d in req["decisions"]:
            if d["id"] == "DEC-004":
                d["overrides_user_answer"] = "Write a new link layer"
                d["reason"] = "The existing library already covers it."
        path.write_text(json.dumps(req), encoding="utf-8")
        self.r.hr("render")
        line = next(l for l in self.focus().splitlines() if "DEC-004" in l)
        self.assertIn("differs from what you answered", line)
        self.assertIn("not decided by you (existing code)", line)
        self.assertEqual(self.focus().count("DEC-004"), 1)

    def test_assumptions_by_risk(self):
        path = self.fdir / ".internal" / "requirements.json"
        req = json.loads(path.read_text(encoding="utf-8"))
        req["assumptions"] += [{"id": "ASM-002", "text": "Links drop at most once a minute", "risk": "medium"},
                               {"id": "ASM-003", "text": "The ground radio is never shared", "risk": "high"}]
        path.write_text(json.dumps(req), encoding="utf-8")
        self.r.hr("render")
        focus = self.focus()
        self.assertIn("**ASM-002** Links drop at most once a minute: assumed for you, medium risk", focus)
        self.assertIn("**ASM-003** The ground radio is never shared: assumed for you, high risk", focus)
        self.assertNotIn("ASM-001", focus)

    def test_a_template_without_the_block_still_renders(self):
        text = self.overview()
        (self.fdir / "overview.md").write_text(re.sub(r"## Read closely\n" + START + ".*?" + END + "\n", "", text,
                                                      flags=re.S), encoding="utf-8")
        self.assertEqual(self.r.hr("render")[0], 0)
        self.assertNotIn(START, self.overview())
        self.assertIn("| DEC-004 |", self.overview())
        self.assertEqual(self.r.hr("doc-check")[0], 0)

    def test_doc_check_passes_with_the_block(self):
        self.r.hr("render")
        self.assertEqual(self.r.hr("doc-check")[0], 0)

    def test_the_cap_counts_the_rest(self):
        f = self.feature()
        rows = "\n".join(f"| ASM-{i:03d} | assumption {i} | high |" for i in range(1, 11))
        text = f"<!-- hr:decisions:start -->\n| ID | Assumption | Risk |\n|---|---|---|\n{rows}\n<!-- hr:decisions:end -->"
        focus = docs.focus_block(f, text)
        self.assertEqual(len(ids_in(focus)), 6)
        self.assertIn("`vehicle_command`", focus)
        self.assertIn("4 more rows match and are not listed here", focus)

    def test_the_cap_is_a_setting(self):
        cfg = self.r.root / ".human-rights" / "config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8").replace("focus_max: 7", "focus_max: 2"), encoding="utf-8")
        self.r.hr("render")
        focus = self.focus()
        self.assertEqual(len([l for l in focus.splitlines() if l.startswith("- ")]), 2)
        self.assertIn("2 more rows match", focus)


class NothingToPointAtTest(unittest.TestCase):
    def test_a_short_line_says_so(self):
        r = Repo()
        try:
            r.hr("init")
            r.hr("new", "Small change", "--slug", "small")
            r.hr("classify", "--axes", L3_AXES, *ONE)
            f = Workspace(r.root).resolve(None)
            text = "\n".join([
                "<!-- hr:tasks:start -->", "| Task | Purpose | Depends on | Risk | Status |", "|---|---|---|---|---|",
                "| [TASK-001](tasks/TASK-001.md) | Do it | - | low | planned |", "<!-- hr:tasks:end -->",
                "<!-- hr:decisions:start -->", "| ID | Question | Decision | Decided by |", "|---|---|---|---|",
                "| DEC-001 | Q | A | you |", "", "| ID | Assumption | Risk |", "|---|---|---|",
                "| ASM-001 | Small | low |", "<!-- hr:decisions:end -->"])
            focus = docs.focus_block(f, text)
            self.assertIn("No row below is decided by someone other than you", focus)
            self.assertNotIn("- ", focus)
        finally:
            r.cleanup()


class KoreanRenderTest(FocusBase):
    language = "ko"

    def test_labels_map_back_from_korean_tables(self):
        self.r.hr("render")
        text = self.overview()
        self.assertIn("| DEC-004 | Link protocol | Keep the existing MAVLink library | 기존 코드 |", text)
        focus = focus_of(text)
        self.assertEqual(ids_in(focus), {"TASK-002", "TASK-003", "DEC-004"})
        self.assertIn("`vehicle_command` (기체 명령 대상 또는 비행 제어 변경): 이것을 승인하면 무엇이 가능해지나요?", focus)
        self.assertIn("**DEC-004** Link protocol: 직접 결정하지 않으심 (기존 코드)", focus)
        self.assertIn("위험 높음 작업", focus)
        self.assertIn("아래 행은 자세히 읽어 주세요", focus)

    def test_a_korean_assumption(self):
        path = self.fdir / ".internal" / "requirements.json"
        req = json.loads(path.read_text(encoding="utf-8"))
        req["assumptions"].append({"id": "ASM-002", "text": "Links drop rarely", "risk": "medium"})
        path.write_text(json.dumps(req), encoding="utf-8")
        self.r.hr("render")
        self.assertIn("**ASM-002** Links drop rarely: 대신 가정함, 위험 보통", self.focus())

    def test_a_planted_decision_credited_to_the_human_is_not_listed(self):
        act = self.plant(mutate("decisions", "DEC-004", "decided_by", "user"))
        self.assertIn("| DEC-004 | Link protocol | Keep the existing MAVLink library | 사용자 |", self.overview())
        self.assertNotIn("DEC-004", self.focus())
        self.assertEqual(act["id"], "DEC-004")


class PlantAgreementTest(FocusBase):
    def table_row(self, rid):
        return next((l for l in self.overview().splitlines() if l.startswith("|") and rid in l.split("|")[1]), None)

    def test_decision_credited_to_the_human_drops_out(self):
        self.r.hr("render")
        self.assertIn("DEC-004", self.focus())
        self.plant(mutate("decisions", "DEC-004", "decided_by", "user"))
        self.assertTrue(self.table_row("DEC-004").rstrip().endswith("| you |"))
        self.assertNotIn("DEC-004", self.focus())

    def test_decision_blamed_on_a_default_shows_up_like_a_real_one(self):
        self.r.hr("render")
        self.assertNotIn("DEC-001", self.focus())
        self.plant(mutate("decisions", "DEC-001", "decided_by", "default"))
        self.assertTrue(self.table_row("DEC-001").rstrip().endswith("| proposed default |"))
        line = next(l for l in self.focus().splitlines() if "DEC-001" in l)
        self.assertEqual(line, "- **DEC-001** Maximum simultaneous vehicles: not decided by you (proposed default)")

    def test_risk_raised_on_a_task(self):
        self.r.hr("render")
        self.assertNotIn("TASK-004", self.focus())
        self.plant(mutate("tasks", "TASK-004", "risk", "high"))
        self.assertIn("| high |", self.table_row("TASK-004"))
        self.assertIn("**TASK-004** Vehicle selection UI: high risk task", self.focus())

    def test_risk_lowered_on_a_task(self):
        self.r.hr("render")
        self.assertIn("TASK-002", self.focus())
        self.plant(mutate("tasks", "TASK-002", "risk", "low"))
        self.assertIn("| low |", self.table_row("TASK-002"))
        self.assertNotIn("TASK-002", self.focus())
        self.assertIn("TASK-003", self.focus())

    def test_risk_raised_on_an_assumption(self):
        self.plant(mutate("decisions", "ASM-001", "risk", "high"))
        self.assertTrue(self.table_row("ASM-001").rstrip().endswith("| high |"))
        line = next(l for l in self.focus().splitlines() if "ASM-001" in l)
        self.assertTrue(line.endswith(": assumed for you, high risk"), line)

    def test_added_medium_assumption(self):
        act = self.plant(add("decisions", "Vehicles on the same link may share a system_id", risk="medium"))
        self.assertEqual(act["id"], "ASM-002")
        self.assertIn("| ASM-002 | Vehicles on the same link may share a system_id | medium |", self.overview())
        self.assertIn("**ASM-002** Vehicles on the same link may share a system_id: assumed for you, medium risk",
                      self.focus())

    def test_added_low_assumption_is_not_listed(self):
        act = self.plant(add("decisions", "Vehicles on the same link may share a system_id", risk="low"))
        self.assertIn(act["id"], self.overview())
        self.assertNotIn(act["id"], self.focus())

    def test_added_high_risk_task(self):
        act = self.plant(add("tasks", "Send commands to every connected vehicle while switching",
                             depends_on="TASK-002", risk="high"))
        self.assertEqual(act["id"], "TASK-005")
        self.assertIn("| high |", self.table_row("TASK-005"))
        self.assertIn("**TASK-005** Send commands to every connected vehicle while switching: high risk task",
                      self.focus())

    def test_removed_high_risk_task_is_not_listed(self):
        self.r.hr("render")
        self.assertIn("TASK-003", self.focus())
        self.plant({"op": "remove", "block": "tasks", "target": "TASK-003", "difficulty": "hard",
                    "category": "silent_exclusion", "against": ["TASK-002"],
                    "why_wrong": "Without this row nothing shows the selector depends on the router."})
        self.assertIsNone(self.table_row("TASK-003"))
        self.assertNotIn("TASK-003", self.focus())
        self.assertIn("TASK-002", self.focus())

    def test_the_block_reads_nothing_but_the_rendered_rows(self):
        self.plant(add("tasks", "Send commands to every connected vehicle while switching",
                       depends_on="TASK-002", risk="high"))
        before = self.overview()
        f = self.feature()
        data = redpill.load(f)
        for key in ("why", "category", "original", "lesson", "technique", "difficulty", "against", "kind", "text"):
            data["active"].pop(key, None)
        redpill.save(f, data)
        docs.render(f)
        self.assertEqual(self.overview(), before)

    def test_the_block_is_the_same_without_a_plant_when_the_rows_are(self):
        self.r.hr("render")
        plain = self.focus()
        self.plant(mutate("tasks", "TASK-001", "depends_on", "TASK-004"))
        self.assertEqual(self.focus(), plain)


if __name__ == "__main__":
    unittest.main()
