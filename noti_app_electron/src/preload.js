const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods to renderer
contextBridge.exposeInMainWorld('api', {
  // Get all windows from database
  getWindows: () => ipcRenderer.invoke('get-windows'),

  // Update window status
  updateStatus: (windowName, status) => ipcRenderer.invoke('update-status', windowName, status),

  // Delete window
  deleteWindow: (windowName) => ipcRenderer.invoke('delete-window', windowName),

  // Focus window via focus: protocol
  focusWindow: (windowName) => ipcRenderer.invoke('focus-window', windowName),

  // Hide the app window
  hideWindow: () => ipcRenderer.send('hide-window'),

  // Listen for window updates from main process
  onWindowsUpdated: (callback) => {
    ipcRenderer.on('windows-updated', (event, windows) => callback(windows));
  }
});
