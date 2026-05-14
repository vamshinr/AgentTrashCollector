import json
import sys

from . import git, store

GIT_TOOLS = {"Bash", "Edit", "Write", "MultiEdit", "NotebookEdit"}


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    cwd = payload.get("cwd")
    tool_name = payload.get("tool_name")
    event_name = payload.get("hook_event_name")

    event = {
        "ts": store.now_iso(),
        "session_id": payload.get("session_id"),
        "cwd": cwd,
        "event": event_name,
        "tool_name": tool_name,
        "tool_input": payload.get("tool_input"),
        "tool_response": payload.get("tool_response"),
    }

    if cwd and event_name == "PostToolUse" and tool_name in GIT_TOOLS:
        if snap := git.snapshot(cwd):
            event["git"] = snap

    try:
        store.append(event)
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
