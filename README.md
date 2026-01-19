# Agent Switchboard

A Windows notification system for AI agent workflows. Track multiple agent windows, see their status at a glance, and switch focus instantly.

## The Problem

When running multiple AI agents (Claude, ChatGPT, Cursor, etc.) across different windows, you lose track of which ones need attention. Alt+Tab cycling is slow and breaks your flow. You need a way to:

- Know when an agent finishes a task
- See status of all agent windows in one place
- Switch to any agent window instantly

## How It Works

```
Your AI agents → ntfy.sh → Notification App → focus: protocol → Window switches
```

1. **Agents publish status** to ntfy.sh (e.g., `claude:project - done`)
2. **Notification app** displays all agents as clickable bars with status
3. **Press Enter** to instantly switch to that window via the `focus:` protocol

<!-- TODO: Add demo GIF here -->

## Features

- **Real-time status updates** via ntfy.sh SSE subscription
- **Keyboard-driven UI** - navigate with arrows, switch with Enter
- **Global hotkey** (Ctrl+,) to toggle visibility
- **System tray** integration - runs in background
- **Instant window switching** - 150ms via compiled C# (87% faster than PowerShell)
- **Status color coding** - done (green), ongoing (blue), addressed (gray)

## Requirements

- Windows 10/11
- Python 3.8+ (Windows version with tkinter)
- WSL (optional, for development)

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/tomyoung903/agent-switchboard.git
cd agent-switchboard
```

### 2. Install Python dependencies

```bash
pip install pillow pystray pynput requests
```

### 3. Install the focus: protocol (PowerShell as Administrator)

```powershell
cd focus-protocol
.\install-focus-protocol-exe.ps1
```

This registers the `focus:` URL protocol so clicking `focus:chrome` brings Chrome to front.

### 4. Configure ntfy topic

Edit `noti_app/src/ntfy_listener.py` and change:

```python
TOPIC_NAME = "your_unique_topic_name"  # Make this unique to you
```

### 5. Run the app

```bash
cd noti_app
python main.py
```

The app starts minimized to system tray. Press `Ctrl+,` to show/hide.

## Sending Notifications

From any script or agent, send notifications via ntfy.sh:

```bash
# Simple window registration
curl -d "myagent" ntfy.sh/your_topic_name

# With status
curl -d "myagent - done" ntfy.sh/your_topic_name
curl -d "claude:project - ongoing" ntfy.sh/your_topic_name
```

### Message Format

```
window_name - status
```

- `window_name`: Used to match and focus the window (matches title or process name)
- `status`: Optional - `done`, `ongoing`, `addressed`, or any custom text

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+,` | Toggle window visibility (global) |
| `↑` / `↓` | Navigate between agents |
| `Tab` | Next agent |
| `Enter` | Switch to selected agent's window |
| `A` | Mark as addressed |
| `Delete` | Remove from list |
| `Home` / `End` | Jump to first/last |
| Any letter | Hide to tray |

## Configuration

Key settings in `noti_app/src/notification_app.py`:

```python
# Window spawn position (adjust for your monitor setup)
SPAWN_X = 1500
SPAWN_Y = -1100  # Negative for monitor above primary

# Window position mode
WINDOW_POSITION = "upper-monitor-center"  # or "bottom-right", "center", etc.
```

Database location in `noti_app/src/db.py`:

```python
# Windows AppData (for proper SQLite locking)
DB_DIR = Path(appdata) / "noti_app"
```

## Architecture

```
noti_app/
├── main.py              # Entry point
├── src/
│   ├── notification_app.py  # Tkinter UI, keyboard handling
│   ├── ntfy_listener.py     # SSE subscription to ntfy.sh
│   ├── db.py                # SQLite storage
│   ├── styles.py            # UI theming
│   └── ui_utils.py          # Rounded corners, etc.

focus-protocol/
├── FocusWindow.exe      # Pre-compiled window switcher
├── FocusWindow.cs       # C# source (uses Windows API)
├── install-*.ps1        # Registry setup scripts
```

## Use Cases

- **AI Agent Dashboard**: Monitor Claude Code, Cursor, ChatGPT windows
- **Build Notifications**: Alert when long builds complete
- **Task Switching**: Quick keyboard-driven window management
- **Remote Notifications**: Receive alerts from servers/CI pipelines

## License

MIT License - see [LICENSE](LICENSE)

---

*This is a demo project showing what's possible with ntfy.sh + custom URL protocols. Fork and customize for your own workflow!*
