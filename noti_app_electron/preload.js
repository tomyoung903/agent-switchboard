const { contextBridge, ipcRenderer } = require('electron');

// Expose secure API to renderer
contextBridge.exposeInMainWorld('api', {
  // Get all windows
  getWindows: () => ipcRenderer.invoke('get-windows'),

  // Update window status
  updateStatus: (windowName, threadName, status) => ipcRenderer.invoke('update-status', windowName, threadName, status),

  // Delete window
  deleteWindow: (windowName, threadName) => ipcRenderer.invoke('delete-window', windowName, threadName),

  // Focus a window via focus: protocol
  focusWindow: (windowName) => ipcRenderer.invoke('focus-window', windowName),

  // Hide the app window
  hideWindow: (reason) => ipcRenderer.send('hide-window', reason),

  // Listen for window updates
  onWindowsUpdated: (callback) => {
    ipcRenderer.on('windows-updated', (event, windows) => callback(windows));
  },

  // Listen for auto-pop shortcut changes
  onAutoPopToggled: (callback) => {
    ipcRenderer.on('auto-pop-toggled', (event, state) => callback(state));
  },

  // Listen for auto-pop show events so the renderer can ignore accidental typing.
  onAutoPopShown: (callback) => {
    ipcRenderer.on('auto-pop-shown', (event, state) => callback(state));
  },

  // Listen for main-process request to open the visible limit editor.
  onOpenLimitEditor: (callback) => {
    ipcRenderer.on('open-limit-editor', () => callback());
  }
});
