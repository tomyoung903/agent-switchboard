// Fast Window Focus - Compiled C# version
// Compile: csc /target:winexe /out:FocusWindow.exe FocusWindow.cs
// Or use: dotnet build (if you have .NET SDK)

using System;
using System.Runtime.InteropServices;
using System.Text;
using System.Diagnostics;
using System.IO;
using System.Collections.Generic;
using System.Threading;

class FocusWindow
{
    [DllImport("user32.dll")]
    private static extern bool IsWindowVisible(IntPtr hWnd);
    
    [DllImport("user32.dll")]
    private static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
    
    [DllImport("user32.dll")]
    private static extern int GetWindowTextLength(IntPtr hWnd);
    
    [DllImport("user32.dll")]
    private static extern bool EnumWindows(EnumWindowsProc enumProc, IntPtr lParam);
    
    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    
    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(IntPtr hWnd);
    
    [DllImport("user32.dll")]
    private static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    
    [DllImport("user32.dll")]
    private static extern bool IsIconic(IntPtr hWnd);
    
    [DllImport("user32.dll")]
    private static extern bool AttachThreadInput(uint idAttach, uint idAttachTo, bool fAttach);
    
    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, IntPtr ProcessId);
    
    [DllImport("kernel32.dll")]
    private static extern uint GetCurrentThreadId();
    
    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();
    
    [DllImport("user32.dll")]
    private static extern bool BringWindowToTop(IntPtr hWnd);
    
    private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    
    private const int SW_RESTORE = 9;

    private static IntPtr targetHandle = IntPtr.Zero;
    private static IntPtr fallbackHandle = IntPtr.Zero;
    private static string searchTarget = "";
    
    static void Main(string[] args)
    {
        if (args.Length == 0)
        {
            Console.WriteLine("Usage: FocusWindow.exe <target>");
            return;
        }
        
        // Parse target (remove focus: prefix if present)
        searchTarget = args[0].Replace("focus:", "").Trim('/');
        
        // Find window - scan all windows for best match
        EnumWindows(EnumWindowCallback, IntPtr.Zero);

        // Prefer exact whole-word match, fallback to partial match
        IntPtr windowToFocus = targetHandle != IntPtr.Zero ? targetHandle : fallbackHandle;

        // Focus the window if found
        if (windowToFocus != IntPtr.Zero)
            FocusWindowFast(windowToFocus);

        // Process co-triggers
        string originalTarget = searchTarget.ToLower();

        // Try multiple methods to find exe directory
        string exeDir = null;
        try { exeDir = Path.GetDirectoryName(System.Reflection.Assembly.GetExecutingAssembly().Location); } catch { }
        if (string.IsNullOrEmpty(exeDir))
            try { exeDir = AppDomain.CurrentDomain.BaseDirectory; } catch { }
        if (string.IsNullOrEmpty(exeDir))
            try { exeDir = Path.GetDirectoryName(Process.GetCurrentProcess().MainModule.FileName); } catch { }

        if (string.IsNullOrEmpty(exeDir)) return;

        string configPath = Path.Combine(exeDir, "co-triggers.json");

        // Debug: write to temp file
        try {
            string debugPath = Path.Combine(exeDir, "debug.txt");
            string debugContent = String.Format("exeDir: {0}\nconfigPath: {1}\nexists: {2}\ntrigger: {3}\ndebugPath: {4}", exeDir, configPath, File.Exists(configPath), originalTarget, debugPath);
            File.WriteAllText(debugPath, debugContent);
        } catch (Exception ex) {
            // Fallback to temp directory
            try { File.WriteAllText(Path.Combine(Path.GetTempPath(), "focuswindow-debug.txt"), String.Format("exeDir: {0}\nconfigPath: {1}\nexists: {2}\ntrigger: {3}\nerror: {4}", exeDir, configPath, File.Exists(configPath), originalTarget, ex.Message)); } catch { }
        }

        if (File.Exists(configPath))
        {
            string[] coTargets = GetCoTriggers(configPath, originalTarget);
            foreach (string coTarget in coTargets)
            {
                Thread.Sleep(100);
                FocusWindowByName(coTarget);
            }
        }
    }

    private static string[] GetCoTriggers(string configPath, string trigger)
    {
        try
        {
            string json = File.ReadAllText(configPath);
            // Simple JSON parsing for format: "key": ["val1", "val2"]
            // Must match key (followed by ":"), not value
            string pattern = "\"" + trigger + "\"";
            int keyIndex = 0;
            while (true)
            {
                keyIndex = json.IndexOf(pattern, keyIndex, StringComparison.OrdinalIgnoreCase);
                if (keyIndex < 0) return new string[0];
                // Check if this is a key (followed by colon)
                int afterQuote = keyIndex + pattern.Length;
                while (afterQuote < json.Length && char.IsWhiteSpace(json[afterQuote])) afterQuote++;
                if (afterQuote < json.Length && json[afterQuote] == ':') break;
                keyIndex++; // Not a key, keep searching
            }

            int bracketStart = json.IndexOf('[', keyIndex);
            if (bracketStart < 0) return new string[0];

            int bracketEnd = json.IndexOf(']', bracketStart);
            if (bracketEnd < 0) return new string[0];

            string arrayContent = json.Substring(bracketStart + 1, bracketEnd - bracketStart - 1);
            List<string> results = new List<string>();

            foreach (string part in arrayContent.Split(','))
            {
                string trimmed = part.Trim().Trim('"');
                if (!string.IsNullOrEmpty(trimmed))
                    results.Add(trimmed);
            }
            return results.ToArray();
        }
        catch
        {
            return new string[0];
        }
    }

    private static void FocusWindowByName(string name)
    {
        targetHandle = IntPtr.Zero;
        fallbackHandle = IntPtr.Zero;
        searchTarget = name;
        EnumWindows(EnumWindowCallback, IntPtr.Zero);

        IntPtr windowToFocus = targetHandle != IntPtr.Zero ? targetHandle : fallbackHandle;
        if (windowToFocus != IntPtr.Zero)
            FocusWindowFast(windowToFocus);
    }
    
    private static bool EnumWindowCallback(IntPtr hWnd, IntPtr lParam)
    {
        if (!IsWindowVisible(hWnd))
            return true;

        int length = GetWindowTextLength(hWnd);
        if (length == 0)
            return true;

        StringBuilder sb = new StringBuilder(length + 1);
        GetWindowText(hWnd, sb, sb.Capacity);
        string title = sb.ToString();

        // Check for whole-word match (words separated by spaces)
        bool isWholeWordMatch = IsWholeWordMatch(title, searchTarget);

        if (isWholeWordMatch)
        {
            // Prioritize whole-word match
            targetHandle = hWnd;
            return false; // Stop enumeration - found exact match
        }

        // Check for partial match (fallback)
        if (title.IndexOf(searchTarget, StringComparison.OrdinalIgnoreCase) >= 0)
        {
            // Store as fallback if we haven't found a whole-word match yet
            if (fallbackHandle == IntPtr.Zero)
            {
                fallbackHandle = hWnd;
            }
        }

        // Also try matching process name
        uint processId;
        GetWindowThreadProcessId(hWnd, out processId);

        try
        {
            Process process = Process.GetProcessById((int)processId);
            string processName = process.ProcessName;

            if (IsWholeWordMatch(processName, searchTarget))
            {
                targetHandle = hWnd;
                return false; // Stop enumeration - found exact match
            }

            if (processName.IndexOf(searchTarget, StringComparison.OrdinalIgnoreCase) >= 0)
            {
                if (fallbackHandle == IntPtr.Zero)
                {
                    fallbackHandle = hWnd;
                }
            }
        }
        catch
        {
            // Process may have exited, ignore
        }

        return true; // Continue enumeration
    }

    private static bool IsWholeWordMatch(string text, string searchTerm)
    {
        // Split text into words (separated by spaces)
        string[] words = text.Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);

        foreach (string word in words)
        {
            if (string.Equals(word, searchTerm, StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }

        return false;
    }
    
    private static void FocusWindowFast(IntPtr hWnd)
    {
        // Restore if minimized
        if (IsIconic(hWnd))
        {
            ShowWindow(hWnd, SW_RESTORE);
        }
        
        // Aggressive focus technique to bypass Windows restrictions
        uint currentThread = GetCurrentThreadId();
        IntPtr foregroundWindow = GetForegroundWindow();
        uint foregroundThread = GetWindowThreadProcessId(foregroundWindow, IntPtr.Zero);
        uint targetThread = GetWindowThreadProcessId(hWnd, IntPtr.Zero);
        
        // Attach threads
        if (foregroundThread != currentThread)
            AttachThreadInput(currentThread, foregroundThread, true);
        if (targetThread != currentThread)
            AttachThreadInput(currentThread, targetThread, true);
        
        // Focus
        BringWindowToTop(hWnd);
        SetForegroundWindow(hWnd);
        
        // Detach threads
        if (foregroundThread != currentThread)
            AttachThreadInput(currentThread, foregroundThread, false);
        if (targetThread != currentThread)
            AttachThreadInput(currentThread, targetThread, false);
    }
}

