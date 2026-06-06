#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
MONITOR_SCRIPT="${CODEX_SESSIONS_SCRIPT:-$SCRIPT_DIR/codex_sessions.py}"
INTERVAL="${CODEX_SESSIONS_INTERVAL:-2}"
MODE="${CODEX_SESSIONS_MODE:-event_type}"
LOG_FILE="${CODEX_SESSION_MONITOR_LOG:-/tmp/codex-sessions-monitor-wsl.log}"
PID_FILE="${CODEX_SESSION_MONITOR_PID:-/tmp/codex-sessions-monitor-wsl.pid}"

monitor_pattern() {
  printf '%s --monitor' "$MONITOR_SCRIPT"
}

is_running() {
  local pid="${1:-}"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

current_pid() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if is_running "$pid"; then
      echo "$pid"
      return 0
    fi
  fi

  pgrep -f "$(monitor_pattern)" | head -n 1 || true
}

start_monitor() {
  if [[ ! -f "$MONITOR_SCRIPT" ]]; then
    echo "Missing monitor script: $MONITOR_SCRIPT" >&2
    return 1
  fi

  local pid
  pid="$(current_pid)"
  if is_running "$pid"; then
    echo "Codex session monitor already running: PID $pid"
    return 0
  fi

  nohup setsid python3 -u "$MONITOR_SCRIPT" \
    --monitor \
    --interval "$INTERVAL" \
    --mode "$MODE" \
    --include-renamed-thread-name \
    >"$LOG_FILE" 2>&1 < /dev/null &

  echo $! > "$PID_FILE"
  sleep 2

  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if ! is_running "$pid"; then
    echo "Failed to start Codex session monitor. Recent log:" >&2
    tail -n 40 "$LOG_FILE" >&2 || true
    return 1
  fi

  echo "Started Codex session monitor: PID $pid"
  echo "Log: $LOG_FILE"
}

stop_monitor() {
  local pid
  pid="$(current_pid)"
  if ! is_running "$pid"; then
    rm -f "$PID_FILE"
    echo "Codex session monitor is not running"
    return 0
  fi

  kill "$pid" 2>/dev/null || true
  sleep 1
  if is_running "$pid"; then
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
  echo "Stopped Codex session monitor: PID $pid"
}

status_monitor() {
  local pid
  pid="$(current_pid)"
  if is_running "$pid"; then
    echo "Codex session monitor is running: PID $pid"
    ps -fp "$pid" || true
    return 0
  fi

  echo "Codex session monitor is not running"
  return 1
}

case "${1:-status}" in
  start)
    start_monitor
    ;;
  restart)
    stop_monitor
    start_monitor
    ;;
  stop)
    stop_monitor
    ;;
  status)
    status_monitor
    ;;
  logs)
    tail -n "${2:-80}" "$LOG_FILE" 2>/dev/null || true
    ;;
  logsf)
    tail -f "$LOG_FILE"
    ;;
  *)
    echo "Usage: $0 start|restart|stop|status|logs [lines]|logsf" >&2
    exit 2
    ;;
esac
