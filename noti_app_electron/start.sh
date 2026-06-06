#!/bin/bash
# Start noti_app_electron as a WINDOWS app (not WSLg)
# Syncs to Windows location and runs via PowerShell

WSL_DIR="/home/tom/windows/noti_app_electron"
WIN_DIR="C:\\noti_app_electron"

# Sync files (excluding node_modules)
echo "Syncing to Windows..."
mkdir -p /mnt/c/noti_app_electron
rsync -av --delete --exclude='node_modules' --exclude='.webpack' "$WSL_DIR/" /mnt/c/noti_app_electron/

# Run from Windows via PowerShell (this runs Windows npm/electron, not Linux)
echo "Starting Windows Electron app..."
powershell.exe -NoProfile -Command "
    Set-Location '$WIN_DIR'
    if (-not (Test-Path 'node_modules')) {
        Write-Host 'Installing dependencies...'
        npm install
    }
    cmd.exe /c C:\noti_app_electron\launch_noti.bat
"
