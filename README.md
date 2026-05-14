# driftwatch

Trace Claude Code tool calls and measure whether your agent session is **converging on a fix** or **thrashing in circles**.

driftwatch installs as a Claude Code hook. Every tool call (Bash, Edit, Write, etc.) is captured to a local JSONL log, then scored across three axes:

- **Convergence** — git movement, test pass rate, and edit churn rolled into a single 0–1 score
- **Thrash** — detects when the agent keeps editing the same file or re-running the same failing command
- **Momentum** — compares the last 10 events to the previous 10 to tell you whether things are getting better or worse

No telemetry leaves your machine. Events are written to `~/.driftwatch/events/<session>.jsonl`.

---

## Install

Requires Python 3.10+.

```bash
pip install driftwatch
driftwatch init
```

`driftwatch init` registers `PreToolUse`, `PostToolUse`, and `Stop` hooks in `~/.claude/settings.json`. Existing hooks are preserved; driftwatch's entries are tagged and can be removed cleanly later.

Start a Claude Code session as usual — events are recorded automatically.

### From a wheel

```bash
pip install ./dist/driftwatch-0.1.0-py3-none-any.whl
```

If pip refuses with `requires a different Python`, your interpreter is older than 3.10. Install a newer Python (`brew install python@3.12`) and recreate the venv.

---

## Usage

```bash
driftwatch sessions          # list captured sessions, most recent first
driftwatch report            # text report for the most recent session
driftwatch report <id>       # text report for a specific session
driftwatch report --json     # same data as JSON
driftwatch watch             # live TUI, repaints as new events arrive
driftwatch watch --interval 1.0
```

### Example report

```
session: 9a1f...
events:  142

convergence: 0.612
  git:      0.700
  tests:    0.667
  churn_ok: 0.480

thrash: 0.667 [TRIGGERED]
  hot file:           src/api/handlers.py

momentum: accelerating  (Δ=+0.143, last=0.701, prev=0.558)
```

### Live watch

```
driftwatch — 9a1f...    events=142    16:04:22

convergence  ██████████████░░░░░░░░  0.612
  git        ████████████████░░░░░░  0.700
  tests      ███████████████░░░░░░░  0.667
  churn_ok   ██████████░░░░░░░░░░░░  0.480

thrash       ███████████████░░░░░░░  0.667  [TRIGGERED]
  hot file:  src/api/handlers.py

momentum:    accelerating  Δ=+0.143  last=0.701  prev=0.558
```

---

## What the metrics mean

### Convergence (0.0 – 1.0)

Weighted sum of three signals. Higher = the session is moving toward a finished change.

| Signal     | Weight | What it measures                                                   |
| ---------- | ------ | ------------------------------------------------------------------ |
| `git`      | 0.40   | Commits made, dirty-tree size, and whether HEAD advanced            |
| `tests`    | 0.35   | Pass rate of detected test commands (pytest, jest, go test, …)      |
| `churn_ok` | 0.25   | Inverse of repeated edits to the same file                          |

`tests` defaults to 0.5 when no test command has been seen yet, so the score isn't penalized for sessions that don't run tests.

### Thrash (0.0 – 1.0, with `triggered` flag)

Fires when either:

- one file has been edited **>3 times since the last `git commit`**, or
- one bash command has **failed ≥2 times** with a non-zero exit

`triggered` flips true at confidence ≥ 0.5. The `hot_file` / `hot_failing_command` fields tell you which one.

### Momentum

Compares the convergence score of the **last 10 events** vs. the **previous 10**.

| State           | Condition                  |
| --------------- | -------------------------- |
| `accelerating`  | Δ > +0.10                  |
| `decelerating`  | Δ < −0.10                  |
| `stuck`         | last window < 0.30          |
| `steady`        | otherwise                  |
| `warming_up`    | fewer than 20 events total |

---

## How it works

```
Claude Code
   │  PreToolUse / PostToolUse / Stop
   ▼
python -m driftwatch.hook   ← stdin: JSON tool payload
   │
   ├─ capture event (tool_name, tool_input, tool_response, cwd, ts)
   ├─ on edit/write/bash PostToolUse: snapshot `git status --porcelain` and `git diff --shortstat`
   ▼
~/.driftwatch/events/<session_id>.jsonl   (append-only)
```

Reading is just `jsonl` → list of dicts; metrics are pure functions over that list. There is no daemon, no network, no database.

### Files

| Path                       | Purpose                                              |
| -------------------------- | ---------------------------------------------------- |
| `driftwatch/hook.py`       | Entrypoint invoked by Claude Code on each tool call  |
| `driftwatch/store.py`      | JSONL append/read in `~/.driftwatch/events/`         |
| `driftwatch/git.py`        | Lightweight `git` snapshots (head, dirty, shortstat) |
| `driftwatch/metrics.py`    | `convergence`, `thrash`, `momentum`                  |
| `driftwatch/cli.py`        | `driftwatch` command-line interface                  |

---

## Uninstall

```bash
driftwatch uninstall            # remove hooks, keep ~/.driftwatch/events
driftwatch uninstall --purge    # also delete the event store
pip uninstall driftwatch        # remove the package itself
```

---

## Development

```bash
git clone <this repo>
cd AgentTrashCollector
python3.12 -m venv venv
source venv/bin/activate
pip install -e .
driftwatch init
```

Build a wheel:

```bash
pip install build
python -m build
```

---

## License

MIT — see [LICENSE](LICENSE).
