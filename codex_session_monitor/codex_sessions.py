#!/usr/bin/env python3
"""Codex session status + ntfy monitor.

Codex writes JSONL logs under ~/.codex/sessions/**/rollout-*.jsonl.

This script publishes a status string per project directory to ntfy.

Modes:

- event_type (default): publish the last event type (payload.type preferred, else top-level type).
- ongoing_done (legacy): publish "ongoing"/"done" using a turn-based state machine.

See codex_sessions.md for the human-readable pseudocode.
"""

import argparse
import base64
import json
import os
import re
import socket
import subprocess
import time
from pathlib import Path

# Turn start/end markers observed in ~/.codex/sessions/*/rollout-*.jsonl.
#
# Start a turn:
# - event_msg/user_message is the clearest signal (user submitted a prompt).
# - response_item/message role=user is a fallback for older logs.
#
# End a turn:
# - response_item/message role=assistant with phase != "commentary" (includes final answers)
# - event_msg/turn_aborted (user interrupted)
#
# While a turn is open, we remain ongoing until the last terminal message comes AFTER
# the last tool event (call or output) for that turn.
TOOL_EVENT_TYPES = {
    "function_call",
    "function_call_output",
    "custom_tool_call",
    "custom_tool_call_output",
    "web_search_call",
}

DEFAULT_NTFY_SERVER = "https://ntfy.sh"
DEFAULT_NTFY_TOPIC = "agent_switchboard_demo_topic_change_me"
DEFAULT_NTFY_ENV_CANDIDATES = (
    Path("~/armory/.shared/noti_ntfy.env").expanduser(),
    Path("~/.config/noti_ntfy.env").expanduser(),
)
SESSIONS_ROOT = Path("~/.codex/sessions").expanduser()
SESSION_INDEX_PATH = Path("~/.codex/session_index.jsonl").expanduser()

# Extremely frequent and usually unhelpful for status display.
NOISE_PAYLOAD_TYPES = {"token_count"}
SESSION_ID_LIKE_RE = re.compile(r"^[0-9a-f]{8,}(?:-[0-9a-f]{4,})+$", re.IGNORECASE)


def _load_simple_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        out[key] = value.strip()
    return out


def _default_ntfy_env_file() -> Path:
    override = os.environ.get("NOTI_NTFY_ENV_FILE")
    if override:
        return Path(override).expanduser()

    for candidate in DEFAULT_NTFY_ENV_CANDIDATES:
        if candidate.exists():
            return candidate

    return DEFAULT_NTFY_ENV_CANDIDATES[0]


def _load_ntfy_settings() -> dict[str, str]:
    file_settings = _load_simple_env_file(_default_ntfy_env_file())

    def pick(name: str, default: str = "") -> str:
        return os.environ.get(name, file_settings.get(name, default))

    return {
        "NTFY_SERVER": pick("NTFY_SERVER", DEFAULT_NTFY_SERVER),
        "NTFY_TOPIC": pick("NTFY_TOPIC", DEFAULT_NTFY_TOPIC),
        "NTFY_AUTH_HEADER": pick("NTFY_AUTH_HEADER", ""),
        "NTFY_TOKEN": pick("NTFY_TOKEN", pick("NOTI_NTFY_TOKEN", "")),
        "NTFY_USERNAME": pick("NTFY_USERNAME", ""),
        "NTFY_PASSWORD": pick("NTFY_PASSWORD", ""),
        "NOTI_HOST_ID": pick("NOTI_HOST_ID", pick("NOTI_MACHINE_ID", "")),
    }


def _build_auth_header(settings: dict[str, str]) -> str:
    if settings["NTFY_AUTH_HEADER"]:
        return settings["NTFY_AUTH_HEADER"]
    if settings["NTFY_TOKEN"]:
        return f"Authorization: Bearer {settings['NTFY_TOKEN']}"
    user = settings["NTFY_USERNAME"]
    password = settings["NTFY_PASSWORD"]
    if user or password:
        basic = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        return f"Authorization: Basic {basic}"
    return ""


_NTFY_SETTINGS = _load_ntfy_settings()
NTFY_SERVER = _NTFY_SETTINGS["NTFY_SERVER"].rstrip("/")
NTFY_TOPIC = _NTFY_SETTINGS["NTFY_TOPIC"]
NTFY_URL = f"{NTFY_SERVER}/{NTFY_TOPIC}"
NTFY_AUTH_HEADER = _build_auth_header(_NTFY_SETTINGS)
NOTI_HOST_ID = (
    _NTFY_SETTINGS["NOTI_HOST_ID"]
    or os.environ.get("HOSTNAME", "")
    or socket.gethostname()
    or "unknown"
).strip()


def read_tail(path: Path, max_bytes: int = 262144) -> list[str]:
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        read_size = min(size, max_bytes)
        f.seek(size - read_size)
        data = f.read().splitlines()
    if size > max_bytes and data:
        data = data[1:]
    return [line.decode("utf-8", "replace") for line in data[-500:]]


def _parse_ts(ts: str) -> float | None:
    if not ts:
        return None
    try:
        # Example: 2026-02-10T09:42:02.723Z
        from datetime import datetime

        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return None


def last_event_type(path: Path) -> str | None:
    """Return the last event type.

    Prefers payload.type when present, otherwise falls back to the top-level type.
    """

    tail = read_tail(path)
    for line in reversed(tail):
        try:
            obj = json.loads(line)
        except Exception:
            continue

        typ = obj.get("type")
        payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
        ptyp = payload.get("type")

        if ptyp in NOISE_PAYLOAD_TYPES:
            continue

        if ptyp:
            return ptyp
        if typ:
            return typ

    return None


def is_active(path: Path) -> bool:
    """Return True if this session is currently working on the latest user prompt."""

    tail = read_tail(path)

    # 1) Find the start of the latest turn: last user prompt submission.
    last_user_ts = None
    for line in tail:
        try:
            obj = json.loads(line)
        except Exception:
            continue
        typ = obj.get("type")
        payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
        ptyp = payload.get("type")

        is_user_submit = typ == "event_msg" and ptyp == "user_message"
        is_user_msg_fallback = (
            typ == "response_item" and ptyp == "message" and payload.get("role") == "user"
        )
        if not (is_user_submit or is_user_msg_fallback):
            continue

        t = _parse_ts(obj.get("timestamp", ""))
        if t is None:
            continue
        if last_user_ts is None or t > last_user_ts:
            last_user_ts = t

    if last_user_ts is None:
        # No prompts observed; treat as idle/done.
        return False

    # 2) For events after the latest user prompt, see if the turn has ended.
    last_tool_ts = None
    last_terminal_ts = None
    for line in tail:
        try:
            obj = json.loads(line)
        except Exception:
            continue
        t = _parse_ts(obj.get("timestamp", ""))
        if t is None or t < last_user_ts:
            continue

        typ = obj.get("type")
        payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
        ptyp = payload.get("type")

        # Track tool activity within the turn.
        if typ == "response_item" and ptyp in TOOL_EVENT_TYPES:
            last_tool_ts = t if last_tool_ts is None else max(last_tool_ts, t)

        # Treat turn_aborted as an immediate terminal for the turn.
        if typ == "event_msg" and ptyp == "turn_aborted":
            last_terminal_ts = t if last_terminal_ts is None else max(last_terminal_ts, t)

        # A terminal assistant message is any assistant message that is NOT a progress update.
        # Newer logs tag progress updates with phase="commentary".
        if typ == "response_item" and ptyp == "message" and payload.get("role") == "assistant":
            phase = payload.get("phase")
            if phase != "commentary":
                last_terminal_ts = t if last_terminal_ts is None else max(last_terminal_ts, t)

    if last_terminal_ts is None:
        # User submitted a prompt and we haven't seen any terminal output yet.
        return True

    if last_tool_ts is not None and last_terminal_ts <= last_tool_ts:
        # We have output, but it happened before the last tool event finished.
        # This means we're still working on the prompt.
        return True

    # Terminal output exists and is after the last tool event (or there were no tools).
    return False


def get_cwd(path: Path) -> str | None:
    with path.open("r") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("type") == "session_meta":
                return obj.get("payload", {}).get("cwd")
            break
    return None


def get_session_meta(path: Path) -> tuple[str | None, str | None]:
    with path.open("r") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("type") != "session_meta":
                break
            payload = obj.get("payload", {})
            if not isinstance(payload, dict):
                return None, None
            return payload.get("cwd"), payload.get("id")
    return None, None


def latest_session_files() -> dict[str, tuple[str, Path]]:
    """Return {session_id: (cwd, rollout_path)} for the most recent rollout file per session."""

    latest_paths: dict[str, tuple[str, Path]] = {}
    latest_mtimes: dict[str, float] = {}
    if not SESSIONS_ROOT.exists():
        return latest_paths

    for path in SESSIONS_ROOT.rglob("rollout-*.jsonl"):
        cwd, session_id = get_session_meta(path)
        if not cwd or not session_id:
            continue
        mtime = path.stat().st_mtime
        if session_id in latest_mtimes and mtime <= latest_mtimes[session_id]:
            continue
        latest_mtimes[session_id] = mtime
        latest_paths[session_id] = (cwd, path)

    return latest_paths


def load_latest_thread_names() -> dict[str, str]:
    names: dict[str, str] = {}
    if not SESSION_INDEX_PATH.exists():
        return names

    try:
        with SESSION_INDEX_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                session_id = obj.get("id")
                thread_name = obj.get("thread_name")
                if isinstance(session_id, str) and isinstance(thread_name, str):
                    names[session_id] = thread_name
    except Exception:
        return names

    return names


def is_user_named_thread(thread_name: str | None, session_id: str | None) -> bool:
    if not thread_name or not isinstance(thread_name, str):
        return False

    normalized = thread_name.strip()
    if not normalized:
        return False
    if session_id and normalized == session_id:
        return False
    if SESSION_ID_LIKE_RE.match(normalized):
        return False
    return True


def format_default_thread_name(session_id: str | None) -> str:
    if not session_id:
        return "session-unknown"
    return f"session-{session_id[:8]}"


def format_session_label(
    cwd: str,
    session_id: str | None,
    thread_names: dict[str, str],
    include_renamed_thread_name: bool,
) -> str:
    dirname = Path(cwd).name
    if not include_renamed_thread_name or not session_id:
        return dirname

    thread_name = thread_names.get(session_id)
    if not is_user_named_thread(thread_name, session_id):
        thread_name = format_default_thread_name(session_id)

    return f"{dirname} | {thread_name}"


def scan_event_type_statuses(include_renamed_thread_name: bool = False) -> dict[str, str]:
    """Return {label: last_event_type} for all sessions."""

    out: dict[str, str] = {}
    session_files = latest_session_files()
    thread_names = load_latest_thread_names() if include_renamed_thread_name else {}
    for session_id, (cwd, path) in session_files.items():
        label = format_session_label(
            cwd,
            session_id,
            thread_names,
            include_renamed_thread_name,
        )
        out[label] = last_event_type(path) or "None"
    return out


def scan_ongoing_done(include_renamed_thread_name: bool = False) -> dict[str, bool]:
    """Return {label: is_active} for all sessions."""

    out: dict[str, bool] = {}
    session_files = latest_session_files()
    thread_names = load_latest_thread_names() if include_renamed_thread_name else {}
    for session_id, (cwd, path) in session_files.items():
        label = format_session_label(
            cwd,
            session_id,
            thread_names,
            include_renamed_thread_name,
        )
        out[label] = is_active(path)
    return out


def notify(window_name: str, status: str, thread_name: str = "") -> None:
    payload = {
        "host": NOTI_HOST_ID or "unknown",
        "window_name": window_name,
        "thread_name": thread_name,
        "status": status,
    }
    cmd = ["curl", "-sS"]
    if NTFY_AUTH_HEADER:
        cmd.extend(["-H", NTFY_AUTH_HEADER])
    cmd.extend(["-H", "Content-Type: application/json"])
    cmd.extend(["-d", json.dumps(payload, separators=(",", ":")), NTFY_URL])
    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def monitor(interval: float, mode: str, include_renamed_thread_name: bool) -> None:
    prev: dict[str, str] = {}
    first_run = True

    print(f"Monitoring codex sessions every {interval}s. mode={mode}. Ctrl+C to stop.")
    try:
        while True:
            session_files = latest_session_files()
            thread_names = load_latest_thread_names() if include_renamed_thread_name else {}
            if mode == "ongoing_done":
                current = {
                    session_id: ("ongoing" if active else "done")
                    for session_id, active in (
                        (session_id, is_active(path))
                        for session_id, (_, path) in session_files.items()
                    )
                }
            else:
                current = {
                    session_id: (last_event_type(path) or "None")
                    for session_id, (_, path) in session_files.items()
                }

            # On startup, seed state only. A service restart should not flood ntfy
            # with every existing session status; only subsequent changes matter.
            if first_run:
                print(f"[STARTUP] Seeded {len(current)} sessions without notify.")
                prev = current
                first_run = False
            else:
                # Detect changes.
                for session_id, status in current.items():
                    prev_status = prev.get(session_id)
                    if prev_status != status:
                        cwd, _ = session_files.get(session_id, (None, None))
                        if not cwd:
                            continue
                        label = format_session_label(
                            cwd,
                            session_id,
                            thread_names,
                            include_renamed_thread_name,
                        )
                        window_name = Path(cwd).name
                        thread_name = ""
                        if " | " in label:
                            window_name, thread_name = label.split(" | ", 1)
                        ts = time.strftime("%H:%M:%S")
                        print(f"[{ts}] {label} - {status}")
                        notify(window_name, status, thread_name)
                prev = current
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Codex session status")
    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Continuously monitor and notify on status changes",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Poll interval in seconds (default: 2)",
    )
    parser.add_argument(
        "--mode",
        choices=["event_type", "ongoing_done"],
        default="event_type",
        help="Status mode: event_type (default) or ongoing_done (legacy)",
    )
    parser.add_argument(
        "--include-renamed-thread-name",
        action="store_true",
        help="Emit 'dirname | thread_name' when a user-renamed thread_name exists",
    )
    args = parser.parse_args()

    if args.monitor:
        monitor(args.interval, args.mode, args.include_renamed_thread_name)
        return

    if args.mode == "ongoing_done":
        for label, active in sorted(
            scan_ongoing_done(args.include_renamed_thread_name).items()
        ):
            if active:
                print(label)
        return

    session_files = latest_session_files()
    thread_names = load_latest_thread_names() if args.include_renamed_thread_name else {}
    for session_id, (cwd, path) in sorted(
        session_files.items(),
        key=lambda item: (item[1][0], item[0]),
    ):
        status = last_event_type(path) or "None"
        label = format_session_label(
            cwd,
            session_id,
            thread_names,
            args.include_renamed_thread_name,
        )
        print(f"{label} - {status}")


if __name__ == "__main__":
    main()
