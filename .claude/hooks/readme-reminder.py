#!/usr/bin/env python3
"""PostToolUse hook: nudge Claude to consider README.md when files change.

Reads the hook payload on stdin and emits a hookSpecificOutput JSON that
injects a system-reminder into the model's context. Skips when the edit
target IS README.md (no feedback loop). Fails silently on any error so a
broken hook never blocks a tool call.
"""
import json
import sys


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    file_path = (
        (payload.get("tool_input") or {}).get("file_path")
        or (payload.get("tool_response") or {}).get("filePath")
        or ""
    )
    # Skip README.md edits to avoid a self-reinforcing reminder loop.
    if file_path.endswith("README.md"):
        return
    msg = (
        "Edit complete. If this change touches user-facing behavior "
        "(Company dataclass shape, WEIGHTS, schedule, env vars, scan output "
        "format, architecture), update README.md to match. Skip if the edit "
        "was internal-only (typo, rename, refactor with no API change)."
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": msg,
        },
    }))


if __name__ == "__main__":
    main()