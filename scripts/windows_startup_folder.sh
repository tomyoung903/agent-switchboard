#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  windows_startup_folder.sh add --name NAME --target WINDOWS_PATH [--working-dir WINDOWS_DIR]
  windows_startup_folder.sh status --name NAME
  windows_startup_folder.sh remove --name NAME
  windows_startup_folder.sh list
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

ACTION="${1:-}"
[[ -n "$ACTION" ]] || { usage; exit 2; }
shift || true

NAME=""
TARGET=""
WORKING_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name)
      NAME="${2:-}"
      shift 2
      ;;
    --target)
      TARGET="${2:-}"
      shift 2
      ;;
    --working-dir)
      WORKING_DIR="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
done

case "$ACTION" in
  add)
    [[ -n "$NAME" ]] || die "--name is required"
    [[ -n "$TARGET" ]] || die "--target is required"
    ;;
  status|remove)
    [[ -n "$NAME" ]] || die "--name is required"
    ;;
  list)
    ;;
  *)
    usage
    exit 2
    ;;
esac

ps_quote() {
  local value="${1//\'/\'\'}"
  printf "'%s'" "$value"
}

PS_ACTION="$(ps_quote "$ACTION")"
PS_NAME="$(ps_quote "$NAME")"
PS_TARGET="$(ps_quote "$TARGET")"
PS_WORKING_DIR="$(ps_quote "$WORKING_DIR")"

read -r -d '' PS_SCRIPT <<'EOF' || true
$ErrorActionPreference = "Stop"

function Get-StartupDir {
  [Environment]::GetFolderPath("Startup")
}

function Get-LinkPath([string]$name) {
  if (-not $name.EndsWith(".lnk", [StringComparison]::OrdinalIgnoreCase)) {
    $name = "$name.lnk"
  }
  Join-Path (Get-StartupDir) $name
}

function Read-Link([string]$path) {
  $shell = New-Object -ComObject WScript.Shell
  $shortcut = $shell.CreateShortcut($path)
  [PSCustomObject]@{
    Name = [IO.Path]::GetFileName($path)
    Path = $path
    TargetPath = $shortcut.TargetPath
    Arguments = $shortcut.Arguments
    WorkingDirectory = $shortcut.WorkingDirectory
  }
}

$action = __ACTION__
$name = __NAME__
$target = __TARGET__
$workingDir = __WORKING_DIR__
$startupDir = Get-StartupDir

switch ($action) {
  "list" {
    Write-Output "Startup folder: $startupDir"
    Get-ChildItem -Path $startupDir -Filter "*.lnk" -Force |
      Sort-Object Name |
      ForEach-Object { Read-Link $_.FullName } |
      Format-List
  }
  "status" {
    $linkPath = Get-LinkPath $name
    Write-Output "Startup folder: $startupDir"
    if (-not (Test-Path $linkPath)) {
      Write-Output "Missing: $linkPath"
      exit 1
    }
    Read-Link $linkPath | Format-List
  }
  "remove" {
    $linkPath = Get-LinkPath $name
    if (Test-Path $linkPath) {
      Remove-Item -Path $linkPath -Force
      Write-Output "Removed: $linkPath"
    } else {
      Write-Output "Already missing: $linkPath"
    }
  }
  "add" {
    if (-not (Test-Path $target)) {
      throw "Target does not exist: $target"
    }
    if ([string]::IsNullOrWhiteSpace($workingDir)) {
      $workingDir = Split-Path -Parent $target
    }
    if ($workingDir -and -not (Test-Path $workingDir)) {
      throw "Working directory does not exist: $workingDir"
    }

    $linkPath = Get-LinkPath $name
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($linkPath)
    $shortcut.TargetPath = $target
    $shortcut.WorkingDirectory = $workingDir
    $shortcut.Save()

    Write-Output "Added: $linkPath"
    Read-Link $linkPath | Format-List
  }
  default {
    throw "Unknown action: $action"
  }
}
EOF

PS_SCRIPT="${PS_SCRIPT/__ACTION__/$PS_ACTION}"
PS_SCRIPT="${PS_SCRIPT/__NAME__/$PS_NAME}"
PS_SCRIPT="${PS_SCRIPT/__TARGET__/$PS_TARGET}"
PS_SCRIPT="${PS_SCRIPT/__WORKING_DIR__/$PS_WORKING_DIR}"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$PS_SCRIPT"
