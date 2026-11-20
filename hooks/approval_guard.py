#!/usr/bin/env python3
import json
import re
import sys

HUMAN_ONLY = re.compile(
    r"(?:\bhr(?:\.py|\.cmd)?|runtime[/\\]+hr\.py)[\"']?\s+(?:[^|;&\n]*\s)?(approve|record-manual|unblock|flag|redpill\s+(?:on|off|reveal))\b"
)
PROTECTED = re.compile(
    r"\.(?:human-rights|workflow)[/\\]+(?:(?:features|groups)[/\\]+(?:[^/\\\s\"']+[/\\]+)+?\.internal[/\\]+"
    r"(?:state\.json|test-results\.json|failures\.json|events\.jsonl|redpill(?:-pool)?\.json|logs[/\\])"
    r"|\.local[/\\]+prompts\.jsonl)"
)
SECRET = re.compile(r"redpill(?:-pool)?\.json")
QUOTE = re.compile(r"\s--quote(?:\s|=)")
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
        if m and not QUOTE.search(cmd):
            deny(
                f"human-rights: `{m.group(1)}` is a human decision. Run it only on the human's chat message, "
                f"with their exact words: `.human-rights/hr {m.group(1)} ... --quote \"<their words>\"`. "
                "The runtime checks the quote against the message the human actually sent. "
                "Without one, ask the human to decide in chat."
            )
        if SECRET.search(cmd):
            deny(
                "human-rights: red pill files are read and written only by the hr runtime. Reading them would "
                "spoil a drill. Use `hr redpill status`."
            )
        if PROTECTED.search(cmd) and WRITE_HINT.search(cmd):
            deny(
                "human-rights: state.json / test-results.json / failures.json / events.jsonl / logs are written only by "
                "the hr runtime. Use `hr transition` for state changes and `hr verify` for test results."
            )
        sys.exit(0)

    if tool in ("Read", "Grep") and SECRET.search(str(inp.get("file_path") or inp.get("path") or "")):
        deny(
            "human-rights: red pill files are read only by the hr runtime. Reading them would spoil a drill. "
            "Use `hr redpill status`."
        )
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
