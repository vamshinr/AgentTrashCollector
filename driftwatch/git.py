import re
import subprocess


def _run(args: list[str], cwd: str) -> str | None:
    try:
        out = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=2)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


def snapshot(cwd: str) -> dict | None:
    head = _run(["git", "rev-parse", "HEAD"], cwd)
    if head is None:
        return None
    status = _run(["git", "status", "--porcelain"], cwd) or ""
    shortstat = _run(["git", "diff", "--shortstat"], cwd) or ""

    files = insertions = deletions = 0
    if m := re.search(r"(\d+) files? changed", shortstat):
        files = int(m.group(1))
    if m := re.search(r"(\d+) insertions?", shortstat):
        insertions = int(m.group(1))
    if m := re.search(r"(\d+) deletions?", shortstat):
        deletions = int(m.group(1))

    return {
        "head": head,
        "dirty": bool(status),
        "files_changed": files,
        "insertions": insertions,
        "deletions": deletions,
    }
