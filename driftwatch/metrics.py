from collections import Counter
from typing import Iterable

TEST_PATTERNS = (
    "pytest", "jest", "vitest", "mocha", "rspec",
    "go test", "cargo test", "npm test", "npm run test",
    "yarn test", "pnpm test", "unittest", " test ",
)
EDIT_TOOLS = ("Edit", "Write", "MultiEdit")


def _is_test_cmd(cmd: str) -> bool:
    if not cmd:
        return False
    c = cmd.lower()
    return any(p in c for p in TEST_PATTERNS)


def _bash_events(events: Iterable[dict]) -> Iterable[dict]:
    for e in events:
        if e.get("tool_name") == "Bash" and e.get("event") == "PostToolUse":
            yield e


def _edit_events(events: Iterable[dict]) -> Iterable[dict]:
    for e in events:
        if e.get("tool_name") in EDIT_TOOLS and e.get("event") == "PostToolUse":
            yield e


def _bash_exit_code(e: dict) -> int | None:
    resp = e.get("tool_response") or {}
    if not isinstance(resp, dict):
        return None
    for k in ("exit_code", "exitCode", "returncode"):
        if k in resp and isinstance(resp[k], int):
            return resp[k]
    for k in ("is_error", "isError", "error"):
        if k in resp:
            return 1 if resp[k] else 0
    if resp.get("interrupted"):
        return 130
    return None


def _edit_path(e: dict) -> str | None:
    inp = e.get("tool_input") or {}
    return inp.get("file_path")


def test_pass_rate(events: list[dict]) -> float:
    passes = fails = 0
    for e in _bash_events(events):
        cmd = (e.get("tool_input") or {}).get("command", "")
        if not _is_test_cmd(cmd):
            continue
        code = _bash_exit_code(e)
        if code is None:
            continue
        if code == 0:
            passes += 1
        else:
            fails += 1
    total = passes + fails
    return 0.5 if total == 0 else passes / total


def git_trajectory(events: list[dict]) -> float:
    snaps = [e["git"] for e in events if e.get("git")]
    if not snaps:
        return 0.5
    distinct_heads = len({s["head"] for s in snaps})
    commits = max(0, distinct_heads - 1)
    max_lines = max((s["insertions"] + s["deletions"]) for s in snaps)
    final_dirty = snaps[-1]["dirty"]

    if commits >= 1:
        return min(1.0, 0.5 + 0.2 * commits)
    if final_dirty:
        return min(0.5, max_lines / 200.0)
    return 0.4


def churn_penalty(events: list[dict]) -> float:
    edits = Counter()
    for e in _edit_events(events):
        if p := _edit_path(e):
            edits[p] += 1
    total = sum(edits.values())
    if total == 0:
        return 1.0
    repeated = sum(c - 1 for c in edits.values() if c > 1)
    return 1.0 - min(1.0, repeated / total)


def convergence(events: list[dict]) -> dict:
    g = git_trajectory(events)
    t = test_pass_rate(events)
    c = churn_penalty(events)
    score = 0.40 * g + 0.35 * t + 0.25 * c
    return {
        "score": round(score, 3),
        "git": round(g, 3),
        "tests": round(t, 3),
        "churn_ok": round(c, 3),
    }


def thrash(events: list[dict]) -> dict:
    edits_since_commit = Counter()
    for e in events:
        cmd = (e.get("tool_input") or {}).get("command", "") if e.get("tool_name") == "Bash" else ""
        if "git commit" in cmd and e.get("event") == "PostToolUse":
            edits_since_commit.clear()
            continue
        if e.get("tool_name") in EDIT_TOOLS and e.get("event") == "PostToolUse":
            if p := _edit_path(e):
                edits_since_commit[p] += 1

    edit_confidence = 0.0
    hot_file = None
    if edits_since_commit:
        hot_file, hot_count = edits_since_commit.most_common(1)[0]
        if hot_count > 3:
            edit_confidence = min(1.0, 0.5 + (hot_count - 3) / 6.0)

    cmd_fails = Counter()
    for e in _bash_events(events):
        cmd = (e.get("tool_input") or {}).get("command", "")
        code = _bash_exit_code(e)
        if code is not None and code != 0:
            cmd_fails[cmd] += 1

    fail_confidence = 0.0
    hot_cmd = None
    if cmd_fails:
        hot_cmd, hot_fails = cmd_fails.most_common(1)[0]
        if hot_fails >= 2:
            fail_confidence = min(1.0, 0.5 + (hot_fails - 2) / 4.0)

    confidence = max(edit_confidence, fail_confidence)
    return {
        "confidence": round(confidence, 3),
        "triggered": confidence >= 0.5,
        "hot_file": hot_file if edit_confidence >= fail_confidence else None,
        "hot_failing_command": hot_cmd if fail_confidence > edit_confidence else None,
    }


def momentum(events: list[dict]) -> dict:
    if len(events) < 20:
        return {"state": "warming_up", "delta": 0.0, "last_window": 0.0, "prev_window": 0.0}
    last = convergence(events[-10:])["score"]
    prev = convergence(events[-20:-10])["score"]
    delta = last - prev
    if delta > 0.1:
        state = "accelerating"
    elif delta < -0.1:
        state = "decelerating"
    elif last < 0.3:
        state = "stuck"
    else:
        state = "steady"
    return {
        "state": state,
        "delta": round(delta, 3),
        "last_window": round(last, 3),
        "prev_window": round(prev, 3),
    }
