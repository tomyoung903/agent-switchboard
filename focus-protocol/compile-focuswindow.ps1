# Compile FocusWindow.cs to native executable
# This will create FocusWindow.exe - much faster than PowerShell!

$csFile = "FocusWindow.cs"
$exeFile = "FocusWindow.exe"

if (-not (Test-Path $csFile)) {
    Write-Host "ERROR: $csFile not found!" -ForegroundColor Red
    exit 1
}

Write-Host "Compiling FocusWindow.exe..." -ForegroundColor Cyan

# Try to find csc.exe (C# compiler)
$cscPaths = @(
    "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
    "C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe",
    "C:\Program Files\Microsoft Visual Studio\*\*\MSBuild\*\Bin\Roslyn\csc.exe",
    "C:\Program Files (x86)\Microsoft Visual Studio\*\*\MSBuild\*\Bin\Roslyn\csc.exe"
)

$csc = $null
foreach ($path in $cscPaths) {
    $found = Get-Item $path -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) {
        $csc = $found.FullName
        break
    }
}

if (-not $csc) {
    Write-Host "ERROR: C# compiler (csc.exe) not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install one of:" -ForegroundColor Yellow
    Write-Host "  1. .NET Framework Developer Pack" -ForegroundColor Gray
    Write-Host "  2. Visual Studio Build Tools" -ForegroundColor Gray
    Write-Host "  3. Visual Studio (any edition)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Or use the PowerShell version (install-focus-protocol-fast.ps1)" -ForegroundColor Cyan
    exit 1
}

Write-Host "Using compiler: $csc" -ForegroundColor Gray

# Compile
& $csc /target:winexe /out:$exeFile /nologo /optimize+ $csFile

if ($LASTEXITCODE -eq 0 -and (Test-Path $exeFile)) {
    Write-Host ""
    Write-Host "SUCCESS: $exeFile compiled!" -ForegroundColor Green
    Write-Host ""
    Write-Host "File size: $((Get-Item $exeFile).Length / 1KB) KB" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Test it:" -ForegroundColor Cyan
    Write-Host "  .\$exeFile calculator" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Install it:" -ForegroundColor Cyan
    Write-Host "  .\install-focus-protocol-exe.ps1" -ForegroundColor Gray
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "ERROR: Compilation failed!" -ForegroundColor Red
    exit 1
}

