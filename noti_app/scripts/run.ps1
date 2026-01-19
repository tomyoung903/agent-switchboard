# PowerShell script to launch the notification app
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

# Run the Python app
& python3 notification_app.py
