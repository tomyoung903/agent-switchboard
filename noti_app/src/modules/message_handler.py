"""Message queue monitoring and handling"""

import json
import threading
import time
from pathlib import Path


def load_messages_from_queue(queue_file):
    """Load messages from the queue file (JSONL format)"""
    messages = []

    try:
        if queue_file.exists():
            with open(queue_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            message = json.loads(line)
                            messages.append(message)
                        except json.JSONDecodeError:
                            pass
    except Exception as e:
        print(f"Error loading messages from queue: {e}")

    return messages


def get_default_messages():
    """Return default sample messages when queue is empty"""
    return [
        {"window_name": "osora", "status": None},
        {"window_name": "osora2", "status": None},
        {"window_name": "osora3", "status": None}
    ]


def start_message_monitor(app, queue_file, poll_interval=0.5):
    """Start the background message monitoring thread"""
    def monitor_queue_for_updates():
        """Background thread - continuously monitor queue file for new messages"""
        print(f"[MONITOR] Starting queue monitor, initial count: {app.last_message_count}")
        check_count = 0

        while app.monitor_running:
            try:
                new_messages = load_messages_from_queue(queue_file)
                current_count = len(new_messages)
                check_count += 1

                if current_count > app.last_message_count:
                    added_messages = new_messages[app.last_message_count:]
                    print(f"[MONITOR] Detected {len(added_messages)} new messages!")
                    app.root.after(0, app.add_new_messages, added_messages)
                    app.last_message_count = current_count

                if check_count % 10 == 0:
                    print(f"[MONITOR] Check #{check_count}: Queue has {current_count} messages (tracking {app.last_message_count})")

                time.sleep(poll_interval)
            except Exception as e:
                print(f"[MONITOR] Error monitoring queue: {e}")

    monitor_thread = threading.Thread(
        target=monitor_queue_for_updates,
        daemon=True
    )
    monitor_thread.start()
    return monitor_thread
