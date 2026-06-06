# Setup script for Windows
# Run this from PowerShell in Windows

$ErrorActionPreference = "Stop"

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "Setting up noti_app_electron..." -ForegroundColor Cyan

# Check for Node.js
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) {
    Write-Host "Node.js not found. Installing via winget..." -ForegroundColor Yellow
    winget install OpenJS.NodeJS.LTS
    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}

# Remove WSL node_modules if exists (wrong platform binaries)
if (Test-Path "node_modules") {
    Write-Host "Removing existing node_modules..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force "node_modules"
}

# Install dependencies
Write-Host "Installing dependencies..." -ForegroundColor Cyan
npm install

Write-Host "`nSetup complete!" -ForegroundColor Green
Write-Host "Run 'npm start' to launch the app" -ForegroundColor Cyan
