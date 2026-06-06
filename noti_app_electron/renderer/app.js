let allWindows = [];
let windows = [];
let selectedIndex = -1;
let toastTimer = null;
let autoPopKeyboardLocked = false;

const STALE_WORKING_AFTER_MS = 60 * 1000;
const STALE_RENDER_INTERVAL_MS = 1000;
const VISIBLE_LIMIT_KEY = 'noti-visible-limit';
const PINNED_WINDOWS_KEY = 'noti-pinned-windows';
const HIDDEN_WINDOWS_KEY = 'noti-hidden-windows';
const PIN_TOP = 'top';
const PIN_BOTTOM = 'bottom';

let visibleLimit = loadVisibleLimit();
let pinModes = loadPinModes();
let hiddenKeys = loadHiddenKeys();
let searchOpen = false;
let searchQuery = '';
let limitEditorOpen = false;

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function getPrimaryLabel(win) {
  return (win.thread_name || '').trim() || win.window_name;
}

function getWindowKey(win) {
  return `${win.window_name || ''}::${win.thread_name || ''}`;
}

function getBaseStatusClass(status) {
  const s = (status || '').toLowerCase().trim();
  if (s === 'addressed') return 'addressed';
  if (s === 'done' || s === 'updated' || s === 'thread_name_updated' || s === 'task_complete' || s === 'task-complete' || s === 'thread_rolled_back') return 'done';
  if (s === 'exec_command_end') return 'cooldown';
  return 'working';
}

function parseDbTimestamp(value) {
  if (!value) return null;
  const raw = String(value).trim();
  const sqliteUtc = raw.match(/^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})$/);
  const parsed = sqliteUtc ? Date.parse(`${sqliteUtc[1]}T${sqliteUtc[2]}Z`) : Date.parse(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

function getStatusClass(win) {
  const baseClass = getBaseStatusClass(win.status);
  if (baseClass !== 'working') return baseClass;

  const statusChangedAt = parseDbTimestamp(win.status_changed_at || win.timestamp);
  if (!statusChangedAt) return baseClass;

  return Date.now() - statusChangedAt >= STALE_WORKING_AFTER_MS ? 'stale-working' : baseClass;
}

function loadVisibleLimit() {
  const raw = localStorage.getItem(VISIBLE_LIMIT_KEY);
  if (raw == null || raw === '') return null;

  const parsed = Number(raw);
  if (!Number.isInteger(parsed) || parsed < 0) return null;
  return parsed;
}

function saveVisibleLimit() {
  if (visibleLimit == null) {
    localStorage.removeItem(VISIBLE_LIMIT_KEY);
    return;
  }
  localStorage.setItem(VISIBLE_LIMIT_KEY, String(visibleLimit));
}

function loadPinModes() {
  try {
    const raw = localStorage.getItem(PINNED_WINDOWS_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    const modes = new Map();

    if (Array.isArray(parsed)) {
      for (const key of parsed) {
        if (typeof key === 'string') modes.set(key, PIN_TOP);
      }
      return modes;
    }

    if (parsed && typeof parsed === 'object') {
      for (const [key, mode] of Object.entries(parsed)) {
        if (typeof key === 'string' && (mode === PIN_TOP || mode === PIN_BOTTOM)) {
          modes.set(key, mode);
        }
      }
    }

    return modes;
  } catch (err) {
    return new Map();
  }
}

function savePinModes() {
  localStorage.setItem(PINNED_WINDOWS_KEY, JSON.stringify(Object.fromEntries([...pinModes.entries()].sort())));
}

function loadHiddenKeys() {
  try {
    const raw = localStorage.getItem(HIDDEN_WINDOWS_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    const hidden = new Map();

    if (Array.isArray(parsed)) {
      for (const key of parsed) {
        if (typeof key === 'string') hidden.set(key, null);
      }
      return hidden;
    }

    if (parsed && typeof parsed === 'object') {
      for (const [key, status] of Object.entries(parsed)) {
        if (typeof key === 'string') hidden.set(key, typeof status === 'string' ? status : null);
      }
    }

    return hidden;
  } catch (err) {
    return new Map();
  }
}

function saveHiddenKeys() {
  localStorage.setItem(HIDDEN_WINDOWS_KEY, JSON.stringify(Object.fromEntries([...hiddenKeys.entries()].sort())));
}

function syncHiddenKeysWithStatuses(windowList) {
  let changed = false;
  const statusByKey = new Map(windowList.map((win) => [getWindowKey(win), String(win.status || '')]));

  for (const [key, hiddenStatus] of hiddenKeys.entries()) {
    if (!statusByKey.has(key)) {
      hiddenKeys.delete(key);
      changed = true;
      continue;
    }

    const currentStatus = statusByKey.get(key);
    if (hiddenStatus == null) {
      hiddenKeys.set(key, currentStatus);
      changed = true;
    } else if (hiddenStatus !== currentStatus) {
      hiddenKeys.delete(key);
      changed = true;
    }
  }

  if (changed) saveHiddenKeys();
}

function isPinned(win) {
  return Boolean(getPinMode(win));
}

function getPinMode(win) {
  return pinModes.get(getWindowKey(win)) || '';
}

function getPinSortGroup(win) {
  const mode = getPinMode(win);
  if (mode === PIN_TOP) return 0;
  if (mode === PIN_BOTTOM) return 2;
  return 1;
}

function isHidden(win) {
  const key = getWindowKey(win);
  if (!hiddenKeys.has(key)) return false;

  const hiddenStatus = hiddenKeys.get(key);
  if (hiddenStatus == null) return true;
  return hiddenStatus === String(win.status || '');
}

function getSearchText(win) {
  return [win.window_name, win.thread_name, win.status].filter(Boolean).join(' ').toLowerCase();
}

function sortWindows(windowList) {
  const statusOrder = {
    done: 0,
    cooldown: 1,
    'stale-working': 2,
    working: 3,
    addressed: 4,
  };

  return [...windowList].sort((a, b) => {
    const aPinGroup = getPinSortGroup(a);
    const bPinGroup = getPinSortGroup(b);
    if (aPinGroup !== bPinGroup) return aPinGroup - bPinGroup;

    const aStatus = getStatusClass(a);
    const bStatus = getStatusClass(b);
    const aOrder = statusOrder[aStatus] ?? 1;
    const bOrder = statusOrder[bStatus] ?? 1;
    if (aOrder !== bOrder) return aOrder - bOrder;

    const nameCompare = String(a.window_name || '').localeCompare(String(b.window_name || ''));
    if (nameCompare !== 0) return nameCompare;
    return String(a.thread_name || '').localeCompare(String(b.thread_name || ''));
  });
}

function getDisplayWindows() {
  const sorted = sortWindows(allWindows);

  if (searchOpen) {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return sorted;
    return sorted.filter((win) => getSearchText(win).includes(query));
  }

  const visibleCandidates = sorted.filter((win) => !isHidden(win));

  if (visibleLimit == null) return visibleCandidates;

  const visible = [];
  let unpinnedCount = 0;
  for (const win of visibleCandidates) {
    if (isPinned(win)) {
      visible.push(win);
      continue;
    }

    if (unpinnedCount < visibleLimit) {
      visible.push(win);
      unpinnedCount += 1;
    }
  }

  return visible;
}

function getHiddenCount() {
  if (searchOpen) return 0;
  return Math.max(0, allWindows.length - windows.length);
}

function refreshDisplay({ preserveSelection = true } = {}) {
  const selectedKey = preserveSelection && windows[selectedIndex] ? getWindowKey(windows[selectedIndex]) : null;
  windows = getDisplayWindows();

  if (selectedKey) {
    const nextIndex = windows.findIndex((win) => getWindowKey(win) === selectedKey);
    selectedIndex = nextIndex >= 0 ? nextIndex : Math.min(selectedIndex, windows.length - 1);
  } else if (selectedIndex >= windows.length) {
    selectedIndex = windows.length - 1;
  }

  if (selectedIndex < 0 && windows.length > 0) {
    selectedIndex = 0;
  }

  render();
  updateControls();
}

function render() {
  const container = document.getElementById('window-list');
  if (!container) return;

  if (windows.length === 0) {
    const message = searchOpen
      ? 'No windows match search'
      : allWindows.length === 0
        ? 'No windows tracked'
        : 'No unpinned windows visible; pinned rows still show here';
    container.innerHTML = `<div class="empty-state">${escapeHtml(message)}</div>`;
    return;
  }

  container.innerHTML = windows.map((win, index) => {
    const statusClass = getStatusClass(win);
    const selectedClass = index === selectedIndex ? 'selected' : '';
    const pinMode = getPinMode(win);
    const pinnedClass = pinMode ? `pinned pinned-${pinMode}` : '';
    const pinBadge = pinMode ? `<span class="pin-badge pin-${pinMode}">${pinMode.toUpperCase()}</span>` : '';

    return `
      <div class="message-bar status-${statusClass} ${selectedClass} ${pinnedClass}"
           data-index="${index}"
           data-name="${escapeHtml(win.window_name)}"
           data-thread="${escapeHtml(win.thread_name || '')}">
        <div class="name-stack">
          <span class="window-name">${escapeHtml(getPrimaryLabel(win))}</span>
          ${win.thread_name ? `<span class="window-subtitle">${escapeHtml(win.window_name)}</span>` : ''}
        </div>
        <div class="badge-stack">
          ${pinBadge}
          <span class="status-badge ${statusClass}">${escapeHtml(win.status || 'unknown')}</span>
        </div>
      </div>
    `;
  }).join('');
}

function updateSelection() {
  document.querySelectorAll('.message-bar').forEach((bar, index) => {
    bar.classList.toggle('selected', index === selectedIndex);
  });

  const selected = document.querySelector('.message-bar.selected');
  if (selected) {
    selected.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }
  updateControls();
}

function updateControls() {
  const limitButton = document.getElementById('limit-button');
  if (limitButton) {
    limitButton.textContent = visibleLimit == null ? 'Limit: All' : `Limit: ${visibleLimit}`;
    limitButton.title = `${windows.length}/${allWindows.length} visible${getHiddenCount() ? `, ${getHiddenCount()} hidden` : ''}`;
  }

  const pinButton = document.getElementById('pin-button');
  if (pinButton) {
    const selected = windows[selectedIndex];
    const mode = selected ? getPinMode(selected) : '';
    pinButton.disabled = !selected;
    pinButton.textContent = mode === PIN_TOP ? 'Pin Bottom' : mode === PIN_BOTTOM ? 'Unpin' : 'Pin Top';
  }

  const searchPanel = document.getElementById('search-panel');
  if (searchPanel) {
    searchPanel.classList.toggle('visible', searchOpen);
  }

  const limitPanel = document.getElementById('limit-panel');
  if (limitPanel) {
    limitPanel.classList.toggle('visible', limitEditorOpen);
  }

  const limitInput = document.getElementById('limit-input');
  if (limitInput && document.activeElement !== limitInput) {
    limitInput.value = visibleLimit == null ? '' : String(visibleLimit);
  }

  const searchInput = document.getElementById('search-input');
  if (searchInput && searchInput.value !== searchQuery) {
    searchInput.value = searchQuery;
  }

  const searchSummary = document.getElementById('search-summary');
  if (searchSummary) {
    searchSummary.textContent = searchOpen
      ? `${windows.length}/${allWindows.length}`
      : getHiddenCount()
        ? `${getHiddenCount()} hidden`
        : '';
  }
}

function showToast(message) {
  const toast = document.getElementById('toast');
  if (!toast) return;

  if (toastTimer) {
    clearTimeout(toastTimer);
  }

  toast.textContent = message;
  toast.classList.add('visible');
  toastTimer = setTimeout(() => {
    toast.classList.remove('visible');
    toastTimer = null;
  }, 1800);
}

function lockAutoPopKeyboard() {
  autoPopKeyboardLocked = true;
}

function unlockAutoPopKeyboard() {
  autoPopKeyboardLocked = false;
}

function focusSelectedWindow() {
  if (selectedIndex >= 0 && selectedIndex < windows.length) {
    window.api.focusWindow(windows[selectedIndex].window_name);
    window.api.hideWindow('enter-focus-window');
  }
}

function deleteSelectedWindow() {
  if (selectedIndex >= 0 && selectedIndex < windows.length) {
    const win = windows[selectedIndex];
    const key = getWindowKey(win);
    if (pinModes.delete(key)) {
      savePinModes();
    }
    hiddenKeys.set(key, String(win.status || ''));
    saveHiddenKeys();
    showToast('Window hidden');
    refreshDisplay({ preserveSelection: false });
  }
}

function markSelectedAddressed() {
  if (selectedIndex >= 0 && selectedIndex < windows.length) {
    const win = windows[selectedIndex];
    window.api.updateStatus(win.window_name, win.thread_name || '', 'addressed');
  }
}

function toggleSelectedPin() {
  if (selectedIndex < 0 || selectedIndex >= windows.length) return;

  const win = windows[selectedIndex];
  const key = getWindowKey(win);
  const currentMode = pinModes.get(key) || '';

  if (currentMode === PIN_TOP) {
    pinModes.set(key, PIN_BOTTOM);
    hiddenKeys.delete(key);
    saveHiddenKeys();
    showToast('Window pinned to bottom');
  } else if (currentMode === PIN_BOTTOM) {
    pinModes.delete(key);
    showToast('Window unpinned');
  } else {
    pinModes.set(key, PIN_TOP);
    hiddenKeys.delete(key);
    saveHiddenKeys();
    showToast('Window pinned to top');
  }

  savePinModes();
  refreshDisplay();
}

function applyVisibleLimitValue(value) {
  const trimmed = String(value || '').trim();
  if (!trimmed) {
    visibleLimit = null;
    saveVisibleLimit();
    closeLimitEditor();
    refreshDisplay();
    showToast('Limit set to all');
    return;
  }

  const parsed = Number(trimmed);
  if (!Number.isInteger(parsed) || parsed < 0) {
    showToast('Limit must be a non-negative integer');
    return;
  }

  visibleLimit = parsed;
  saveVisibleLimit();
  closeLimitEditor();
  refreshDisplay();
  showToast(`Limit set to ${visibleLimit}`);
}

function openLimitEditor() {
  limitEditorOpen = true;
  updateControls();

  const input = document.getElementById('limit-input');
  if (input) {
    input.value = visibleLimit == null ? '' : String(visibleLimit);
    input.focus();
    input.select();
  }
}

function closeLimitEditor() {
  limitEditorOpen = false;
  updateControls();
}

function applyVisibleLimitFromEditor() {
  const input = document.getElementById('limit-input');
  applyVisibleLimitValue(input ? input.value : '');
}

function openSearch() {
  searchOpen = true;
  refreshDisplay({ preserveSelection: false });
  const input = document.getElementById('search-input');
  if (input) {
    input.focus();
    input.select();
  }
}

function closeSearch() {
  searchOpen = false;
  searchQuery = '';
  refreshDisplay({ preserveSelection: false });
}

function handleLimitInputKey(event) {
  switch (event.key) {
    case 'Escape':
      event.preventDefault();
      closeLimitEditor();
      break;
    case 'Enter':
      event.preventDefault();
      applyVisibleLimitFromEditor();
      break;
    default:
      break;
  }
}

function handleSearchInputKey(event) {
  switch (event.key) {
    case 'Escape':
      event.preventDefault();
      closeSearch();
      break;
    case 'ArrowDown':
      event.preventDefault();
      if (windows.length === 0) return;
      selectedIndex = Math.min(selectedIndex + 1, windows.length - 1);
      if (selectedIndex < 0) selectedIndex = 0;
      updateSelection();
      break;
    case 'ArrowUp':
      event.preventDefault();
      if (windows.length === 0) return;
      selectedIndex = Math.max(selectedIndex - 1, 0);
      updateSelection();
      break;
    case 'Enter':
      event.preventDefault();
      focusSelectedWindow();
      break;
    default:
      break;
  }
}

document.addEventListener('keydown', (event) => {
  const container = document.getElementById('window-list');
  const key = event.key.toLowerCase();
  const target = event.target;
  const isSearchInput = target && target.id === 'search-input';
  const isLimitInput = target && target.id === 'limit-input';

  if ((event.ctrlKey || event.metaKey) && key === 'f') {
    event.preventDefault();
    openSearch();
    return;
  }

  if (isSearchInput) {
    handleSearchInputKey(event);
    return;
  }

  if (isLimitInput) {
    handleLimitInputKey(event);
    return;
  }

  if ((event.ctrlKey || event.metaKey) && key === 'n') {
    event.preventDefault();
    openLimitEditor();
    return;
  }

  if (autoPopKeyboardLocked) {
    const intentionalKeys = new Set(['Tab', 'ArrowDown', 'ArrowUp', 'Enter', 'PageUp', 'PageDown', 'Home', 'End', 'Escape']);
    if (event.key === 'Escape') {
      event.preventDefault();
      unlockAutoPopKeyboard();
      window.api.hideWindow('escape-after-auto-pop');
      return;
    }

    if (!intentionalKeys.has(event.key)) {
      event.preventDefault();
      event.stopPropagation();
      return;
    }

    unlockAutoPopKeyboard();
  }

  switch (event.key) {
    case 'Tab':
      event.preventDefault();
      if (windows.length === 0) return;
      selectedIndex = (selectedIndex + 1) % windows.length;
      updateSelection();
      break;

    case 'ArrowDown':
      event.preventDefault();
      if (windows.length === 0) return;
      selectedIndex = Math.min(selectedIndex + 1, windows.length - 1);
      if (selectedIndex < 0) selectedIndex = 0;
      updateSelection();
      break;

    case 'ArrowUp':
      event.preventDefault();
      if (windows.length === 0) return;
      selectedIndex = Math.max(selectedIndex - 1, 0);
      updateSelection();
      break;

    case 'Enter':
      event.preventDefault();
      focusSelectedWindow();
      break;

    case 'PageUp':
      event.preventDefault();
      if (container) container.scrollBy({ top: -100, behavior: 'smooth' });
      break;

    case 'PageDown':
      event.preventDefault();
      if (container) container.scrollBy({ top: 100, behavior: 'smooth' });
      break;

    case 'Home':
      event.preventDefault();
      if (windows.length === 0) return;
      selectedIndex = 0;
      updateSelection();
      if (container) container.scrollTo({ top: 0, behavior: 'smooth' });
      break;

    case 'End':
      event.preventDefault();
      if (windows.length === 0) return;
      selectedIndex = windows.length - 1;
      updateSelection();
      if (container) container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
      break;

    case 'Delete':
      event.preventDefault();
      deleteSelectedWindow();
      break;

    case 'a':
    case 'A':
      event.preventDefault();
      markSelectedAddressed();
      break;

    case 'p':
    case 'P':
      event.preventDefault();
      toggleSelectedPin();
      break;

    case 'Escape':
      if (searchOpen) {
        event.preventDefault();
        closeSearch();
      } else if (limitEditorOpen) {
        event.preventDefault();
        closeLimitEditor();
      }
      break;

    default:
      if (event.key.length === 1 && event.key.match(/[b-zB-Z]/)) {
        event.preventDefault();
        window.api.hideWindow(`letter-shortcut:${event.key}`);
      }
      break;
  }
});

window.api.onWindowsUpdated((updatedWindows) => {
  allWindows = updatedWindows;
  syncHiddenKeysWithStatuses(allWindows);
  refreshDisplay();
});

window.api.onAutoPopToggled((state) => {
  showToast(`Auto-pop ${state.enabled ? 'enabled' : 'disabled'}`);
});

window.api.onAutoPopShown(() => {
  lockAutoPopKeyboard();
});

if (window.api.onOpenLimitEditor) {
  window.api.onOpenLimitEditor(() => {
    openLimitEditor();
  });
}

window.api.getWindows().then((initialWindows) => {
  allWindows = initialWindows;
  syncHiddenKeysWithStatuses(allWindows);
  refreshDisplay({ preserveSelection: false });
});

setInterval(() => {
  if (allWindows.some((win) => getBaseStatusClass(win.status) === 'working')) {
    refreshDisplay();
  }
}, STALE_RENDER_INTERVAL_MS);

document.addEventListener('DOMContentLoaded', () => {
  const container = document.getElementById('window-list');
  if (container) {
    container.addEventListener('pointerdown', unlockAutoPopKeyboard);
    container.addEventListener('wheel', (event) => {
      event.preventDefault();
      container.scrollBy({ top: event.deltaY, behavior: 'smooth' });
    }, { passive: false });
  }

  const limitButton = document.getElementById('limit-button');
  if (limitButton) {
    limitButton.addEventListener('click', openLimitEditor);
  }

  const limitInput = document.getElementById('limit-input');
  if (limitInput) {
    limitInput.addEventListener('keydown', handleLimitInputKey);
  }

  const limitApply = document.getElementById('limit-apply');
  if (limitApply) {
    limitApply.addEventListener('click', applyVisibleLimitFromEditor);
  }

  const limitAll = document.getElementById('limit-all');
  if (limitAll) {
    limitAll.addEventListener('click', () => applyVisibleLimitValue(''));
  }

  const limitClose = document.getElementById('limit-close');
  if (limitClose) {
    limitClose.addEventListener('click', closeLimitEditor);
  }

  const pinButton = document.getElementById('pin-button');
  if (pinButton) {
    pinButton.addEventListener('click', toggleSelectedPin);
  }

  const searchButton = document.getElementById('search-button');
  if (searchButton) {
    searchButton.addEventListener('click', openSearch);
  }

  const searchInput = document.getElementById('search-input');
  if (searchInput) {
    searchInput.addEventListener('input', (event) => {
      searchQuery = event.target.value;
      refreshDisplay({ preserveSelection: false });
    });
  }

  const searchClose = document.getElementById('search-close');
  if (searchClose) {
    searchClose.addEventListener('click', closeSearch);
  }

  updateControls();
});

console.log('[RENDERER] Noti App renderer initialized');
