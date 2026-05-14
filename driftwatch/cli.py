import argparse
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

from . import metrics, store

CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"
HOOK_CMD = f"{sys.executable} -m driftwatch.hook"
TOOL_EVENTS = ("PreToolUse", "PostToolUse")
SESSION_EVENTS = ("Stop",)


def _is_driftwatch(entry: dict) -> bool:
    return any("driftwatch.hook" in (h.get("command") or "") for h in entry.get("hooks", []))


def cmd_init(_args) -> None:
    CLAUDE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    if CLAUDE_SETTINGS.exists():
        settings = json.loads(CLAUDE_SETTINGS.read_text() or "{}")
    else:
        settings = {}

    hooks = settings.setdefault("hooks", {})
    runner = {"hooks": [{"type": "command", "command": HOOK_CMD}]}

    for evt in TOOL_EVENTS:
        bucket = [b for b in hooks.get(evt, []) if not _is_driftwatch(b)]
        bucket.append({"matcher": "", **runner})
        hooks[evt] = bucket

    for evt in SESSION_EVENTS:
        bucket = [b for b in hooks.get(evt, []) if not _is_driftwatch(b)]
        bucket.append(dict(runner))
        hooks[evt] = bucket

    CLAUDE_SETTINGS.write_text(json.dumps(settings, indent=2))
    store.ensure_store()
    print(f"driftwatch: hooks installed in {CLAUDE_SETTINGS}")
    print(f"driftwatch: events will be written to {store.STORE_DIR}")


def cmd_uninstall(args) -> None:
    if not CLAUDE_SETTINGS.exists():
        print(f"driftwatch: no settings file at {CLAUDE_SETTINGS}")
    else:
        settings = json.loads(CLAUDE_SETTINGS.read_text() or "{}")
        hooks = settings.get("hooks", {})
        removed = 0
        for evt in list(hooks.keys()):
            before = len(hooks[evt])
            hooks[evt] = [b for b in hooks[evt] if not _is_driftwatch(b)]
            removed += before - len(hooks[evt])
            if not hooks[evt]:
                del hooks[evt]
        if not hooks:
            settings.pop("hooks", None)
        CLAUDE_SETTINGS.write_text(json.dumps(settings, indent=2))
        print(f"driftwatch: removed {removed} hook entries from {CLAUDE_SETTINGS}")

    root = store.STORE_DIR.parent
    if args.purge:
        shutil.rmtree(root, ignore_errors=True)
        print(f"driftwatch: deleted event store at {root}")
    else:
        print(f"driftwatch: event store at {root} preserved (re-run with --purge to delete)")
    print("driftwatch: run `pip uninstall driftwatch` to remove the package itself")


def cmd_sessions(_args) -> None:
    sessions = store.list_sessions()
    if not sessions:
        print("no sessions captured yet")
        return
    for sid, _ in sessions:
        events = store.read(sid)
        print(f"{sid}  events={len(events)}")


def _resolve_session(arg: str | None) -> str | None:
    if arg:
        return arg
    sessions = store.list_sessions()
    return sessions[0][0] if sessions else None


def cmd_report(args) -> None:
    session = _resolve_session(args.session)
    if not session:
        print("no sessions captured yet — run `driftwatch init` and start Claude Code")
        return
    events = store.read(session)
    if not events:
        print(f"no events for session {session}")
        return

    conv = metrics.convergence(events)
    thr = metrics.thrash(events)
    mom = metrics.momentum(events)

    if args.json:
        print(json.dumps({
            "session": session,
            "events": len(events),
            "convergence": conv,
            "thrash": thr,
            "momentum": mom,
        }, indent=2))
        return

    print(f"session: {session}")
    print(f"events:  {len(events)}")
    print()
    print(f"convergence: {conv['score']:.3f}")
    print(f"  git:      {conv['git']:.3f}")
    print(f"  tests:    {conv['tests']:.3f}")
    print(f"  churn_ok: {conv['churn_ok']:.3f}")
    print()
    flag = "TRIGGERED" if thr["triggered"] else "ok"
    print(f"thrash: {thr['confidence']:.3f} [{flag}]")
    if thr["hot_file"]:
        print(f"  hot file:           {thr['hot_file']}")
    if thr["hot_failing_command"]:
        print(f"  hot failing cmd:    {thr['hot_failing_command']}")
    print()
    print(f"momentum: {mom['state']}  (Δ={mom['delta']:+.3f}, last={mom['last_window']:.3f}, prev={mom['prev_window']:.3f})")


def _bar(v: float, width: int = 22) -> str:
    v = max(0.0, min(1.0, v))
    filled = int(round(v * width))
    return "█" * filled + "░" * (width - filled)


def _render_watch(session: str, events: list[dict]) -> None:
    conv = metrics.convergence(events)
    thr = metrics.thrash(events)
    mom = metrics.momentum(events)
    print("\033[H\033[J", end="")
    print(f"driftwatch — {session}    events={len(events)}    {datetime.now().strftime('%H:%M:%S')}")
    print()
    print(f"convergence  {_bar(conv['score'])}  {conv['score']:.3f}")
    print(f"  git        {_bar(conv['git'])}  {conv['git']:.3f}")
    print(f"  tests      {_bar(conv['tests'])}  {conv['tests']:.3f}")
    print(f"  churn_ok   {_bar(conv['churn_ok'])}  {conv['churn_ok']:.3f}")
    print()
    tag = "  [TRIGGERED]" if thr["triggered"] else ""
    print(f"thrash       {_bar(thr['confidence'])}  {thr['confidence']:.3f}{tag}")
    if thr["hot_file"]:
        print(f"  hot file:  {thr['hot_file']}")
    if thr["hot_failing_command"]:
        print(f"  hot fail:  {thr['hot_failing_command']}")
    print()
    print(f"momentum:    {mom['state']}  Δ={mom['delta']:+.3f}  last={mom['last_window']:.3f}  prev={mom['prev_window']:.3f}")
    print()
    print("recent events:")
    for e in events[-6:]:
        inp = e.get("tool_input") or {}
        detail = inp.get("command") or inp.get("file_path") or ""
        if len(detail) > 58:
            detail = detail[:55] + "..."
        ev = (e.get("event") or "")[:11]
        tn = (e.get("tool_name") or "-")[:11]
        print(f"  {ev:<11}  {tn:<11}  {detail}")
    print()
    print("(ctrl-c to exit)")


def cmd_watch(args) -> None:
    session = _resolve_session(args.session)
    if not session:
        print("no sessions yet — start a Claude Code session first")
        return
    path = store.session_path(session)
    last_count = -1
    try:
        while True:
            events = store.read(session) if path.exists() else []
            if len(events) != last_count:
                _render_watch(session, events)
                last_count = len(events)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print()


def main() -> None:
    p = argparse.ArgumentParser(prog="driftwatch")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="install Claude Code hooks").set_defaults(func=cmd_init)
    u = sub.add_parser("uninstall", help="remove Claude Code hooks")
    u.add_argument("--purge", action="store_true", help="also delete ~/.driftwatch event store")
    u.set_defaults(func=cmd_uninstall)
    sub.add_parser("sessions", help="list captured sessions").set_defaults(func=cmd_sessions)
    r = sub.add_parser("report", help="metrics for a session")
    r.add_argument("session", nargs="?", help="session id (default: most recent)")
    r.add_argument("--json", action="store_true", help="emit JSON instead of text")
    r.set_defaults(func=cmd_report)
    w = sub.add_parser("watch", help="live TUI for a session")
    w.add_argument("session", nargs="?", help="session id (default: most recent)")
    w.add_argument("--interval", type=float, default=0.5, help="poll seconds (default 0.5)")
    w.set_defaults(func=cmd_watch)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
