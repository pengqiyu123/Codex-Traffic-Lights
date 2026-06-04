# Data Acquisition Rules

These rules are the memory for all Codex Traffic Lights state-detection work.

## Rule 1: Real Data Before Product Logic

Do not implement a new status mapping from guesses. First capture the upstream
payload, file, log line, process command, or app-server notification that proves
the state exists.

## Rule 2: Label Every Source

Every observed status must declare its source:

- `hook-file`
- `app-server`
- `vscode-log`
- `process`
- `manual-fixture`

Only `hook-file` and `app-server` can drive the product UI without a warning.

## Rule 3: Fixtures Test Parsers Only

Fixture JSON is allowed for unit tests, but it cannot prove real VSCode Codex
state. A report must say `fixture` when data is not live.

## Rule 4: Multi-Session Requires Distinct Keys

Multiple columns in Expanded mode require distinct `session_key` values. If two
VSCode conversations collapse into one `global` or one workspace key, the data
source is insufficient and must be fixed before UI work continues.

## Rule 5: Process Detection Is Only Fallback

`psutil` can answer only "a Codex-like process exists" or "it disappeared". It
cannot distinguish working, idle, approval, user input, queued, review, or
per-thread state.

## Rule 6: Never Treat Silence As Idle

No hook update does not mean Codex is idle. It means the data source is silent,
broken, or unavailable.

## Rule 7: Promote Only After a Live Transcript

Before changing `state_mapper.py`, `process_monitor.py`, or UI aggregation,
capture a live transcript from `watch_codex_sessions.py` showing the exact
session files and transitions.
