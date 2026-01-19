# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Agent Switchboard is a Windows notification system for AI agent workflows, consisting of two components:

1. **noti_app** - A Python/tkinter notification app that displays clickable message bars for tracking AI agent windows/tasks
2. **focus-protocol** - A Windows URL protocol handler (`focus:windowname`) for instant window switching

The system is designed for WSL+Windows environments where AI agents publish status updates via ntfy.sh, and users can quickly switch focus between agent windows.

## Architecture

```
ntfy.sh (cloud)
    ↓ SSE
ntfy_listener.py (background process)
    ↓ SQLite
notification_app.py (tkinter UI)
    ↓ focus: protocol
FocusWindow.exe (Windows API)
```

- **ntfy_listener.py**: Subscribes to ntfy.sh topic, parses messages (`windowname - status`), writes to SQLite
- **notification_app.py**: Monitors SQLite for changes, renders message bars with status, triggers `focus:` protocol on Enter
- **db.py**: SQLite wrapper with cross-platform path handling (Windows AppData for proper file locking)
- **FocusWindow.exe**: Pre-compiled C# that uses Windows API to bring windows to foreground

## Development Commands

### Run the notification app (from WSL)
```bash
cd noti_app && ./scripts/run.sh
```

### Run directly with Windows Python
```powershell
cd noti_app
python3 main.py
```

### Install focus protocol (PowerShell as Admin)
```powershell
cd focus-protocol
.\install-focus-protocol-exe.ps1
```

### Recompile FocusWindow.exe (optional)
```powershell
cd focus-protocol
.\compile-focuswindow.ps1
```

## Key Configuration Points

- **ntfy topic**: `TOPIC_NAME` in `noti_app/src/ntfy_listener.py`
- **Window spawn position**: `SPAWN_X`, `SPAWN_Y` in `noti_app/src/notification_app.py`
- **Database location**: `DB_DIR` in `noti_app/src/db.py` (uses Windows AppData)
- **Global hotkey**: `Ctrl+,` toggles window visibility

## Message Format

ntfy messages use format: `windowname - status`
- Example: `claude:project - done`
- Status values: `done`, `ongoing`, `addressed`, or custom

## Platform Notes

- The app runs as a Windows GUI but can be launched from WSL
- SQLite database is stored in Windows AppData for proper file locking across WSL/Windows boundary
- focus-protocol only works on Windows (uses Windows Registry and native APIs)
