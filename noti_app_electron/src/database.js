const initSqlJs = require('sql.js');
const path = require('path');
const fs = require('fs');
const { app } = require('electron');

class Database {
  constructor() {
    this.db = null;
    this.dbPath = null;
  }

  async init() {
    // Initialize sql.js
    const SQL = await initSqlJs();

    // Get user data path for persistent storage
    const userDataPath = app.getPath('userData');
    this.dbPath = path.join(userDataPath, 'noti_windows.db');

    console.log('[DB] Database path:', this.dbPath);

    // Load existing database or create new one
    try {
      if (fs.existsSync(this.dbPath)) {
        const buffer = fs.readFileSync(this.dbPath);
        this.db = new SQL.Database(buffer);
        console.log('[DB] Loaded existing database');
      } else {
        this.db = new SQL.Database();
        console.log('[DB] Created new database');
      }
    } catch (err) {
      console.error('[DB] Error loading database:', err);
      this.db = new SQL.Database();
    }

    this.ensureSchema();

    this.saveToFile();
    console.log('[DB] Database initialized');
  }

  ensureSchema() {
    const tableInfo = this.db.exec("PRAGMA table_info(windows)");
    const hasWindowsTable = tableInfo.length > 0 && tableInfo[0].values.length > 0;

    if (!hasWindowsTable) {
      this.db.run(`
        CREATE TABLE windows (
          window_name TEXT NOT NULL,
          thread_name TEXT NOT NULL DEFAULT '',
          status TEXT DEFAULT 'unknown',
          timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
          status_changed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (window_name, thread_name)
        )
      `);
      console.log('[DB] Created windows table with thread support');
      return;
    }

    const columns = tableInfo[0].values.map((row) => row[1]);
    if (!columns.includes('thread_name')) {
      this.db.run('ALTER TABLE windows RENAME TO windows_legacy');
      this.db.run(`
        CREATE TABLE windows (
          window_name TEXT NOT NULL,
          thread_name TEXT NOT NULL DEFAULT '',
          status TEXT DEFAULT 'unknown',
          timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
          status_changed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (window_name, thread_name)
        )
      `);
      this.db.run(`
        INSERT INTO windows (window_name, thread_name, status, timestamp, status_changed_at)
        SELECT window_name, '', status, timestamp, timestamp
        FROM windows_legacy
      `);
      this.db.run('DROP TABLE windows_legacy');
      console.log('[DB] Migrated windows table to support thread_name');

      return;
    }

    if (!columns.includes('status_changed_at')) {
      this.db.run('ALTER TABLE windows ADD COLUMN status_changed_at DATETIME');
      this.db.run(`
        UPDATE windows
        SET status_changed_at = COALESCE(timestamp, CURRENT_TIMESTAMP)
        WHERE status_changed_at IS NULL
      `);
      console.log('[DB] Added status_changed_at column');
    }
  }

  saveToFile() {
    if (!this.db || !this.dbPath) return;
    try {
      const data = this.db.export();
      const buffer = Buffer.from(data);
      fs.writeFileSync(this.dbPath, buffer);
    } catch (err) {
      console.error('[DB] Error saving database:', err);
    }
  }

  getAllWindows() {
    if (!this.db) return [];
    try {
      const results = this.db.exec(`
        SELECT window_name, thread_name, status, timestamp, status_changed_at
        FROM windows
        ORDER BY timestamp DESC
      `);
      if (results.length === 0) return [];

      const columns = results[0].columns;
      const values = results[0].values;

      return values.map(row => {
        const obj = {};
        columns.forEach((col, i) => obj[col] = row[i]);
        return obj;
      });
    } catch (err) {
      console.error('[DB] Error getting windows:', err);
      return [];
    }
  }

  deletePlainWindows(windowNames = []) {
    if (!this.db || !Array.isArray(windowNames) || windowNames.length === 0) return;
    try {
      const placeholders = windowNames.map(() => '?').join(', ');
      this.db.run(
        `
          DELETE FROM windows
          WHERE thread_name = ''
            AND window_name IN (${placeholders})
        `,
        windowNames
      );
      this.saveToFile();
      console.log(`[DB] Deleted plain rows for: ${windowNames.join(', ')}`);
    } catch (err) {
      console.error('[DB] Error deleting plain windows:', err);
    }
  }

  addOrUpdateWindow(windowName, status, threadName = '') {
    if (!this.db) return;
    try {
      this.db.run(`
        INSERT INTO windows (window_name, thread_name, status, timestamp, status_changed_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(window_name, thread_name) DO UPDATE SET
          status = excluded.status,
          timestamp = CURRENT_TIMESTAMP,
          status_changed_at = CASE
            WHEN windows.status IS excluded.status THEN COALESCE(windows.status_changed_at, CURRENT_TIMESTAMP)
            ELSE CURRENT_TIMESTAMP
          END
      `, [windowName, threadName || '', status]);
      this.saveToFile();
      console.log(`[DB] Updated window: ${windowName}${threadName ? ` / ${threadName}` : ''} -> ${status}`);
    } catch (err) {
      console.error('[DB] Error adding/updating window:', err);
    }
  }

  updateWindowStatus(windowName, threadName, status) {
    if (status === undefined) {
      this.addOrUpdateWindow(windowName, threadName, '');
      return;
    }

    this.addOrUpdateWindow(windowName, status, threadName);
  }

  deleteWindow(windowName, threadName = '') {
    if (!this.db) return;
    try {
      this.db.run(
        'DELETE FROM windows WHERE window_name = ? AND thread_name = ?',
        [windowName, threadName || '']
      );
      this.saveToFile();
      console.log(`[DB] Deleted window: ${windowName}${threadName ? ` / ${threadName}` : ''}`);
    } catch (err) {
      console.error('[DB] Error deleting window:', err);
    }
  }

  getDbHash() {
    if (!this.db) return '';
    try {
      const results = this.db.exec(`
        SELECT window_name, thread_name, status
        FROM windows
        ORDER BY window_name, thread_name
      `);
      return JSON.stringify(results);
    } catch (err) {
      return '';
    }
  }

  close() {
    if (this.db) {
      this.saveToFile();
      this.db.close();
      this.db = null;
    }
  }
}

module.exports = Database;
