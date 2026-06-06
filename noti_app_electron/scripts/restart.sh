#!/bin/bash

# Restart Electron noti_app from WSL
# Runs the app from the Windows copy at C:\noti_app_electron

echo "Restarting noti_app Electron..."

# Kill existing electron instances and free up ports
echo "Killing existing instances..."
powershell.exe -NoProfile -Command '
    # Kill electron processes from noti_app_electron
    Get-Process | Where-Object { $_.Path -like "*noti_app_electron*" } | Stop-Process -Force -ErrorAction SilentlyContinue

    # Kill processes on ports used by the app (3456, 3457, 9876, 9877)
    @(3456, 3457, 9876, 9877, 9220) | ForEach-Object {
        $conns = Get-NetTCPConnection -LocalPort $_ -ErrorAction SilentlyContinue
        foreach ($conn in $conns) {
            Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
' 2>/dev/null

echo "Waiting for processes to terminate..."
sleep 2

# Start the app from Windows path
echo "Starting app..."
powershell.exe -NoProfile -Command '
    Set-Location "C:\noti_app_electron"
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c C:\noti_app_electron\launch_noti.bat" -WorkingDirectory "C:\noti_app_electron"
' 2>/dev/null &

sleep 4
echo "App restarted"
