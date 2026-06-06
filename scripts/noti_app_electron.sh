#!/usr/bin/env bash
set -euo pipefail

APP_DIR='C:\noti_app_electron'
LAUNCH_BAT='C:\noti_app_electron\launch_noti.bat'

usage() {
  printf 'Usage: %s {restart|start|status|stop}\n' "$0" >&2
}

status() {
  powershell.exe -NoProfile -Command '
    Get-CimInstance Win32_Process |
      Where-Object {
        ($_.Name -eq "electron.exe" -or $_.Name -eq "cmd.exe") -and
        ($_.CommandLine -like "*noti_app_electron*" -or $_.ExecutablePath -like "*noti_app_electron*")
      } |
      Select-Object ProcessId,Name,CommandLine |
      Format-List
  '
}

stop_app() {
  powershell.exe -NoProfile -Command '
    Get-CimInstance Win32_Process |
      Where-Object {
        ($_.Name -eq "electron.exe" -or $_.Name -eq "cmd.exe") -and
        ($_.CommandLine -like "*noti_app_electron*" -or $_.ExecutablePath -like "*noti_app_electron*")
      } |
      ForEach-Object {
        try {
          Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
          "stopped $($_.ProcessId) $($_.Name)"
        } catch {
          "skip $($_.ProcessId) $($_.Name): $($_.Exception.Message)"
        }
      }
  '
}

start_app() {
  powershell.exe -NoProfile -Command "Start-Process -FilePath 'cmd.exe' -ArgumentList '/c \"$LAUNCH_BAT\"' -WorkingDirectory '$APP_DIR'"
}

case "${1:-restart}" in
  status)
    status
    ;;
  stop)
    stop_app
    ;;
  start)
    start_app
    sleep 2
    status
    ;;
  restart)
    stop_app
    sleep 2
    start_app
    sleep 2
    status
    ;;
  *)
    usage
    exit 2
    ;;
esac
