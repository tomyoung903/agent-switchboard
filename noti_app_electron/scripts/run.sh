#!/bin/bash

# Run Electron noti_app from WSL

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
APP_DIR_WIN=$(wslpath -w "$APP_DIR")

echo "Starting noti_app Electron..."

# Kill existing instances
powershell.exe -Command "Get-Process -Name 'noti*' -ErrorAction SilentlyContinue | Stop-Process -Force" 2>/dev/null

# Check if node_modules exists
if [ ! -d "$APP_DIR/node_modules" ]; then
    echo "Installing dependencies..."
    cd "$APP_DIR"
    npm install
fi

# Run the app
cd "$APP_DIR"
npm start &

echo "App started"
