import json
from datetime import datetime, timezone
from pathlib import Path

STORE_DIR = Path.home() / ".driftwatch" / "events"


def ensure_store() -> None:
    STORE_DIR.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def session_path(session_id: str) -> Path:
    return STORE_DIR / f"{session_id}.jsonl"


def append(event: dict) -> None:
    ensure_store()
    sid = event.get("session_id") or "unknown"
    with session_path(sid).open("a") as f:
        f.write(json.dumps(event) + "\n")


def read(session_id: str) -> list[dict]:
    path = session_path(session_id)
    if not path.exists():
        return []
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def list_sessions() -> list[tuple[str, float]]:
    ensure_store()
    pairs = [(p.stem, p.stat().st_mtime) for p in STORE_DIR.glob("*.jsonl")]
    return sorted(pairs, key=lambda x: -x[1])
