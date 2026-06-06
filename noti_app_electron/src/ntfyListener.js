const http = require('http');
const https = require('https');

const PLAIN_WINDOW_DENYLIST = new Set(['sglang', 'sglang2', 'sglang3']);

class NtfyListener {
  constructor(server, topic, database, options = {}) {
    this.server = (server || '').replace(/\/+$/, '');
    this.topic = topic;
    this.database = database;
    this.request = null;
    this.reconnectTimer = null;
    this.initialReconnectDelay = options.initialReconnectDelayMs || 1000;
    this.reconnectDelay = this.initialReconnectDelay;
    this.maxReconnectDelay = options.maxReconnectDelayMs || 300000;
    this.running = false;
    this.connected = false;
    this.authBlocked = false;
    this.lastStatusCode = null;
    this.heartbeatTimeout = null;
    this.heartbeatInterval = 90000; // 90s - ntfy sends keepalives ~every 30-45s
    this.authHeader = options.authHeader || process.env.NTFY_AUTH_HEADER || '';
    this.authToken = options.authToken || process.env.NTFY_TOKEN || process.env.NOTI_NTFY_TOKEN || '';
    this.basicUser = options.basicUser || process.env.NTFY_USERNAME || '';
    this.basicPass = options.basicPass || process.env.NTFY_PASSWORD || '';
    this.connectionSeq = 0;
  }

  start() {
    this.running = true;
    this.connected = false;
    this.authBlocked = false;
    this.lastStatusCode = null;
    this.connect();
  }

  stop() {
    this.running = false;
    this.connected = false;
    this.clearHeartbeatTimeout();
    this.clearReconnectTimer();
    this.destroyRequest();
    console.log('[NTFY] Listener stopped');
  }

  getState() {
    return {
      running: this.running,
      connected: this.connected,
      authBlocked: this.authBlocked,
      lastStatusCode: this.lastStatusCode,
    };
  }

  getAuthHeader() {
    if (this.authHeader) return this.authHeader;
    if (this.authToken) return `Bearer ${this.authToken}`;
    if (this.basicUser || this.basicPass) {
      const raw = `${this.basicUser}:${this.basicPass}`;
      return `Basic ${Buffer.from(raw).toString('base64')}`;
    }
    return '';
  }

  hasAuthConfigured() {
    return Boolean(this.getAuthHeader());
  }

  clearReconnectTimer() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  destroyRequest() {
    if (this.request) {
      const connId = this.request.__connId || '?';
      console.log(`[NTFY][conn=${connId}] Destroying request`);
      this.request.destroy();
      this.request = null;
    }
  }

  resetHeartbeatTimeout() {
    this.clearHeartbeatTimeout();
    this.heartbeatTimeout = setTimeout(() => {
      if (!this.running) return;
      console.log('[NTFY] No data received in 90s, connection likely dead. Reconnecting...');
      this.connected = false;
      this.destroyRequest();
      this.scheduleReconnect();
    }, this.heartbeatInterval);
  }

  clearHeartbeatTimeout() {
    if (this.heartbeatTimeout) {
      clearTimeout(this.heartbeatTimeout);
      this.heartbeatTimeout = null;
    }
  }

  parseRetryAfterMs(value) {
    if (!value) return null;

    const raw = Array.isArray(value) ? value[0] : value;
    const numericSeconds = Number(raw);
    if (Number.isFinite(numericSeconds)) {
      return Math.max(0, Math.floor(numericSeconds * 1000));
    }

    const absoluteTime = Date.parse(raw);
    if (Number.isFinite(absoluteTime)) {
      return Math.max(0, absoluteTime - Date.now());
    }

    return null;
  }

  handleNonSuccessStatus(statusCode, headers, body) {
    this.lastStatusCode = statusCode;
    this.connected = false;
    this.clearHeartbeatTimeout();
    this.request = null;

    const bodySnippet = body ? body.trim().slice(0, 300) : '';

    if (statusCode === 401 || statusCode === 403) {
      this.authBlocked = true;
      const reason = this.hasAuthConfigured()
        ? 'Credentials were provided but rejected.'
        : 'No credentials provided for a protected topic.';
      console.error(`[NTFY] Authentication failed (HTTP ${statusCode}). ${reason}`);
      console.error('[NTFY] Auto reconnect paused. Update auth and restart listener/app.');
      if (bodySnippet) {
        console.error(`[NTFY] Response: ${bodySnippet}`);
      }
      return;
    }

    if (statusCode === 429) {
      const retryAfterMs = this.parseRetryAfterMs(headers['retry-after']);
      const delay = retryAfterMs || Math.max(this.reconnectDelay * 2, 60000);
      console.warn(`[NTFY] Rate limited (HTTP 429). Reconnecting in ${delay}ms.`);
      if (bodySnippet) {
        console.warn(`[NTFY] Response: ${bodySnippet}`);
      }
      this.scheduleReconnect(delay);
      return;
    }

    console.error(`[NTFY] Unexpected HTTP status ${statusCode}.`);
    if (bodySnippet) {
      console.error(`[NTFY] Response: ${bodySnippet}`);
    }
    this.scheduleReconnect();
  }

  buildRequestOptions(url) {
    const headers = {
      Accept: 'text/event-stream',
      'Cache-Control': 'no-cache',
      'User-Agent': 'noti-app-electron/1.0',
    };

    const authHeader = this.getAuthHeader();
    if (authHeader) {
      headers.Authorization = authHeader;
    }

    return {
      protocol: url.protocol,
      hostname: url.hostname,
      port: url.port || (url.protocol === 'http:' ? 80 : 443),
      path: `${url.pathname}${url.search}`,
      method: 'GET',
      headers,
    };
  }

  connect() {
    if (!this.running) return;
    if (this.authBlocked) return;

    const url = `${this.server}/${this.topic}/sse`;
    const connId = ++this.connectionSeq;
    console.log(`[NTFY][conn=${connId}] Connecting to: ${url}`);

    const parsedUrl = new URL(url);
    if (parsedUrl.protocol !== 'http:' && parsedUrl.protocol !== 'https:') {
      console.error(`[NTFY] Unsupported protocol: ${parsedUrl.protocol}`);
      this.scheduleReconnect();
      return;
    }

    const requestOptions = this.buildRequestOptions(parsedUrl);
    const httpModule = parsedUrl.protocol === 'http:' ? http : https;
    this.request = httpModule.request(requestOptions, (res) => {
      const statusCode = res.statusCode || 0;
      this.lastStatusCode = statusCode;
      res.__connId = connId;

      if (statusCode !== 200) {
        let body = '';
        res.on('data', (chunk) => {
          if (body.length < 4096) body += chunk.toString();
        });
        res.on('end', () => {
          console.log(`[NTFY][conn=${connId}] Non-success response ended with HTTP ${statusCode}`);
          this.handleNonSuccessStatus(statusCode, res.headers, body);
        });
        res.on('error', (err) => {
          console.error(`[NTFY][conn=${connId}] Response error:`, err.message);
          this.connected = false;
          this.scheduleReconnect();
        });
        return;
      }

      console.log(`[NTFY][conn=${connId}] Connected, status: ${statusCode}`);
      this.connected = true;
      this.reconnectDelay = this.initialReconnectDelay;
      this.resetHeartbeatTimeout();

      let buffer = '';
      res.on('data', (chunk) => {
        this.resetHeartbeatTimeout();
        buffer += chunk.toString();

        const events = buffer.split(/\r?\n\r?\n/);
        buffer = events.pop();

        for (const rawEvent of events) {
          this.handleSseEvent(rawEvent, connId);
        }
      });

      res.on('end', () => {
        console.log(`[NTFY][conn=${connId}] Connection ended`);
        this.connected = false;
        this.clearHeartbeatTimeout();
        this.request = null;
        this.scheduleReconnect();
      });

      res.on('error', (err) => {
        console.error(`[NTFY][conn=${connId}] Response error:`, err.message);
        this.connected = false;
        this.clearHeartbeatTimeout();
        this.request = null;
        this.scheduleReconnect();
      });
    });
    this.request.__connId = connId;

    this.request.on('error', (err) => {
      console.error(`[NTFY][conn=${connId}] Request error:`, err.message);
      this.connected = false;
      this.clearHeartbeatTimeout();
      this.request = null;
      this.scheduleReconnect();
    });

    // Keep SSE connection open indefinitely; liveness is handled by heartbeatTimeout.
    this.request.setTimeout(0);

    this.request.end();
  }

  handleSseEvent(rawEvent, connId) {
    const normalized = rawEvent.replace(/\r/g, '');
    const lines = normalized.split('\n');
    let eventName = '';
    let eventId = '';
    const dataLines = [];

    for (const line of lines) {
      if (line.startsWith(':')) continue;
      if (line.startsWith('event:')) {
        eventName = line.slice(6).trim();
        continue;
      }
      if (line.startsWith('id:')) {
        eventId = line.slice(3).trim();
        continue;
      }
      if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trimStart());
      }
    }

    if (dataLines.length === 0) {
      if (eventName || eventId) {
        console.log(`[NTFY][conn=${connId}] SSE meta event event=${eventName || '-'} id=${eventId || '-'}`);
      }
      return;
    }

    const dataText = dataLines.join('\n');
    console.log(`[NTFY][conn=${connId}] SSE event=${eventName || 'message'} id=${eventId || '-'} bytes=${dataText.length}`);

    try {
      const data = JSON.parse(dataText);
      if (data.message) {
        this.handleMessage(data.message, { connId, eventId, eventName: eventName || 'message' });
      } else {
        console.log(`[NTFY][conn=${connId}] JSON event missing message field`);
      }
    } catch (err) {
      console.log(`[NTFY][conn=${connId}] Ignoring non-JSON SSE payload`);
    }
  }

  scheduleReconnect(delayOverrideMs = null) {
    if (this.running && !this.authBlocked) {
      const baseDelay = delayOverrideMs == null ? this.reconnectDelay : delayOverrideMs;
      const delay = Math.min(Math.max(baseDelay, this.initialReconnectDelay), this.maxReconnectDelay);
      console.log(`[NTFY] Reconnecting in ${delay}ms...`);
      this.clearReconnectTimer();
      this.reconnectTimer = setTimeout(() => {
        this.reconnectTimer = null;
        this.connect();
      }, delay);

      if (delayOverrideMs == null) {
        this.reconnectDelay = Math.min(delay * 2, this.maxReconnectDelay);
      } else {
        this.reconnectDelay = Math.min(Math.max(delay, this.initialReconnectDelay), this.maxReconnectDelay);
      }
    } else if (this.authBlocked) {
      console.warn('[NTFY] Reconnect skipped because listener is paused by auth failure.');
    }
  }

  parseMessage(message) {
    const separatorIndex = message.lastIndexOf(' - ');
    if (separatorIndex < 0) {
      return null;
    }

    const targetPart = message.slice(0, separatorIndex).trim();
    const status = message.slice(separatorIndex + 3).trim();
    if (!targetPart || !status) {
      return null;
    }

    const threadSeparatorIndex = targetPart.indexOf(' | ');
    if (threadSeparatorIndex < 0) {
      return {
        windowName: targetPart,
        threadName: '',
        status,
      };
    }

    const windowName = targetPart.slice(0, threadSeparatorIndex).trim();
    const threadName = targetPart.slice(threadSeparatorIndex + 3).trim();
    if (!windowName || !threadName) {
      return null;
    }

    return {
      windowName,
      threadName,
      status,
    };
  }

  handleMessage(message, meta = {}) {
    const connSuffix = meta.connId ? `[conn=${meta.connId}]` : '';
    const eventSuffix = meta.eventId ? `[event=${meta.eventId}]` : '';
    console.log(`[NTFY]${connSuffix}${eventSuffix} Received: ${message}`);

    const parsed = this.parseMessage(message);
    if (!parsed) {
      console.log(`[NTFY]${connSuffix}${eventSuffix} Invalid message format, expected "window_name - status" or "window_name | thread_name - status"`);
      return;
    }

    if (!parsed.threadName && PLAIN_WINDOW_DENYLIST.has(parsed.windowName)) {
      console.log(`[NTFY]${connSuffix}${eventSuffix} Ignored plain update for denied window: ${parsed.windowName}`);
      return;
    }

    this.database.addOrUpdateWindow(parsed.windowName, parsed.status, parsed.threadName);
    const threadSuffix = parsed.threadName ? ` / ${parsed.threadName}` : '';
    console.log(`[NTFY]${connSuffix}${eventSuffix} Updated: ${parsed.windowName}${threadSuffix} -> ${parsed.status}`);
  }
}

module.exports = NtfyListener;
