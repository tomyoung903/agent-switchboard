# Codex Session Monitor

Publishes Codex CLI session status changes to an ntfy topic so the Electron dashboard can show live agent state.

Codex writes JSONL session logs under:

```text
~/.codex/sessions/**/rollout-*.jsonl
```

The monitor tails the latest session per working directory and publishes messages in this format:

```text
window_name | thread_name - status
```

## Configure ntfy

Copy the example config:

```bash
mkdir -p ~/.config
cp ../config/noti_ntfy.env.example ~/.config/noti_ntfy.env
```

Edit `~/.config/noti_ntfy.env` with your own topic and credentials.

## Run

```bash
./codex_session_monitor.sh restart
./codex_session_monitor.sh status
./codex_session_monitor.sh logs
```

Useful overrides:

```bash
CODEX_SESSIONS_INTERVAL=1 ./codex_session_monitor.sh restart
CODEX_SESSIONS_MODE=ongoing_done ./codex_session_monitor.sh restart
```
