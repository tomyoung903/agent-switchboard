#!/usr/bin/env python3
"""
ntfy Listener - Standalone service that listens for notifications and tracks window status
Runs continuously in the background and maintains current status for each window
"""

# Force unbuffered output for subprocess logging
import sys
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None
sys.stderr.reconfigure(line_buffering=True) if hasattr(sys.stderr, 'reconfigure') else None

import requests
import json
import os
import signal
import subprocess
from datetime import datetime
from pathlib import Path
import platform

# Add src directory to path for imports when run as standalone script
sys.path.insert(0, str(Path(__file__).parent))

# Configuration
NTFY_SERVER = "https://ntfy.sh"
TOPIC_NAME = "tom_noti_app_abc123xyz"
TOPIC_URL = f"{NTFY_SERVER}/{TOPIC_NAME}"

# Import database module
from db import update_window_status, DB_DIR as STATUS_DIR


def parse_focus_message(message_text):
    """
    Parse incoming messages into window_name and status

    Expected formats:
    - "claude:windows - task completed" → window_name: "claude:windows", status: "task completed"
    - "app - status message" → window_name: "app", status: "status message"
    - "app" → window_name: "app", status: None
    """
    if not message_text:
        return None

    message_text = message_text.strip()

    # Parse different message formats
    if " - " in message_text:
        # Format: "window_name - status"
        parts = message_text.split(" - ", 1)
        window_name = parts[0]
        status = parts[1] if len(parts) > 1 else None
    else:
        # Default: treat entire message as window_name
        window_name = message_text
        status = None

    return {
        "window_name": window_name,
        "status": status
    }


## update_window_status is now imported from db module


def listen_for_notifications():
    """Listen for ntfy notifications and update window status with auto-reconnection"""
    print(f"[LISTENER] Starting ntfy listener on: {TOPIC_URL}")
    print(f"[LISTENER] Using SQLite database in: {STATUS_DIR}")

    # Debug log
    debug_log = STATUS_DIR / "listener_debug.txt"
    def log(msg):
        try:
            with open(debug_log, "a") as f:
                f.write(f"{datetime.now().isoformat()} {msg}\n")
            print(f"[LISTENER] {msg}")
        except Exception as e:
            print(f"[LISTENER] Log error: {e}")

    log(f"Listener started. DB_DIR={STATUS_DIR}")

    reconnect_delay = 5  # Start with 5 second delay
    max_reconnect_delay = 60  # Max 60 seconds between retries

    while True:  # Reconnection loop
        try:
            log(f"Connecting to {TOPIC_URL}/sse...")
            response = requests.get(
                f"{TOPIC_URL}/sse",
                stream=True,
                timeout=300  # 5 minute timeout for detecting dead connections
            )

            log(f"Connected successfully (status={response.status_code})")
            reconnect_delay = 5  # Reset delay on successful connection

            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')

                    # Parse ntfy SSE format: data: {"message": "..."}
                    if line.startswith('data:'):
                        try:
                            data = json.loads(line[5:].strip())

                            # Extract message content
                            message_text = data.get('message', '')

                            # Parse message into window_name and status
                            parsed = parse_focus_message(message_text)

                            if parsed:
                                update_window_status(
                                    parsed["window_name"],
                                    parsed.get("status")
                                )

                        except json.JSONDecodeError:
                            print(f"[WARN] Could not parse message: {line}")

        except KeyboardInterrupt:
            print("\n[LISTENER] Stopped listening")
            break  # Exit cleanly on Ctrl+C

        except Exception as e:
            print(f"[ERROR] Connection lost: {e}")
            print(f"[LISTENER] Reconnecting in {reconnect_delay} seconds...")

            import time
            time.sleep(reconnect_delay)

            # Exponential backoff
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
            continue  # Retry connection


def kill_existing_listeners():
    """Kill any existing ntfy_listener processes except this one"""
    current_pid = os.getpid()
    current_process_name = Path(__file__).name

    print(f"[LISTENER] Checking for existing listeners (current PID: {current_pid})")

    try:
        # Use pkill to kill other instances
        result = subprocess.run(
            ["pgrep", "-f", current_process_name],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            killed_count = 0

            for pid_str in pids:
                pid = int(pid_str.strip())
                if pid != current_pid:
                    try:
                        os.kill(pid, signal.SIGTERM)
                        print(f"[LISTENER] Killed existing listener PID: {pid}")
                        killed_count += 1
                    except ProcessLookupError:
                        pass

            if killed_count > 0:
                print(f"[LISTENER] Killed {killed_count} existing listener(s)")
            else:
                print("[LISTENER] No other listeners found")
        else:
            print("[LISTENER] No existing listeners found")

    except Exception as e:
        print(f"[LISTENER] Could not check for existing listeners: {e}")


if __name__ == "__main__":
    # Kill any existing listeners before starting
    kill_existing_listeners()

    # Start listening
    listen_for_notifications()
