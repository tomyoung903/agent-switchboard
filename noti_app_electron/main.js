const { app, BrowserWindow, ipcMain, Tray, Menu, globalShortcut, screen, nativeImage } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn, exec } = require('child_process');
const Database = require('./src/database');
const NtfyListener = require('./src/ntfyListener');

if (require('electron-squirrel-startup')) {
  app.quit();
}

// Configuration
const CONFIG = {
  windowWidth: 304,
  windowHeight: 200,
  minWindowWidth: 220,
  minWindowHeight: 140,
  spawnX: 1500,
  spawnY: -1100,
  ntfyServer: process.env.NTFY_SERVER || 'https://ntfy.sh',
  ntfyTopic: process.env.NTFY_TOPIC || 'agent_switchboard_demo_topic_change_me',
  ntfyAuthHeader: process.env.NTFY_AUTH_HEADER || '',
  ntfyAuthToken: process.env.NTFY_TOKEN || process.env.NOTI_NTFY_TOKEN || '',
  ntfyUsername: process.env.NTFY_USERNAME || '',
  ntfyPassword: process.env.NTFY_PASSWORD || '',
  dbPollInterval: 500,
  listenerHealthCheckInterval: 30000,
  autoPopOnDone: process.env.AUTO_POP_ON_DONE !== '0',
  autoPopFocus: process.env.AUTO_POP_FOCUS === '1',
  donePopupCooldownMs: Number.isFinite(Number(process.env.DONE_POPUP_COOLDOWN_MS))
    ? Math.max(0, Number(process.env.DONE_POPUP_COOLDOWN_MS))
    : 1500
};

const PLAIN_WINDOW_DENYLIST = ['sglang', 'sglang2', 'sglang3'];

let mainWindow = null;
let tray = null;
let database = null;
let ntfyListener = null;
let dbMonitorInterval = null;
let lastDbHash = null;
let windowStatePath = null;
let saveBoundsTimer = null;
let statusClassByWindowKey = new Map();
let statusCacheSeeded = false;
let lastDonePopupAt = 0;
let autoPopOnDoneEnabled = CONFIG.autoPopOnDone;
let autoPopHoldingTop = false;

function getStatusClass(status) {
  const s = (status || '').toLowerCase().trim();
  if (s === 'addressed') return 'addressed';
  if (s === 'done' || s === 'updated' || s === 'thread_name_updated' || s === 'task_complete' || s === 'task-complete' || s === 'thread_rolled_back') return 'done';
  if (s === 'exec_command_end') return 'cooldown';
  return 'working';
}

function getWindowKey(win) {
  return `${win.window_name || ''}::${win.thread_name || ''}`;
}

function getWindowStatePath() {
  if (!windowStatePath) {
    windowStatePath = path.join(app.getPath('userData'), 'noti_window_state.json');
  }
  return windowStatePath;
}

function loadSavedBounds() {
  try {
    const raw = fs.readFileSync(getWindowStatePath(), 'utf8');
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return null;

    const x = Number(parsed.x);
    const y = Number(parsed.y);
    const width = Number(parsed.width);
    const height = Number(parsed.height);
    if (![x, y, width, height].every(Number.isFinite)) return null;

    return {
      x: Math.round(x),
      y: Math.round(y),
      width: Math.max(CONFIG.minWindowWidth, Math.round(width)),
      height: Math.max(CONFIG.minWindowHeight, Math.round(height)),
    };
  } catch (err) {
    return null;
  }
}

function saveWindowBounds() {
  if (!mainWindow || mainWindow.isDestroyed()) return;

  try {
    const bounds = mainWindow.getBounds();
    const payload = {
      x: bounds.x,
      y: bounds.y,
      width: bounds.width,
      height: bounds.height,
      updatedAt: new Date().toISOString(),
    };
    fs.writeFileSync(getWindowStatePath(), JSON.stringify(payload, null, 2), 'utf8');
  } catch (err) {
    console.error('[APP] Failed to persist window bounds:', err.message);
  }
}

function scheduleSaveWindowBounds() {
  if (saveBoundsTimer) {
    clearTimeout(saveBoundsTimer);
  }
  saveBoundsTimer = setTimeout(() => {
    saveBoundsTimer = null;
    saveWindowBounds();
  }, 150);
}

// Create main window
function createWindow() {
  const savedBounds = loadSavedBounds();
  const initialBounds = savedBounds || {
    width: CONFIG.windowWidth,
    height: CONFIG.windowHeight,
    x: CONFIG.spawnX,
    y: CONFIG.spawnY,
  };

  mainWindow = new BrowserWindow({
    width: initialBounds.width,
    height: initialBounds.height,
    x: initialBounds.x,
    y: initialBounds.y,
    minWidth: CONFIG.minWindowWidth,
    minHeight: CONFIG.minWindowHeight,
    resizable: true,
    movable: true,
    frame: false,
    transparent: false,
    skipTaskbar: true,
    show: false,
    alwaysOnTop: false,
    backgroundColor: '#1e1e2e',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  mainWindow.on('close', (event) => {
    if (!app.isQuitting) {
      event.preventDefault();
      hideWindow('close-event');
    }
  });

  mainWindow.on('blur', () => {
    // Optional: hide on blur
  });

  mainWindow.on('move', scheduleSaveWindowBounds);
  mainWindow.on('resize', scheduleSaveWindowBounds);

  console.log('[APP] Window created');
}

// Create system tray
function createTray() {
  // Create a blue circle icon
  const size = 32;
  const canvas = Buffer.alloc(size * size * 4);
  const centerX = size / 2;
  const centerY = size / 2;
  const radius = size / 2 - 2;

  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const idx = (y * size + x) * 4;
      const dist = Math.sqrt((x - centerX) ** 2 + (y - centerY) ** 2);

      if (dist <= radius) {
        canvas[idx] = 100;     // B
        canvas[idx + 1] = 149; // G
        canvas[idx + 2] = 237; // R (cornflower blue)
        canvas[idx + 3] = 255; // A
      } else {
        canvas[idx] = 0;
        canvas[idx + 1] = 0;
        canvas[idx + 2] = 0;
        canvas[idx + 3] = 0;
      }
    }
  }

  const icon = nativeImage.createFromBuffer(canvas, { width: size, height: size });
  tray = new Tray(icon);

  const contextMenu = Menu.buildFromTemplate([
    { label: 'Show', click: () => showWindow({ reason: 'tray-menu' }) },
    { label: 'Hide', click: () => hideWindow('tray-menu') },
    { type: 'separator' },
    { label: 'Exit', click: () => quitApp() }
  ]);

  tray.setToolTip('Noti App');
  tray.setContextMenu(contextMenu);

  tray.on('click', () => {
    if (mainWindow.isVisible()) {
      hideWindow('tray-click');
    } else {
      showWindow({ reason: 'tray-click' });
    }
  });

  console.log('[TRAY] System tray created');
}

// Window visibility functions
function ensureWindowOnScreen() {
  if (!mainWindow) return;

  const bounds = mainWindow.getBounds();
  const displays = screen.getAllDisplays();
  const isOnScreen = displays.some((display) => {
    const area = display.workArea;
    const overlapsX = bounds.x < area.x + area.width && (bounds.x + bounds.width) > area.x;
    const overlapsY = bounds.y < area.y + area.height && (bounds.y + bounds.height) > area.y;
    return overlapsX && overlapsY;
  });

  if (!isOnScreen) {
    const primaryArea = screen.getPrimaryDisplay().workArea;
    const safeX = primaryArea.x + Math.max(0, Math.floor((primaryArea.width - bounds.width) / 2));
    const safeY = primaryArea.y + Math.max(0, Math.floor((primaryArea.height - bounds.height) / 2));
    mainWindow.setPosition(safeX, safeY);
    console.log(`[APP] Window moved on-screen to (${safeX}, ${safeY})`);
  }
}

function showWindow({ focus = true, reason = 'manual' } = {}) {
  if (mainWindow) {
    ensureWindowOnScreen();
    if (mainWindow.isMinimized()) {
      mainWindow.restore();
    }
    if (!focus && typeof mainWindow.showInactive === 'function') {
      mainWindow.showInactive();
    } else {
      mainWindow.show();
    }
    if (focus) {
      mainWindow.focus();
    }
    console.log(`[APP] Window shown (${reason}, focus=${focus})`);
  }
}

function popWindowForDoneTransition(win, transitionCount) {
  if (!mainWindow || mainWindow.isDestroyed()) return;

  const now = Date.now();
  if (now - lastDonePopupAt < CONFIG.donePopupCooldownMs) {
    console.log(`[APP] Done popup suppressed by cooldown (${transitionCount} transition(s))`);
    return;
  }

  lastDonePopupAt = now;
  autoPopHoldingTop = true;
  mainWindow.setAlwaysOnTop(true);
  showWindow({ focus: CONFIG.autoPopFocus, reason: 'auto-pop' });
  if (typeof mainWindow.moveTop === 'function') {
    mainWindow.moveTop();
  }
  mainWindow.webContents.send('auto-pop-shown', { focus: CONFIG.autoPopFocus });

  const label = win.thread_name ? `${win.window_name} / ${win.thread_name}` : win.window_name;
  console.log(`[APP] Auto-popped for done status: ${label} -> ${win.status}`);
}

function handleDoneTransitions(windows) {
  const nextStatusClassByWindowKey = new Map();
  const doneTransitions = [];

  for (const win of windows) {
    const key = getWindowKey(win);
    const nextClass = getStatusClass(win.status);
    const previousClass = statusClassByWindowKey.get(key);

    if (
      autoPopOnDoneEnabled &&
      statusCacheSeeded &&
      nextClass === 'done' &&
      previousClass !== 'done'
    ) {
      doneTransitions.push(win);
    }

    nextStatusClassByWindowKey.set(key, nextClass);
  }

  statusClassByWindowKey = nextStatusClassByWindowKey;
  if (!statusCacheSeeded) {
    statusCacheSeeded = true;
    console.log('[APP] Done-popup status cache seeded');
    return;
  }

  if (doneTransitions.length > 0) {
    popWindowForDoneTransition(doneTransitions[0], doneTransitions.length);
  }
}

function toggleAutoPopOnDone() {
  autoPopOnDoneEnabled = !autoPopOnDoneEnabled;
  console.log(`[HOTKEY] Auto-pop on done ${autoPopOnDoneEnabled ? 'enabled' : 'disabled'}`);
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('auto-pop-toggled', { enabled: autoPopOnDoneEnabled });
  }
}

function openLimitEditor() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  showWindow({ reason: 'limit-hotkey' });
  mainWindow.webContents.send('open-limit-editor');
}

function hideWindow(reason = 'unknown') {
  if (mainWindow) {
    if (autoPopHoldingTop) {
      autoPopHoldingTop = false;
      mainWindow.setAlwaysOnTop(false);
    }
    mainWindow.hide();
    console.log(`[APP] Window hidden (${reason})`);
  }
}

function toggleWindow() {
  if (mainWindow) {
    if (mainWindow.isVisible()) {
      hideWindow('toggle-hotkey');
    } else {
      showWindow({ reason: 'toggle-hotkey' });
    }
  }
}

// Focus first done window
async function focusFirstDoneWindow() {
  try {
    const windows = database.getAllWindows();
    const doneWindow = windows.find(w => getStatusClass(w.status) === 'done');

    if (doneWindow) {
      const focusUrl = `focus:${doneWindow.window_name}`;
      exec(`powershell.exe -Command "Start-Process '${focusUrl}'"`, { windowsHide: true });
      console.log(`[HOTKEY] Alt+X - Focused: ${doneWindow.window_name}`);
      return true;
    }

    console.log('[HOTKEY] Alt+X - No done windows found');
    return false;
  } catch (err) {
    console.error('[HOTKEY] Alt+X error:', err);
    return false;
  }
}

// Register global hotkeys
function registerHotkeyWithFallback(label, accelerators, handler) {
  for (const accelerator of accelerators) {
    const registered = globalShortcut.register(accelerator, handler);
    if (registered) {
      console.log(`[HOTKEY] Registered ${label}: ${accelerator}`);
      return accelerator;
    }
    console.warn(`[HOTKEY] Failed to register ${label}: ${accelerator}`);
  }

  console.error(`[HOTKEY] Could not register ${label}`);
  return null;
}

function registerHotkeys() {
  const toggleAccelerator = registerHotkeyWithFallback(
    'toggle window',
    ['CommandOrControl+,', 'CommandOrControl+.'],
    () => {
    console.log('[HOTKEY] Ctrl+, pressed');
    toggleWindow();
    }
  );

  const focusAccelerator = registerHotkeyWithFallback(
    'focus first done window',
    ['Alt+X'],
    async () => {
    console.log('[HOTKEY] Alt+X pressed');
    const focused = await focusFirstDoneWindow();
    if (!focused && !mainWindow.isVisible()) {
      showWindow({ reason: 'focus-hotkey-fallback' });
    }
    }
  );

  const autoPopAccelerator = registerHotkeyWithFallback(
    'toggle auto-pop on done',
    ['Alt+Z', 'Alt+Shift+X'],
    () => {
    toggleAutoPopOnDone();
    }
  );

  const limitAccelerator = registerHotkeyWithFallback(
    'open visible limit editor',
    ['CommandOrControl+N'],
    () => {
    console.log('[HOTKEY] Ctrl+N pressed');
    openLimitEditor();
    }
  );

  console.log(
    `[HOTKEY] Global hotkeys ready (toggle=${toggleAccelerator || 'none'}, focus=${focusAccelerator || 'none'}, autoPop=${autoPopAccelerator || 'none'}, limit=${limitAccelerator || 'none'})`
  );
}

// Database monitoring
function startDbMonitor() {
  dbMonitorInterval = setInterval(() => {
    try {
      const currentHash = database.getDbHash();
      if (currentHash !== lastDbHash) {
        lastDbHash = currentHash;
        if (mainWindow && mainWindow.webContents) {
          const windows = database.getAllWindows();
          mainWindow.webContents.send('windows-updated', windows);
          handleDoneTransitions(windows);
          console.log('[MONITOR] Database changed, UI updated');
        }
      }
    } catch (err) {
      console.error('[MONITOR] Error:', err);
    }
  }, CONFIG.dbPollInterval);

  console.log('[MONITOR] Database monitor started');
}

// Quit app
function quitApp() {
  app.isQuitting = true;

  saveWindowBounds();
  if (saveBoundsTimer) {
    clearTimeout(saveBoundsTimer);
    saveBoundsTimer = null;
  }

  if (ntfyListener) {
    ntfyListener.stop();
  }

  if (dbMonitorInterval) {
    clearInterval(dbMonitorInterval);
  }

  globalShortcut.unregisterAll();

  app.quit();
}

// IPC handlers
function setupIpcHandlers() {
  ipcMain.handle('get-windows', () => {
    return database.getAllWindows();
  });

  ipcMain.handle('update-status', (event, windowName, threadName, status) => {
    database.updateWindowStatus(windowName, threadName || '', status);
    return true;
  });

  ipcMain.handle('delete-window', (event, windowName, threadName) => {
    database.deleteWindow(windowName, threadName || '');
    return true;
  });

  ipcMain.handle('focus-window', (event, windowName) => {
    const focusUrl = `focus:${windowName}`;
    exec(`powershell.exe -Command "Start-Process '${focusUrl}'"`, { windowsHide: true });
    return true;
  });

  ipcMain.on('hide-window', (event, reason) => {
    hideWindow(reason || 'renderer');
  });

  console.log('[APP] IPC handlers registered');
}

// App lifecycle
app.whenReady().then(async () => {
  // Initialize database (async for sql.js)
  database = new Database();
  await database.init();
  database.deletePlainWindows(PLAIN_WINDOW_DENYLIST);

  // Create window and tray
  createWindow();
  createTray();

  // Setup IPC
  setupIpcHandlers();

  // Register hotkeys
  registerHotkeys();

  // Start database monitor
  startDbMonitor();

  // Start ntfy listener
  ntfyListener = new NtfyListener(CONFIG.ntfyServer, CONFIG.ntfyTopic, database, {
    authHeader: CONFIG.ntfyAuthHeader,
    authToken: CONFIG.ntfyAuthToken,
    basicUser: CONFIG.ntfyUsername,
    basicPass: CONFIG.ntfyPassword,
    maxReconnectDelayMs: 300000,
  });

  if (CONFIG.ntfyAuthHeader || CONFIG.ntfyAuthToken || CONFIG.ntfyUsername || CONFIG.ntfyPassword) {
    console.log('[NTFY] Auth is configured for listener.');
  } else {
    console.warn('[NTFY] No auth configured. Protected topics will return 401/403.');
  }

  ntfyListener.start();

  // Send initial data
  mainWindow.webContents.on('did-finish-load', () => {
    const windows = database.getAllWindows();
    mainWindow.webContents.send('windows-updated', windows);
  });

  console.log('[APP] Application ready');
});

app.on('window-all-closed', () => {
  // Don't quit on window close, keep in tray
});

app.on('before-quit', () => {
  app.isQuitting = true;
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
});
