# PowerShell script to run the notification app
$wslPath = "\\wsl.localhost\Ubuntu\home\tom\windows\noti_app"

# Change to the app directory
Push-Location $wslPath

# Run the Python app with Windows Python (which has tkinter)
python3 main.py

# Keep window open if there was an error
if ($LASTEXITCODE -ne 0) {
    Read-Host "Press Enter to close this window"
}

Pop-Location
