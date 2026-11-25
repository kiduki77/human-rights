from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List

SIZE_TEST_PATTERNS = [
    "**/tests/**", "**/test/**", "**/__tests__/**", "**/spec/**", "test_*.py", "*_test.py", "conftest.py",
    "*.test.*", "*.spec.*", "*_test.go", "*Test.java", "*Tests.java", "*Test.kt", "*Tests.kt", "*Test.cs",
    "*Tests.cs", "**/*.Tests/**", "**/*.Test/**",
]
SIZE_MANIFESTS = [
    "package.json", "composer.json", "pyproject.toml", "requirements*.txt", "Pipfile", "go.mod", "Cargo.toml",
    "pom.xml", "build.gradle", "build.gradle.kts", "*.csproj", "Directory.Packages.props", "packages.config", "Gemfile",
]
SIZE_LOCKFILES = [
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock", "Pipfile.lock", "Cargo.lock",
    "go.sum", "composer.lock", "Gemfile.lock", "packages.lock.json", "gradle.lockfile",
]


def _flow(items: List[str]) -> str:
    return "[" + ", ".join(json.dumps(x) for x in items) + "]"


DEFAULT_CONFIG_TEXT = """\
version: 1

routing:
  design_gate_modes: [L2, L3]
  final_gate_modes: [L3]
  l2_design_gate_min_arch: 2

github:
  enabled: auto
  issue_modes: [L2, L3]
  draft_pr_modes: [L2, L3]
  auto_merge: false

verification:
  max_same_failure_retries: 3
  default_timeout_seconds: 900
  max_parallel_tests: 4

scheduler:
  max_parallel_tasks: 3
  worktree_root: ""

groups:
  max_active_children: 1

redpill:
  enabled: false
  one_in: 10
  gates: [design, final]
  difficulty: adaptive
  author: agent
  max_flags: 3
  language: ""

docs:
  language: en
  l0_summary_max_lines: 15
  overview_max_lines: 120
  focus_max: 7
  prose_check: error
  banned_phrases: []
  allowed_phrases: []

size:
  test_patterns: """ + _flow(SIZE_TEST_PATTERNS) + """
  manifests: """ + _flow(SIZE_MANIFESTS) + """
  lockfiles: """ + _flow(SIZE_LOCKFILES) + """

agents:
  preset: balanced
  investigator_model: sonnet
  investigator_effort: medium
  plan_reviewer_model: opus
  plan_reviewer_effort: high
  code_reviewer_model: opus
  code_reviewer_effort: high
  task_worker_model: sonnet
  task_worker_effort: high
  tester_model: sonnet
  tester_effort: high
  redpill_author_model: sonnet
  redpill_author_effort: high
"""

AGENT_ROLES = {
    "investigator": "hr-investigator",
    "plan_reviewer": "hr-plan-reviewer",
    "code_reviewer": "hr-code-reviewer",
    "task_worker": "hr-task-worker",
    "tester": "hr-tester",
    "redpill_author": "hr-redpill-author",
}
AGENT_PRESETS = {
    "balanced": {"investigator": ("sonnet", "medium"), "plan_reviewer": ("opus", "high"),
                 "code_reviewer": ("opus", "high"), "task_worker": ("sonnet", "high"),
                 "tester": ("sonnet", "high"), "redpill_author": ("sonnet", "high")},
    "quality": {"investigator": ("opus", "medium"), "plan_reviewer": ("opus", "high"),
                "code_reviewer": ("opus", "high"), "task_worker": ("opus", "high"),
                "tester": ("opus", "high"), "redpill_author": ("opus", "high")},
    "economy": {"investigator": ("haiku", ""), "plan_reviewer": ("sonnet", "high"),
                "code_reviewer": ("sonnet", "high"), "task_worker": ("sonnet", "medium"),
                "tester": ("sonnet", "medium"), "redpill_author": ("sonnet", "medium")},
    "inherit": {"investigator": ("inherit", ""), "plan_reviewer": ("inherit", ""),
                "code_reviewer": ("inherit", ""), "task_worker": ("inherit", ""),
                "tester": ("inherit", ""), "redpill_author": ("inherit", "")},
}
MODEL_ALIASES = ("sonnet", "opus", "haiku", "fable", "inherit")
EFFORTS = ("low", "medium", "high", "xhigh", "max")


def _scalar(raw: str) -> Any:
    raw = raw.strip()
    if raw == "":
        return None
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        return [_scalar(x) for x in inner.split(",")] if inner else []
    if raw[0] in "\"'" and raw[-1] == raw[0]:
        return raw[1:-1]
    low = raw.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "~"):
        return None
    try:
        return int(raw)
    except ValueError:
        return raw


def _strip_comment(line: str) -> str:
    in_q = None
    for i, ch in enumerate(line):
        if ch in "\"'":
            in_q = None if in_q == ch else (ch if in_q is None else in_q)
        elif ch == "#" and in_q is None and (i == 0 or line[i - 1].isspace()):
            return line[:i]
    return line


def parse_simple_yaml(text: str) -> Dict[str, Any]:
    root: Dict[str, Any] = {}
    stack = [(-1, root)]
    for raw_line in text.splitlines():
        line = _strip_comment(raw_line).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        key, sep, value = line.strip().partition(":")
        if not sep:
            raise ValueError(f"config.yaml: unsupported line: {raw_line!r}")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        key = key.strip()
        if len(key) > 1 and key[0] in "\"'" and key[-1] == key[0]:
            key = key[1:-1]
        if value.strip() == "":
            child: Dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _scalar(value)
    return root


def _deep_merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


DEFAULTS = parse_simple_yaml(DEFAULT_CONFIG_TEXT)


def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return copy.deepcopy(DEFAULTS)
    text = path.read_text(encoding="utf-8")
    try:
        import yaml

        data = yaml.safe_load(text) or {}
    except ImportError:
        data = parse_simple_yaml(text)
    return _deep_merge(DEFAULTS, data)


def set_section(path: Path, section: str, values: Dict[str, Any]) -> None:
    import re

    from runtime.common import write_text_atomic

    text = path.read_text(encoding="utf-8") if path.exists() else ""

    def fmt(v: Any) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, list):
            return "[" + ", ".join(str(x) for x in v) + "]"
        if v is None or v == "":
            return '""'
        return str(v)

    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if re.match(rf"^{re.escape(section)}:\s*$", l)), None)
    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"{section}:")
        start = len(lines) - 1
    end = start + 1
    while end < len(lines) and (lines[end].startswith(" ") or not lines[end].strip()):
        end += 1
    body = lines[start + 1:end]
    for key, val in values.items():
        line = f"  {key}: {fmt(val)}"
        idx = next((i for i, l in enumerate(body) if re.match(rf"^\s+{re.escape(key)}:", l)), None)
        if idx is None:
            while body and not body[-1].strip():
                body.pop()
            body.append(line)
        else:
            body[idx] = line
    lines[start + 1:end] = body + ([""] if end < len(lines) else [])
    write_text_atomic(path, "\n".join(lines).rstrip("\n") + "\n")


def preset_values(name: str) -> Dict[str, Any]:
    if name not in AGENT_PRESETS:
        raise ValueError(f"unknown agent preset {name!r} (choose from: {', '.join(AGENT_PRESETS)})")
    values: Dict[str, Any] = {"preset": name}
    for role, (model, effort) in AGENT_PRESETS[name].items():
        values[f"{role}_model"] = model
        values[f"{role}_effort"] = effort
    return values


def agent_settings(cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    section = cfg.get("agents") or {}
    out = {}
    for role, agent in AGENT_ROLES.items():
        model = str(section.get(f"{role}_model") or "inherit").strip()
        effort = str(section.get(f"{role}_effort") or "").strip()
        problems = []
        if model not in MODEL_ALIASES and not model.startswith("claude-"):
            problems.append(f"unknown model {model!r}")
        if effort and effort not in EFFORTS:
            problems.append(f"unknown effort {effort!r}")
        call = {}
        if model != "inherit":
            call["model"] = model
        if effort:
            call["effort"] = effort
        out[role] = {"agent": agent, "model": model, "effort": effort or None, "agent_call": call,
                     "problems": problems}
    return out
