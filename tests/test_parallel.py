import copy
import json
import shutil
import threading
import time
import unittest
from pathlib import Path

from helpers import ONE
from helpers import EXAMPLE, L3_AXES, PLUGIN, PY, Repo, git, install_example_plan
from runtime.scheduler.dag import plan_batch, task_conflicts, test_batches

FILES = {
    "TASK-001": "src/link/registry.py",
    "TASK-002": "src/command/router.py",
    "TASK-003": "src/link/reconnect.py",
    "TASK-004": "src/ui/vehicle_selector.py",
}
CHECKS = {
    "TEST-001": ["src/link/registry.py"],
    "TEST-002": ["src/command/router.py"],
    "TEST-003": ["src/link/reconnect.py"],
    "TEST-004": ["src/ui/vehicle_selector.py"],
    "TEST-010": ["src/command/router.py", "src/ui/vehicle_selector.py"],
    "TEST-011": ["src/link/reconnect.py"],
    "TEST-012": ["src/link/registry.py"],
}


def exists_cmd(paths):
    cond = " and ".join(f"os.path.exists('{p}')" for p in paths)
    return f'{PY} -c "import os,sys,time; time.sleep(0.3); sys.exit(0 if {cond} else 1)"'


def graph():
    return json.loads((EXAMPLE / ".internal" / "task-graph.json").read_text(encoding="utf-8"))


def set_status(g, **st):
    for t in g["tasks"]:
        if t["id"] in st:
            t["status"] = st[t["id"]]
    return g


class DagTest(unittest.TestCase):
    def test_only_roots_are_ready_at_start(self):
        p = plan_batch(graph(), {}, 3)
        self.assertEqual(p["batch"], ["TASK-001"])
        self.assertEqual(set(p["waiting"]), {"TASK-002", "TASK-003", "TASK-004"})

    def test_independent_tasks_run_together(self):
        p = plan_batch(set_status(graph(), **{"TASK-001": "verified"}), {}, 3)
        self.assertEqual(p["batch"], ["TASK-002", "TASK-003"])
        self.assertEqual(p["waiting"], {"TASK-004": ["TASK-002"]})

    def test_unmerged_worktree_dependency_blocks_dependents(self):
        g = set_status(graph(), **{"TASK-001": "verified"})
        p = plan_batch(g, {"TASK-001": {"status": "active"}}, 3)
        self.assertEqual(p["batch"], [])

    def test_overlapping_paths_are_serialized(self):
        g = set_status(graph(), **{"TASK-001": "verified"})
        g["tasks"][2]["scope"]["paths"] = ["src/command/"]
        p = plan_batch(g, {}, 3)
        self.assertEqual(p["batch"], ["TASK-002"])
        self.assertIn("overlapping paths", " ".join(p["deferred"]["TASK-003"]))

    def test_shared_resource_and_unknown_footprint_are_serialized(self):
        g = set_status(graph(), **{"TASK-001": "verified"})
        g["tasks"][1]["resources"] = ["sitl"]
        g["tasks"][2]["resources"] = ["sitl"]
        self.assertIn("shared resources", " ".join(plan_batch(g, {}, 3)["deferred"]["TASK-003"]))
        g = set_status(graph(), **{"TASK-001": "verified"})
        g["tasks"][2]["scope"]["paths"] = []
        self.assertIn("unknown footprint", " ".join(plan_batch(g, {}, 3)["deferred"]["TASK-003"]))

    def test_contract_provider_and_consumer_conflict(self):
        g = graph()
        a, b = copy.deepcopy(g["tasks"][1]), copy.deepcopy(g["tasks"][3])
        self.assertTrue(any("contract" in r for r in task_conflicts(a, b)))

    def test_max_parallel_limits_the_batch(self):
        p = plan_batch(set_status(graph(), **{"TASK-001": "verified"}), {}, 1)
        self.assertEqual(p["batch"], ["TASK-002"])
        self.assertIn("max_parallel", p["deferred"]["TASK-003"][0])

    def test_test_rounds(self):
        tests = [
            {"id": "A", "parallel_safe": True, "resources": ["db"]},
            {"id": "B", "parallel_safe": True},
            {"id": "C", "parallel_safe": True, "resources": ["db"]},
            {"id": "D"},
            {"id": "E", "parallel_safe": True, "exclusive": True},
        ]
        rounds = [[t["id"] for t in r] for r in test_batches(tests, 4)]
        self.assertEqual(rounds, [["A", "B"], ["C"], ["D"], ["E"]])
        self.assertEqual([[t["id"] for t in r] for r in test_batches(tests, 1)], [["A"], ["B"], ["C"], ["D"], ["E"]])


class ParallelFlowTest(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        r = self.r
        r.hr("init")
        r.hr("new", "Multi-vehicle control", "--slug", "multi-drone")
        r.hr("classify", "--axes", L3_AXES, *ONE, "--flags", "vehicle_command")
        fdir = install_example_plan(r)
        plan = json.loads((fdir / ".internal/test-plan.json").read_text(encoding="utf-8"))
        for t in plan["tests"]:
            if t["id"] in CHECKS:
                t["command"] = exists_cmd(CHECKS[t["id"]])
            if t["id"] in ("TEST-002", "TEST-003", "TEST-012"):
                t["parallel_safe"] = True
            if t["id"] in ("TEST-010", "TEST-011"):
                t["parallel_safe"] = True
                t["resources"] = ["sitl-4"]
        (fdir / ".internal/test-plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
        r.hr("transition", "planning")
        code, out = r.hr("transition", "awaiting_design_approval")
        assert code == 0, out
        code, out = r.hr("approve", "design", "--by", "alice")
        assert code == 0, out
        self.wt_root = r.root.parent / f"{r.root.name}.hr-worktrees"

    def tearDown(self):
        shutil.rmtree(self.wt_root, ignore_errors=True)
        self.r.cleanup()

    def ok(self, *argv):
        code, out = self.r.hr(*argv)
        self.assertEqual(code, 0, f"hr {' '.join(argv)}\n{out}")
        return out

    def build_in(self, root: Path, task: str, extra: str = ""):
        p = root / FILES[task]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"# {task}\n{extra}", encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", f"FEAT-001 {task}")

    def worktree(self, task) -> Path:
        return Path(self.r.state()["parallel"]["worktrees"][task]["path"])

    def test_parallel_batch_then_integration_on_merged_code(self):
        r = self.r
        out = self.ok("schedule")
        self.assertIn("next batch: TASK-001", out)
        self.ok("task", "TASK-001", "in_progress")
        self.build_in(r.root, "TASK-001")
        self.ok("task", "TASK-001", "implemented")
        self.ok("verify", "--task", "TASK-001")
        self.ok("task", "TASK-001", "verified")

        out = self.ok("schedule", "--start")
        self.assertIn("started: TASK-002, TASK-003", out)
        self.assertIn("brief for TASK-002", out)
        self.assertIn("Never edit anything under .human-rights/", out)
        self.assertIn("waiting TASK-004", out)
        w2, w3 = self.worktree("TASK-002"), self.worktree("TASK-003")
        self.assertTrue(w2.is_dir() and w3.is_dir())
        self.assertEqual(w2.parent.parent, self.wt_root)
        code, out = r.hr("worktree", "create", "TASK-004")
        self.assertEqual(code, 3, "TASK-004 depends on unmerged TASK-002")

        self.build_in(w2, "TASK-002")
        self.build_in(w3, "TASK-003")
        self.assertFalse((r.root / FILES["TASK-002"]).exists(), "worktree work must not leak into main")
        for t in ("TASK-002", "TASK-003"):
            self.ok("task", t, "implemented")
        start = time.monotonic()
        out = self.ok("verify", "--tasks", "TASK-002", "TASK-003", "--parallel", "2")
        self.assertIn("(worktree TASK-002)", out)
        self.assertIn("[parallel x2]", out)
        self.assertLess(time.monotonic() - start, 3.0)
        for t in ("TASK-002", "TASK-003"):
            self.ok("task", t, "verified")
        results = json.loads((r.feature_dir() / ".internal/test-results.json").read_text(encoding="utf-8"))["runs"]
        main_tree = r.state()
        w2_run = next(x for x in results if x["test_id"] == "TEST-002")
        self.assertEqual(w2_run["worktree_task"], "TASK-002")

        self.ok("transition", "verifying_tasks")
        code, out = r.hr("transition", "integrating")
        self.assertEqual(code, 3)
        self.assertIn("not merged", out)
        self.ok("transition", "executing")

        self.ok("worktree", "merge", "TASK-002", "--remove")
        self.ok("worktree", "merge", "TASK-003", "--remove")
        self.assertTrue((r.root / FILES["TASK-002"]).exists() and (r.root / FILES["TASK-003"]).exists())
        self.assertFalse(w2.exists())

        out = self.ok("schedule", "--start")
        self.assertIn("started: TASK-004", out)
        w4 = self.worktree("TASK-004")
        self.assertTrue((w4 / FILES["TASK-002"]).exists(), "TASK-004 starts from the merged dependency")
        self.build_in(w4, "TASK-004")
        self.ok("task", "TASK-004", "implemented")
        self.ok("verify", "--task", "TASK-004")
        self.ok("task", "TASK-004", "verified")
        self.ok("worktree", "merge", "TASK-004", "--remove")

        self.ok("transition", "verifying_tasks")
        self.ok("transition", "integrating")
        code, out = r.hr("transition", "awaiting_final_approval")
        self.assertEqual(code, 3)
        self.assertIn("stale", out)
        out = self.ok("verify", "--level", "all", "--parallel", "4")
        self.assertIn("[parallel x", out)
        r.hr("record-manual", "TEST-013", "passed", "--by", "bob", "--evidence", "https://example.com/rec")
        self.ok("transition", "awaiting_final_approval")
        self.ok("approve", "final", "--by", "alice")
        st = r.state()
        self.assertEqual(st["approvals"]["final"]["commit_sha"], git(r.root, "rev-parse", "HEAD"))

        m = json.loads(self.ok("metrics", "--json"))
        self.assertEqual(m["verification_coverage"], 1.0)
        self.assertTrue(any(set(b["tasks"]) == {"TASK-002", "TASK-003"} for b in m["parallel_batches"]))

    def test_conflicting_merge_is_aborted_and_task_reworked(self):
        r = self.r
        self.ok("task", "TASK-001", "in_progress")
        self.build_in(r.root, "TASK-001")
        self.ok("task", "TASK-001", "implemented")
        self.ok("verify", "--task", "TASK-001")
        self.ok("task", "TASK-001", "verified")
        self.ok("schedule", "--start")
        w2, w3 = self.worktree("TASK-002"), self.worktree("TASK-003")
        for w, task in ((w2, "TASK-002"), (w3, "TASK-003")):
            (w / "src" / "app.py").write_text(f"print('{task}')\n", encoding="utf-8")
            self.build_in(w, task)
            self.ok("task", task, "implemented")
            self.ok("verify", "--task", task)
            self.ok("task", task, "verified")
        self.ok("worktree", "merge", "TASK-002")
        head = git(r.root, "rev-parse", "HEAD")
        code, out = r.hr("worktree", "merge", "TASK-003")
        self.assertEqual(code, 3)
        self.assertIn("src/app.py", out)
        self.assertEqual(git(r.root, "rev-parse", "HEAD"), head, "integration branch unchanged")
        self.assertEqual(git(r.root, "status", "--porcelain", "--", "src"), "", "merge fully aborted")
        tasks = {t["id"]: t for t in json.loads((r.feature_dir() / ".internal/task-graph.json").read_text(encoding="utf-8"))["tasks"]}
        self.assertEqual(tasks["TASK-003"]["status"], "rework_required")

    def test_changed_after_verification_cannot_merge(self):
        r = self.r
        self.ok("task", "TASK-001", "in_progress")
        self.build_in(r.root, "TASK-001")
        self.ok("verify", "--task", "TASK-001")
        self.ok("task", "TASK-001", "verified")
        self.ok("schedule", "--start", "--max", "1")
        w2 = self.worktree("TASK-002")
        self.build_in(w2, "TASK-002")
        self.ok("verify", "--task", "TASK-002")
        self.ok("task", "TASK-002", "verified")
        self.build_in(w2, "TASK-002", extra="more\n")
        code, out = r.hr("worktree", "merge", "TASK-002")
        self.assertEqual(code, 3)
        self.assertIn("changed after it was verified", out)


class TemplatesMetricsTest(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.r.hr("init")
        self.r.hr("new", "Multi-vehicle control")
        self.r.hr("classify", "--axes", L3_AXES, *ONE, "--flags", "vehicle_command")

    def tearDown(self):
        self.r.cleanup()

    def test_install_customize_update_and_scaffold(self):
        r = self.r
        code, out = r.hr("templates", "install")
        self.assertIn("copied:", out)
        local = r.root / ".human-rights" / "templates" / "overview.md"
        self.assertTrue(local.exists())
        local.write_text(local.read_text(encoding="utf-8") + "\n<!-- ACME review checklist -->\n", encoding="utf-8")
        code, out = r.hr("templates", "status")
        self.assertIn("customized", out)
        code, out = r.hr("templates", "update")
        self.assertIn("kept_customized: overview.md", out)
        self.assertIn("ACME", local.read_text(encoding="utf-8"))

        install_example_plan(r)
        (r.feature_dir() / "overview.md").unlink()
        shutil.rmtree(r.feature_dir() / "tasks")
        code, out = r.hr("scaffold", "overview", "tasks")
        self.assertEqual(code, 0, out)
        ov = (r.feature_dir() / "overview.md").read_text(encoding="utf-8")
        self.assertIn("ACME", ov, "repo template wins over the plugin's")
        self.assertIn("Multi-vehicle control", ov)
        t2 = (r.feature_dir() / "tasks" / "TASK-002.md").read_text(encoding="utf-8")
        self.assertIn("Route commands to the selected vehicle", t2)
        self.assertIn("`src/command/router.py`", t2)
        self.assertIn("AC-T2-2", t2)
        self.assertIn("```mermaid", t2, "a task that changes a flow gets a diagram to fill in")
        self.assertNotIn("flow:start", t2)
        t3 = (r.feature_dir() / "tasks" / "TASK-003.md").read_text(encoding="utf-8")
        self.assertNotIn("mermaid", t3)
        self.assertNotIn("[FILL", t3.split("## Result")[0])
        code, out = r.hr("scaffold", "overview")
        self.assertIn("kept existing: overview.md", out)

    def test_org_template_pack(self):
        r = self.r
        pack = r.root / "org-templates"
        pack.mkdir()
        (pack / "overview.md").write_text("# [FILL: feature name]\n\nOrg format\n", encoding="utf-8")
        code, out = r.hr("templates", "install", "--from", str(pack))
        self.assertIn("copied: overview.md", out)
        self.assertEqual(r.hr("scaffold", "overview")[0], 0)
        self.assertIn("Org format", (r.feature_dir() / "overview.md").read_text(encoding="utf-8"))

    def test_metrics_record_and_compute(self):
        r = self.r
        r.hr("metrics", "record", "--kind", "tokens", "--value", "12000")
        r.hr("metrics", "record", "--kind", "tokens", "--value", "3000")
        r.hr("metrics", "record", "--kind", "review_minutes", "--value", "7", "--by", "human:alice")
        code, out = r.hr("metrics", "record", "--kind", "bogus")
        self.assertEqual(code, 2)
        m = json.loads(r.hr("metrics", "--json")[1])
        self.assertEqual(m["tokens"], 15000)
        self.assertEqual(m["human_review_minutes"], 7)
        self.assertGreaterEqual(m["lead_time_s"], 0)
        agg = json.loads(r.hr("metrics", "--all", "--json")[1])
        self.assertEqual(agg["features"], 1)
        self.assertEqual(agg["total_tokens"], 15000)


class LockTest(unittest.TestCase):
    def test_heartbeat_keeps_long_holder_alive(self):
        from runtime.common import HRError
        from runtime.state import store

        r = Repo(use_git=False)
        r.hr("init")
        ws = store.Workspace(r.root)
        old = (store.LOCK_STALE_AFTER, store.LOCK_HEARTBEAT)
        store.LOCK_STALE_AFTER, store.LOCK_HEARTBEAT = 1, 0.2
        stolen = []
        try:
            with ws.lock():
                time.sleep(1.5)

                def contender():
                    try:
                        with ws.lock(timeout=0.5):
                            stolen.append(True)
                    except HRError:
                        stolen.append(False)

                t = threading.Thread(target=contender)
                t.start()
                t.join()
            self.assertEqual(stolen, [False])
        finally:
            store.LOCK_STALE_AFTER, store.LOCK_HEARTBEAT = old
            r.cleanup()


if __name__ == "__main__":
    unittest.main()
