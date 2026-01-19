#!/bin/bash

# Launch notification app on Windows from WSL
# This script uses PowerShell to launch the app on Windows

NOTI_DIR="/home/tom/windows/noti_app"
MAIN_PATH="$NOTI_DIR/main.py"

# Kill any existing notification app processes first
echo "Checking for existing notification app..."

# Kill ALL Python processes on Windows (more aggressive)
powershell.exe -NoProfile -Command "Get-Process python* 2>\$null | Stop-Process -Force 2>\$null" 2>/dev/null

# Also kill any WSL-side processes
pkill -f "notification_app.py" 2>/dev/null
pkill -f "ntfy_listener.py" 2>/dev/null
pkill -f "main.py" 2>/dev/null

echo "Killed any existing app instances"

# Small delay to ensure processes are fully terminated
sleep 1

# Convert WSL path to Windows path for PowerShell
MAIN_PATH_WIN=$(wslpath -w "$MAIN_PATH")

# Launch on Windows using PowerShell (run in background so it doesn't block)
powershell.exe -NoProfile -Command "python3 '$MAIN_PATH_WIN'" &
sleep 1
echo "App launched"
