from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict

DEFAULT_CONFIG_TEXT = """\
version: 1

routing:
  design_gate_modes: [L3]
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

redpill:
  enabled: false
  one_in: 10
  gates: [design, final]
  language: ""

docs:
  language: en
  l0_summary_max_lines: 15
  overview_max_lines: 120
"""


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
        if value.strip() == "":
            child: Dict[str, Any] = {}
            parent[key.strip()] = child
            stack.append((indent, child))
        else:
            parent[key.strip()] = _scalar(value)
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
