import json
import unittest

from helpers import L0_AXES, L3_AXES, ONE, Repo, git, install_example_plan
from runtime import docs, size
from runtime.config import DEFAULTS
from runtime.state.store import Workspace

CFG = size.settings(DEFAULTS)


def lines(n: int) -> str:
    return "".join(f"line {i}\n" for i in range(n))


class PatternTest(unittest.TestCase):
    def kinds(self, *paths):
        return {p: size._kind(p, CFG) for p in paths}

    def test_defaults_cover_common_ecosystems(self):
        got = self.kinds("tests/test_a.py", "pkg/test_b.py", "pkg/b_test.py", "web/app.test.tsx", "web/app.spec.js",
                         "web/__tests__/a.js", "cmd/main_test.go", "src/test/java/FooTest.java", "src/FooTests.kt",
                         "tests/it.rs", "App.Tests/UnitTest1.cs", "Core/WidgetTests.cs", "src/app.py", "pkg/contest.py",
                         "package-lock.json", "web/yarn.lock")
        tests = {p for p, k in got.items() if k == "tests"}
        self.assertEqual(tests, {"tests/test_a.py", "pkg/test_b.py", "pkg/b_test.py", "web/app.test.tsx",
                                 "web/app.spec.js", "web/__tests__/a.js", "cmd/main_test.go",
                                 "src/test/java/FooTest.java", "src/FooTests.kt", "tests/it.rs",
                                 "App.Tests/UnitTest1.cs", "Core/WidgetTests.cs"})
        self.assertEqual(got["package-lock.json"], "locks")
        self.assertEqual(got["web/yarn.lock"], "locks")
        self.assertEqual(got["pkg/contest.py"], "code")

    def test_config_replaces_the_defaults(self):
        cfg = size.settings({"size": {"test_patterns": ["checks/**"], "lockfiles": "my.lock"}})
        self.assertEqual(size._kind("checks/a.py", cfg), "tests")
        self.assertEqual(size._kind("tests/a.py", cfg), "code")
        self.assertEqual(size._kind("deep/my.lock", cfg), "locks")
        self.assertEqual(cfg["manifests"], DEFAULTS["size"]["manifests"])


class ReaderTest(unittest.TestCase):
    def test_manifests(self):
        self.assertEqual(size._package_json('{"dependencies": {"a": "1"}, "devDependencies": {"b": "2"}}'), {"a", "b"})
        self.assertEqual(size._pyproject('[project]\ndependencies = ["Req>=2", "x"]\n[project.optional-dependencies]\n'
                                         'dev = ["pytest"]\n[tool.poetry.dependencies]\npython = "^3.9"\nrich = "1"\n'),
                         {"req", "x", "pytest", "rich"})
        self.assertEqual(size._cargo('[dependencies]\nserde = "1"\n[dev-dependencies]\ninsta = "1"\n'), {"serde", "insta"})
        self.assertEqual(size._requirements("# c\n-r other.txt\nflask==2\nrequests\n"), {"flask", "requests"})
        self.assertEqual(size._gomod("module m\n\nrequire (\n\tgithub.com/a/b v1.2.3\n\tgolang.org/x/y v0.1.0 // indirect\n)\n"
                                     "require github.com/c/d v1.0.0\n"), {"github.com/a/b", "golang.org/x/y", "github.com/c/d"})
        self.assertEqual(size._pom("<dependencies><dependency><groupId>g</groupId><artifactId>a</artifactId>"
                                   "</dependency></dependencies>"), {"g:a"})
        self.assertEqual(size._gradle("implementation 'g:a:1'\ntestImplementation(\"h:b:2\")\n"), {"g:a", "h:b"})
        self.assertEqual(size._nuget('<PackageReference Include="Newtonsoft.Json" Version="13" />'), {"Newtonsoft.Json"})
        self.assertEqual(size._gemfile("gem 'rails', '~> 7'\n"), {"rails"})

    def test_lock_files(self):
        self.assertEqual(size._package_lock('{"packages": {"": {}, "node_modules/a": {}, "node_modules/a/node_modules/b": {}}}'),
                         {"a", "b"})
        self.assertEqual(size._yarn_lock('# x\n"@s/a@^1", "@s/a@^1.2":\n  version "1"\nb@^2:\n  version "2"\n'), {"@s/a", "b"})
        self.assertEqual(size._toml_packages('[[package]]\nname = "a"\nversion = "1"\n\n[[package]]\nname = "b"\n'), {"a", "b"})
        self.assertEqual(size._go_sum("github.com/a/b v1 h1:x\ngithub.com/a/b v1/go.mod h1:y\n"), {"github.com/a/b"})


class SizeTest(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.r.hr("init")

    def tearDown(self):
        self.r.cleanup()

    def feature(self):
        return Workspace(self.r.root).resolve(None)

    def test_l0_summary_counts_code_tests_and_dependencies(self):
        self.r.write("package.json", '{"dependencies": {"left": "1"}}')
        self.r.commit("manifest")
        self.r.hr("new", "Center login card")
        self.r.hr("classify", "--axes", L0_AXES)
        self.r.write("src/new.py", lines(4))
        self.r.write("src/app.py", "print('hello')\nprint('more')\n")
        self.r.write("tests/test_new.py", lines(6))
        self.r.write("package.json", '{"dependencies": {"left": "1", "leaflet": "1.9"}}')
        self.r.commit("work")
        code, out = self.r.hr("scaffold", "l0-summary")
        self.assertEqual(code, 0, out)
        code, out = self.r.hr("render")
        self.assertEqual(code, 0, out)
        text = (self.r.feature_dir() / "overview.md").read_text(encoding="utf-8")
        self.assertIn("4 file(s): 2 added, 2 changed, 0 deleted. Code +6 / -1 lines, tests +6 / -0.", text)
        self.assertIn("New dependencies: `leaflet` (package.json).", text)

    def test_uncommitted_work_is_counted_for_a_small_change(self):
        self.r.hr("new", "Center login card")
        self.r.hr("classify", "--axes", L0_AXES)
        self.r.write("src/app.py", "print('hello')\nprint('more')\n")
        self.r.write("src/new.py", lines(3))
        code, out = self.r.hr("change-size")
        self.assertEqual(code, 0, out)
        self.assertIn("2 file(s): 1 added, 1 changed, 0 deleted. Code +4 / -0 lines", out)

    def test_nothing_changed_and_no_git(self):
        self.r.hr("new", "Center login card")
        code, out = self.r.hr("change-size")
        self.assertIn("No file has changed since", out)
        plain = Repo(use_git=False)
        try:
            plain.hr("init")
            plain.hr("new", "Center login card")
            code, out = plain.hr("change-size")
            self.assertEqual(code, 0, out)
            self.assertIn("not available", out)
        finally:
            plain.cleanup()

    def test_lock_file_lines_are_kept_out_of_code(self):
        self.r.hr("new", "Center login card")
        self.r.hr("classify", "--axes", L0_AXES)
        self.r.write("package-lock.json", json.dumps({"packages": {"": {}, "node_modules/leaflet": {}, "node_modules/x": {}}}, indent=2))
        self.r.write("src/new.py", lines(2))
        self.r.commit("work")
        data = size.measure(self.feature())
        self.assertEqual(data["total"]["code"]["plus"], 2)
        self.assertGreater(data["total"]["locks"]["plus"], 2)
        self.assertEqual(data["dependencies"]["locked"], 2)
        self.assertEqual(data["dependencies"]["added"], [])

    def test_deleted_and_renamed_files(self):
        self.r.write("src/old.py", lines(5))
        self.r.commit("old file")
        self.r.hr("new", "Center login card")
        self.r.hr("classify", "--axes", L0_AXES)
        (self.r.root / "src" / "old.py").unlink()
        self.r.write("src/app.py", "print('changed')\n")
        self.r.commit("work")
        data = size.measure(self.feature())
        self.assertEqual((data["total"]["code"]["changed"], data["total"]["code"]["deleted"]), (1, 1))
        self.assertEqual(data["total"]["code"]["minus"], 6)

    def test_a_manifest_with_no_reader_is_reported_not_skipped(self):
        self.r.write(".human-rights/config.yaml", "size:\n  manifests: [\"*.gemspec\", \"package.json\"]\n")
        self.r.hr("new", "Center login card")
        self.r.hr("classify", "--axes", L0_AXES)
        self.r.write("lib.gemspec", "spec.add_dependency 'x'\n")
        self.r.write("package.json", '{"dependencies": {"a": "1"}}')
        self.r.commit("work")
        out = docs.size_block(self.feature())
        self.assertIn("New dependencies: `a` (package.json).", out)
        self.assertIn("Changed, and not read: `lib.gemspec`.", out)

    def test_removed_dependencies_are_listed(self):
        self.r.write("package.json", '{"dependencies": {"a": "1", "b": "1"}}')
        self.r.commit("manifest")
        self.r.hr("new", "Center login card")
        self.r.hr("classify", "--axes", L0_AXES)
        self.r.write("package.json", '{"dependencies": {"a": "2"}}')
        self.r.commit("work")
        deps = size.measure(self.feature())["dependencies"]
        self.assertEqual((deps["added"], [x["name"] for x in deps["removed"]]), ([], ["b"]))

    def test_korean_block(self):
        self.r.write(".human-rights/config.yaml", "docs:\n  language: ko\n")
        self.r.hr("new", "로그인 카드")
        self.r.hr("classify", "--axes", L0_AXES)
        self.r.write("src/new.py", lines(2))
        self.r.commit("work")
        code, out = self.r.hr("change-size")
        self.assertIn("파일 1개: 추가 1, 수정 0, 삭제 0. 코드 +2 / -0 줄", out)


class TaskSizeTest(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.r.hr("init")
        self.r.hr("new", "Multi-vehicle control", "--slug", "multi-drone")
        self.r.hr("classify", "--axes", L3_AXES, *ONE, "--flags", "vehicle_command")
        self.fdir = install_example_plan(self.r)
        self.base = self.r.state()["git"]["base_sha"]

    def tearDown(self):
        self.r.cleanup()

    def feature(self):
        return Workspace(self.r.root).resolve(None)

    def mark(self, tid, sha=None, worktree=False, status="verified"):
        path = self.fdir / ".internal" / "task-graph.json"
        graph = json.loads(path.read_text(encoding="utf-8"))
        for x in graph["tasks"]:
            if x["id"] == tid:
                x["status"] = status
                if sha:
                    x["verified_evidence"] = {"commit_sha": sha, "worktree": worktree}
        path.write_text(json.dumps(graph), encoding="utf-8")

    def rows(self):
        return {x["id"]: x for x in size.measure(self.feature())["tasks"]}

    def test_each_task_is_counted_from_its_own_commits(self):
        self.r.write("src/link/registry.py", lines(10))
        self.r.write("tests/test_registry.py", lines(7))
        c1 = self.r.commit("TASK-001")
        self.r.write("src/command/router.py", lines(5))
        self.r.write("src/extra.py", lines(3))
        c2 = self.r.commit("TASK-002")
        self.mark("TASK-001", c1)
        self.mark("TASK-002", c2)
        rows = self.rows()
        self.assertEqual(rows["TASK-001"]["basis"], "commits")
        self.assertEqual(rows["TASK-001"]["size"]["code"]["plus"], 10)
        self.assertEqual(rows["TASK-001"]["size"]["tests"]["plus"], 7)
        self.assertEqual(rows["TASK-002"]["size"]["code"]["plus"], 8)
        self.assertEqual(rows["TASK-002"]["paths"], ["src/command/router.py", "src/extra.py"])
        self.assertEqual(rows["TASK-002"]["range"], [c1, c2])
        self.assertEqual(rows["TASK-003"]["basis"], "scope")
        self.assertEqual(rows["TASK-003"]["paths"], [])

    def test_a_worktree_task_is_counted_from_where_its_branch_started(self):
        self.r.write("src/link/registry.py", lines(10))
        c1 = self.r.commit("TASK-001")
        git(self.r.root, "checkout", "-q", "-b", "hr/FEAT-001/TASK-003")
        self.r.write("src/link/reconnect.py", lines(4))
        c3 = self.r.commit("TASK-003")
        git(self.r.root, "checkout", "-q", "-")
        self.r.write("src/command/router.py", lines(5))
        c2 = self.r.commit("TASK-002")
        git(self.r.root, "merge", "-q", "--no-ff", "--no-edit", "hr/FEAT-001/TASK-003")
        merged = git(self.r.root, "rev-parse", "HEAD")
        self.r.write("src/ui/vehicle_selector.py", lines(2))
        c4 = self.r.commit("TASK-004")
        st = self.r.state()
        st["parallel"] = {"worktrees": {"TASK-003": {"base_sha": c1, "status": "merged", "merged_into": merged}}}
        (self.fdir / ".internal" / "state.json").write_text(json.dumps(st), encoding="utf-8")
        self.mark("TASK-001", c1)
        self.mark("TASK-002", c2)
        self.mark("TASK-003", c3, worktree=True)
        self.mark("TASK-004", c4)
        rows = self.rows()
        self.assertEqual(rows["TASK-003"]["paths"], ["src/link/reconnect.py"])
        self.assertEqual(rows["TASK-002"]["paths"], ["src/command/router.py"])
        self.assertEqual(rows["TASK-004"]["paths"], ["src/ui/vehicle_selector.py"])
        self.assertEqual(rows["TASK-004"]["range"], [merged, c4])

    def test_a_task_with_no_recorded_commit_is_attributed_by_its_paths(self):
        self.r.write("src/link/registry.py", lines(10))
        self.r.write("src/link/session.py", lines(2))
        self.r.write("src/stray.py", lines(3))
        self.r.commit("everything at once")
        rows = self.rows()
        self.assertEqual(rows["TASK-001"]["basis"], "scope")
        self.assertEqual(rows["TASK-001"]["size"]["code"]["plus"], 12)
        data = size.measure(self.feature())
        self.assertEqual(data["outside"]["code"]["plus"], 3)

    def test_a_task_commit_that_is_no_longer_in_history_falls_back_to_its_paths(self):
        self.r.write("src/link/registry.py", lines(10))
        self.r.commit("TASK-001")
        self.mark("TASK-001", "0" * 40)
        self.assertEqual(self.rows()["TASK-001"]["basis"], "scope")

    def test_final_block_has_totals_dependencies_and_a_row_per_task(self):
        self.r.write("src/link/registry.py", lines(10))
        self.r.write("requirements.txt", "flask\n")
        c1 = self.r.commit("TASK-001")
        self.mark("TASK-001", c1)
        self.r.hr("render")
        text = (self.fdir / "overview.md").read_text(encoding="utf-8")
        block = text.split("<!-- hr:size:start -->")[1].split("<!-- hr:size:end -->")[0]
        self.assertIn("| Code | 2 | 0 | 0 | +11 | -0 |", block)
        self.assertIn("New dependencies: `flask` (requirements.txt).", block)
        self.assertIn("| TASK-001 | Replace the global single-connection object", block)
        self.assertIn("2 / 0 / 0 | +11 / -0 | +0 / -0 | the task's commits |", block)
        self.assertIn("| TASK-002 |", block)

    def test_a_template_without_the_block_still_renders_and_passes_the_check(self):
        for name in ("overview.md", "verification.md"):
            path = self.fdir / name
            text = path.read_text(encoding="utf-8")
            start, end = "<!-- hr:size:start -->", "<!-- hr:size:end -->"
            if start in text:
                path.write_text(text.replace(start, "").replace(end, ""), encoding="utf-8")
        code, out = self.r.hr("render")
        self.assertEqual(code, 0, out)
        self.assertNotIn("hr:size", (self.fdir / "overview.md").read_text(encoding="utf-8"))
        self.assertEqual([e for e in docs.check_docs(self.feature())["errors"] if "size" in e], [])

    def test_the_block_does_not_change_the_focus_list(self):
        self.r.write("src/link/registry.py", lines(10))
        self.r.commit("TASK-001")
        self.r.hr("render")
        text = (self.fdir / "overview.md").read_text(encoding="utf-8")
        with_block = docs.focus_block(self.feature(), text)
        stripped = text.replace("<!-- hr:size:start -->", "").replace("<!-- hr:size:end -->", "")
        self.assertEqual(docs.focus_block(self.feature(), stripped), with_block)

    def test_korean_task_table(self):
        self.r.write(".human-rights/config.yaml", "docs:\n  language: ko\n")
        self.r.write("src/link/registry.py", lines(10))
        c1 = self.r.commit("TASK-001")
        self.mark("TASK-001", c1)
        out = docs.size_block(self.feature())
        self.assertIn("파일 추가 / 수정 / 삭제", out)
        self.assertIn("작업의 커밋", out)


if __name__ == "__main__":
    unittest.main()
