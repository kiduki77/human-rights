#!/usr/bin/env python3
import json
import re
import sys

HUMAN_ONLY = re.compile(
    r"(?:\bhr(?:\.py|\.cmd)?|runtime[/\\]+hr\.py)[\"']?\s+(?:[^|;&\n]*\s)?(approve|record-manual|unblock|flag|redpill\s+(?:on|off|reveal))\b"
)
PROTECTED = re.compile(
    r"\.workflow[/\\]+features[/\\]+[^/\\]+[/\\]+\.internal[/\\]+"
    r"(state\.json|test-results\.json|failures\.json|events\.jsonl|redpill\.json|logs[/\\])"
)
WRITE_HINT = re.compile(
    r"(>|\btee\b|\bsed\s+-i|\bperl\s+-[a-z]*i|\bcp\b|\bmv\b|\brm\b|\bdd\b|Set-Content|Add-Content|Out-File|"
    r"Copy-Item|Move-Item|Remove-Item|New-Item|\bopen\(|write_text|WriteAllText|\btruncate\b)",
    re.I,
)


def deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }, ensure_ascii=False))
    sys.exit(0)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    tool = data.get("tool_name", "")
    inp = data.get("tool_input") or {}

    if tool in ("Bash", "PowerShell"):
        cmd = inp.get("command", "") or ""
        m = HUMAN_ONLY.search(cmd)
        if m:
            deny(
                f"human-rights: `{m.group(1)}` is a human-only command. The agent cannot approve, record manual "
                f"test results, or release an escalation. Ask the user to run it themselves: `! .workflow/hr {m.group(1)} ...`"
            )
        if PROTECTED.search(cmd) and WRITE_HINT.search(cmd):
            deny(
                "human-rights: state.json / test-results.json / failures.json / events.jsonl / logs are written only by "
                "the hr runtime. Use `hr transition` for state changes and `hr verify` for test results."
            )
        sys.exit(0)

    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        path = inp.get("file_path") or inp.get("notebook_path") or ""
        if PROTECTED.search(path.replace("\\", "/")):
            deny(
                "human-rights: this file is written only by the hr runtime (single state writer). "
                "Edit only requirements.json / task-graph.json / test-plan.json and the human-facing Markdown."
            )
    sys.exit(0)


if __name__ == "__main__":
    main()
