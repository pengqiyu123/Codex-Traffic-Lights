# Codex Traffic Lights Data Acquisition Test Process

This folder is an isolated live-observation workspace for proving whether Codex
Traffic Lights can read real VSCode Codex / Claude Code state.

It follows one rule: real upstream data first. Fixtures and simulations may test
parsers, but they never count as a successful product-state result.

## What This Tests

- Hook commands in `~/.codex/hooks.json` and `~/.claude/settings.json`
- Real session files in `~/.codex-traffic-lights/sessions`
- Multiple simultaneous sessions from separate VSCode Codex or Claude Code conversations
- Status transitions written by real hooks, not synthetic UI state

## Two-Conversation Procedure

1. Start Codex Traffic Lights from this repo.
2. Open two VSCode windows or two Codex plugin conversations.
3. In each conversation, send a different prompt that triggers tool activity.
4. Run:

```powershell
python test_process\watch_codex_sessions.py --duration 120
```

5. The run is successful only if the watcher reports at least two distinct
   session keys or two distinct display names updated by real hook files.

## Success Criteria

- `source_count >= 2`
- At least two `session_key` values are present.
- `updated_at` changes while the conversations are active.
- Statuses move through real values such as `WORKING`, `WAITING_APPROVAL`,
  `WAITING_USER_INPUT`, `IDLE`, or `ERROR`.

## Failure Criteria

- Only process detection is available.
- `~/.codex-traffic-lights/sessions` stays empty.
- One global session overwrites both conversations.
- Status changes appear only in mock files or tests.

## Notes

This folder is intentionally outside the application package. Findings here
should be promoted into `src/` only after real data confirms the behavior.
