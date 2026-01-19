@echo off
REM Batch file to run the notification app from the correct directory
REM Use PowerShell to navigate to the WSL directory and run Python
powershell.exe -Command "Set-Location '\\wsl.localhost\Ubuntu\home\tom\windows\noti_app'; python3 main.py"
pause
