"""
Database module for noti_app using SQLite.

SQLite provides:
- Atomic transactions (no race conditions)
- Built-in locking (no corruption)
- Reliable across WSL/Windows boundary
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager
import platform
import sys

# Database file location - use native Windows path for proper SQLite locking
# UNC paths (\\wsl.localhost\...) don't support SQLite locking correctly
import os

if platform.system() == 'Windows':
    # Use Windows AppData for reliable SQLite locking
    appdata = os.environ.get('LOCALAPPDATA', r'C:\Users\ytj19\AppData\Local')
    DB_DIR = Path(appdata) / "noti_app"
else:
    # WSL accesses same Windows location via /mnt/c/
    # Get the Windows username from the path or default
    DB_DIR = Path("/mnt/c/Users/ytj19/AppData/Local/noti_app")

DB_FILE = DB_DIR / "windows.db"

# Ensure directory exists
DB_DIR.mkdir(parents=True, exist_ok=True)


def get_connection(retries=3):
    """Get a database connection with proper settings for concurrent access."""
    import time
    last_error = None

    for attempt in range(retries):
        try:
            conn = sqlite3.connect(
                str(DB_FILE),
                timeout=30.0,  # Wait up to 30 seconds for locks
                isolation_level='DEFERRED'  # Defer locking until needed
            )
            conn.row_factory = sqlite3.Row  # Return rows as dict-like objects
            # Set busy timeout (more portable than WAL for cross-platform)
            conn.execute('PRAGMA busy_timeout=30000')  # 30 second busy timeout
            return conn
        except sqlite3.OperationalError as e:
            last_error = e
            if attempt < retries - 1:
                print(f"[DB] Connection attempt {attempt + 1} failed, retrying... ({e})")
                time.sleep(0.5 * (attempt + 1))  # Exponential backoff
            continue

    raise last_error


@contextmanager
def db_transaction():
    """Context manager for database transactions with automatic commit/rollback."""
    conn = None
    try:
        conn = get_connection()
        yield conn
        conn.commit()
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except:
                pass
        raise e
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


def init_db():
    """Initialize the database schema."""
    with db_transaction() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS windows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                window_name TEXT UNIQUE NOT NULL,
                status TEXT,
                timestamp TEXT NOT NULL
            )
        ''')
        # Create index for faster lookups
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_window_name ON windows(window_name)
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_timestamp ON windows(timestamp DESC)
        ''')


def update_window_status(window_name: str, status: str = None) -> bool:
    """
    Update or insert a window status (upsert).
    Returns True on success, False on failure.
    """
    timestamp = datetime.now().isoformat()

    try:
        with db_transaction() as conn:
            # SQLite UPSERT (INSERT OR REPLACE)
            conn.execute('''
                INSERT INTO windows (window_name, status, timestamp)
                VALUES (?, ?, ?)
                ON CONFLICT(window_name) DO UPDATE SET
                    status = excluded.status,
                    timestamp = excluded.timestamp
            ''', (window_name, status, timestamp))

        print(f"[DB] Updated: {window_name}" + (f" - {status}" if status else ""))
        return True
    except Exception as e:
        print(f"[DB] Error updating window status: {e}")
        return False


def get_all_windows() -> list:
    """
    Get all windows sorted by timestamp (most recent first).
    Returns list of dicts with window_name, status, timestamp.
    """
    try:
        with db_transaction() as conn:
            cursor = conn.execute('''
                SELECT window_name, status, timestamp
                FROM windows
                ORDER BY timestamp DESC
            ''')
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"[DB] Error loading windows: {e}")
        return []


def delete_window(window_name: str) -> bool:
    """Delete a window by name. Returns True on success."""
    try:
        with db_transaction() as conn:
            conn.execute('DELETE FROM windows WHERE window_name = ?', (window_name,))
        print(f"[DB] Deleted: {window_name}")
        return True
    except Exception as e:
        print(f"[DB] Error deleting window: {e}")
        return False


def get_db_mtime() -> float:
    """
    Get the modification time of the database file.
    Used for change detection without locking the database.
    """
    try:
        if DB_FILE.exists():
            return DB_FILE.stat().st_mtime
    except OSError as e:
        print(f"[DB] Error getting mtime: {e}")
    return 0.0


def get_db_hash() -> str:
    """
    Get a hash representing the current database state.
    Used for change detection.
    Falls back to mtime if database is locked.
    """
    import hashlib
    try:
        with db_transaction() as conn:
            # Get all data in a deterministic order
            cursor = conn.execute('''
                SELECT window_name, status, timestamp
                FROM windows
                ORDER BY window_name
            ''')
            data = cursor.fetchall()
            # Create hash from data
            content = json.dumps([dict(row) for row in data], sort_keys=True)
            return hashlib.md5(content.encode()).hexdigest()
    except sqlite3.OperationalError as e:
        # Database locked - use mtime as fallback
        mtime = get_db_mtime()
        if mtime > 0:
            return f"mtime:{mtime}"
        return ""
    except Exception as e:
        print(f"[DB] Error getting hash: {e}")
        return ""


def migrate_from_jsonl(jsonl_path: Path) -> bool:
    """
    Migrate data from JSONL file to SQLite database.
    Returns True on success.
    """
    if not jsonl_path.exists():
        print("[DB] No JSONL file to migrate")
        return True

    try:
        windows = []
        with open(jsonl_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        windows.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

        if not windows:
            print("[DB] JSONL file is empty, nothing to migrate")
            return True

        with db_transaction() as conn:
            for window in windows:
                conn.execute('''
                    INSERT OR REPLACE INTO windows (window_name, status, timestamp)
                    VALUES (?, ?, ?)
                ''', (
                    window.get('window_name', 'unknown'),
                    window.get('status'),
                    window.get('timestamp', datetime.now().isoformat())
                ))

        print(f"[DB] Migrated {len(windows)} windows from JSONL")

        # Rename old file as backup
        backup_path = jsonl_path.with_suffix('.jsonl.bak')
        jsonl_path.rename(backup_path)
        print(f"[DB] Backed up JSONL to {backup_path}")

        return True
    except Exception as e:
        print(f"[DB] Migration error: {e}")
        return False


# Initialize database on module import (with retry for cross-platform access)
try:
    init_db()
except sqlite3.OperationalError as e:
    print(f"[DB] Warning: Could not initialize database on import: {e}")
    print("[DB] Database will be initialized on first write operation")
