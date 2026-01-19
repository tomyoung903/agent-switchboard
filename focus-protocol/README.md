# Focus Protocol

Ultra-fast Windows URL protocol handler for instant window switching via `focus:` URL links.

## Overview

The Focus Protocol enables instant window switching by registering a custom `focus:` URL protocol with Windows. When you invoke `focus:calculator` or `focus:chrome`, it instantly brings that window to the foreground - 87% faster than PowerShell-based alternatives.

**Performance**: 150ms window switching (compared to 1150ms for original implementations)

## Features

- **Ultra-Fast**: Compiled C# executable using direct Windows API calls
- **Simple Syntax**: `focus:windowname` to switch to any window
- **Smart Matching**: Matches by window title or process name (case-insensitive)
- **Reliable Focus**: Uses thread attachment techniques to bypass Windows focus restrictions
- **Auto-Restore**: Automatically restores minimized windows before focusing
- **Pre-compiled**: Ready-to-use executable included (no compilation required)

## Installation

### Quick Install (Pre-compiled)

Run in **PowerShell as Administrator**:

```powershell
cd focus-protocol
.\install-focus-protocol-exe.ps1
```

This registers the `focus:` protocol in Windows Registry and makes it available system-wide.

### Compile from Source (Optional)

If you want to rebuild the executable:

```powershell
.\compile-focuswindow.ps1
.\install-focus-protocol-exe.ps1
```

## Usage

### From PowerShell or Command Line

```powershell
Start-Process focus:calculator
Start-Process focus:notepad
Start-Process focus:"Microsoft Edge"
Start-Process focus:chrome
```

### From Batch Scripts

```batch
start focus:calculator
start focus:discord
```

### From URLs or Hyperlinks

```html
<a href="focus:chrome">Switch to Chrome</a>
```

### From Any Application

Any program that can open URLs can use the focus protocol - browsers, automation tools, launchers, etc.

## How It Works

1. **Window Discovery**: Enumerates all visible windows using Windows API
2. **Smart Matching**: Matches your query against:
   - Window titles (case-insensitive substring match)
   - Process names (executable name)
3. **Window Restoration**: If the window is minimized, restores it first
4. **Thread Manipulation**: Attaches input threads to bypass Windows focus restrictions
5. **Foreground Activation**: Brings the window to the top and sets focus

### Technical Implementation

The implementation uses compiled C# with P/Invoke calls to Windows APIs:

- `EnumWindows` - Iterate all windows
- `GetWindowText` - Get window titles
- `GetWindowThreadProcessId` - Get process information
- `IsWindowVisible` - Filter visible windows
- `SetForegroundWindow` / `BringWindowToTop` - Focus window
- `AttachThreadInput` - Bypass focus restrictions
- `ShowWindow` - Restore minimized windows

## Files

| File | Purpose |
|------|---------|
| **FocusWindow.exe** | Pre-compiled executable (ready to use) |
| **FocusWindow.cs** | C# source code (~153 lines) |
| **install-focus-protocol-exe.ps1** | Installation script (registers URL protocol) |
| **compile-focuswindow.ps1** | Build script (optional, for recompiling) |

## Uninstallation

```powershell
.\install-focus-protocol-exe.ps1 -Uninstall
```

This removes the `focus:` protocol registration from Windows Registry.

## Requirements

**To Use**: Windows OS only

**To Compile** (optional): C# compiler (csc.exe) from:
- .NET Framework Developer Pack, or
- Visual Studio Build Tools, or
- Visual Studio (any edition)

## Performance Comparison

| Implementation | Time | Improvement |
|----------------|------|-------------|
| Original (2 PowerShell calls) | 1150ms | baseline |
| Fast (1 PowerShell call) | 600ms | 50% faster |
| **EXE (this version)** | **150ms** | **87% faster** |

The dramatic speedup comes from eliminating PowerShell startup overhead and using direct native API calls.

## Use Cases

- **Instant Window Switching**: Replace Alt+Tab with precise window selection
- **Application Launcher**: Focus existing windows instead of opening new instances
- **Automation Integration**: Integrate with AutoHotkey, batch scripts, or other tools
- **Custom Dashboards**: Create URL-based window switchers in web interfaces
- **Productivity Tools**: Build keyboard shortcuts or menu systems for window management

## Examples

### AutoHotkey Integration

```autohotkey
; Win+C to focus Chrome
#c::Run, focus:chrome

; Win+V to focus VS Code
#v::Run, focus:code
```

### Task Switcher Script

```powershell
# Create a menu of common windows
$windows = @{
    "1" = "focus:chrome"
    "2" = "focus:code"
    "3" = "focus:slack"
    "4" = "focus:outlook"
}

$choice = Read-Host "Select window (1-4)"
Start-Process $windows[$choice]
```

## Registry Details

The installation creates these registry entries:

```
HKCU:\Software\Classes\focus
  (Default) = "URL:Focus Window Protocol"
  URL Protocol = ""
  shell\open\command
    (Default) = "<path-to-FocusWindow.exe>" "%1"
```

## License

Part of the windows utility collection.
