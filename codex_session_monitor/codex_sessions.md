# codex_sessions.py: Status Rules (Readable Pseudocode)

Codex session logs live at:

- `~/.codex/sessions/**/rollout-*.jsonl`

Each line is JSON with:

- `type` (top-level)
- `timestamp` (ISO 8601 string)
- `payload` (object; commonly includes `payload.type`, sometimes `payload.role`, sometimes `payload.phase`)

Note on variable names in this doc:

- `ts` means timestamp.

This script supports 2 status modes:

- `event_type` (default): publish the last event type.
- `ongoing_done` (legacy): publish `ongoing`/`done` using a turn-based state machine.

## Mode: event_type (Default)

Goal: show a compact signal you can learn patterns from, without trying to infer `ongoing/done`.

Output format (per project):

- `"{project_name} - {last_event_type}"`

Noise handling:

- Skip events where `payload.type == "token_count"` (they are extremely frequent and usually drown out the interesting events).

How `last_event_type` is chosen:

- Prefer `payload.type` when it exists.
- Otherwise fall back to the top-level `type`.

### Pseudocode

```text
function latest_session_files():
  # Keep only the newest rollout file per cwd.
  latest = {}
  for each rollout_path in ~/.codex/sessions/**/rollout-*.jsonl:
    cwd = read session_meta.cwd from the first JSON line
    if cwd is missing: continue

    if rollout_path.mtime is newer than latest[cwd].mtime:
      latest[cwd] = rollout_path

  return latest  # {cwd -> rollout_path}


function last_event_type(rollout_path):
  tail_lines = read last ~256KB of file
  tail_lines = tail_lines.last(500)

  for line in tail_lines in reverse order:
    obj = parse_json(line)
    if parse fails: continue

    ptyp = obj.payload.type
    typ  = obj.type

    if ptyp == "token_count":
      continue

    if ptyp exists:
      return ptyp

    if typ exists:
      return typ

  return "None"


function monitor_loop():
  prev = {}  # {cwd -> status_string}

  loop every N seconds:
    latest = latest_session_files()

    current = {}
    for (cwd, rollout_path) in latest:
      current[cwd] = last_event_type(rollout_path)

    if first loop:
      publish all current statuses to ntfy
    else:
      for each cwd in current:
        if current[cwd] != prev[cwd]:
          publish the new status to ntfy

    prev = current
```

## Mode: ongoing_done (Legacy)

Goal: **flip to `ongoing` when a user submits a prompt, and flip back to `done` when Codex has finished that prompt (including tools).**

### Signals In The Logs

Turn Start (user submitted a prompt):

- Preferred: `type == "event_msg" && payload.type == "user_message"`
- Fallback (older logs): `type == "response_item" && payload.type == "message" && payload.role == "user"`

Tool events (work in progress within a turn):

- `type == "response_item" && payload.type in { function_call, function_call_output, custom_tool_call, custom_tool_call_output, web_search_call }`

Turn End (finished or aborted):

- Abort: `type == "event_msg" && payload.type == "turn_aborted"`
- Finished answer: `type == "response_item" && payload.type == "message" && payload.role == "assistant" && payload.phase != "commentary"`

### Pseudocode

```text
function is_active(session_log):
  last_user_ts = max timestamp of:
    - event_msg/user_message
    - OR (fallback) response_item/message role=user

  if last_user_ts is None:
    return false  # done

  last_tool_ts = max timestamp after last_user_ts of tool events
  last_terminal_ts = max timestamp after last_user_ts of:
    - event_msg/turn_aborted
    - response_item/message role=assistant where phase != "commentary"

  if last_terminal_ts is None:
    return true   # ongoing (user asked, no terminal output yet)

  if last_tool_ts exists AND last_terminal_ts <= last_tool_ts:
    return true   # ongoing (terminal output happened before last tool event finished)

  return false    # done (terminal output after tools, or no tools at all)
```
