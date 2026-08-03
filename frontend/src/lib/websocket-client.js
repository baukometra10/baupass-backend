/**
 * WebSocket Client Library — Real-time communication with auto-reconnection and message queuing
 *
 * Provides:
 * - Automatic connection management
 * - Auto-reconnection with exponential backoff
 * - Message queuing when disconnected
 * - Event subscription system
 * - Heartbeat monitoring
 * - Connection state tracking
 */

class WebSocketClient {
  constructor(url, options = {}) {
    this.url = url || this._getDefaultUrl();
    this.socket = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = options.maxReconnectAttempts || 10;
    this.reconnectDelay = options.reconnectDelay || 1000;
    this.maxReconnectDelay = options.maxReconnectDelay || 30000;
    this.heartbeatInterval = options.heartbeatInterval || 25000;
    this.heartbeatTimeout = options.heartbeatTimeout || 5000;

    this.listeners = {};
    this.messageQueue = [];
    this.isConnecting = false;
    this.isConnected = false;
    this.userId = null;
    this.sessionId = null;
    this.auth = null;

    this.metrics = {
      messagesReceived: 0,
      messagesSent: 0,
      connections: 0,
      reconnections: 0,
      failedConnections: 0,
      bytes_sent: 0,
      bytes_received: 0,
    };

    this.heartbeatTimer = null;
    this.heartbeatCheckTimer = null;
    this.lastHeartbeat = Date.now();
  }

  /**
   * Get default WebSocket URL based on current location
   */
  _getDefaultUrl() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}`;
  }

  /**
   * Connect to WebSocket server
   */
  connect(userId, companyId, role, metadata = {}) {
    if (this.isConnecting || this.isConnected) {
      console.warn('Already connected or connecting');
      return Promise.resolve();
    }

    this.isConnecting = true;
    this.userId = userId;

    const auth = {
      user_id: userId,
      company_id: companyId,
      role: role,
      metadata: metadata,
      timestamp: Date.now(),
    };

    return new Promise((resolve, reject) => {
      try {
        // Use socket.io-client if available, otherwise fallback to native WebSocket
        if (typeof io !== 'undefined') {
          this.socket = io(this.url, {
            auth: auth,
            reconnection: true,
            reconnectionDelay: this.reconnectDelay,
            reconnectionDelayMax: this.maxReconnectDelay,
            reconnectionAttempts: this.maxReconnectAttempts,
          });

          this._setupSocketIOListeners(resolve, reject);
        } else {
          this._connectNativeWebSocket(auth, resolve, reject);
        }
      } catch (error) {
        this.isConnecting = false;
        reject(error);
      }
    });
  }

  /**
   * Setup socket.io event listeners
   */
  _setupSocketIOListeners(resolve, reject) {
    this.socket.on('connect', () => {
      this.isConnecting = false;
      this.isConnected = true;
      this.reconnectAttempts = 0;
      this.metrics.connections++;

      console.log('[WebSocket] Connected:', this.socket.id);
      this._startHeartbeat();
      this._drainMessageQueue();
      this._emit('connected', { sessionId: this.socket.id });

      resolve();
    });

    this.socket.on('connection_confirmed', (data) => {
      this.sessionId = data.session_id;
      console.log('[WebSocket] Connection confirmed:', this.sessionId);
    });

    this.socket.on('disconnect', (reason) => {
      this.isConnected = false;
      console.log('[WebSocket] Disconnected:', reason);
      this._stopHeartbeat();
      this._emit('disconnected', { reason });
    });

    this.socket.on('error', (error) => {
      console.error('[WebSocket] Error:', error);
      this.metrics.failedConnections++;
      this._emit('error', { error });
    });

    this.socket.on('message', (data) => {
      this._handleMessage(data);
    });

    this.socket.on('heartbeat_ack', () => {
      this.lastHeartbeat = Date.now();
    });

    // Listen for any custom event
    this.socket.onAny((eventName, data) => {
      if (!['connect', 'disconnect', 'message'].includes(eventName)) {
        this._emit(eventName, data);
      }
    });
  }

  /**
   * Connect using native WebSocket (fallback)
   */
  _connectNativeWebSocket(auth, resolve, reject) {
    const wsUrl = new URL(this.url);
    wsUrl.protocol = wsUrl.protocol === 'https:' ? 'wss:' : 'ws:';

    try {
      this.socket = new WebSocket(wsUrl.toString());

      this.socket.onopen = () => {
        this.isConnecting = false;
        this.isConnected = true;
        this.reconnectAttempts = 0;
        this.metrics.connections++;

        console.log('[WebSocket] Connected via native WebSocket');

        // Send auth message
        this.send('auth', auth);
        this._startHeartbeat();
        this._drainMessageQueue();
        this._emit('connected', {});

        resolve();
      };

      this.socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this._handleMessage(data);
        } catch (error) {
          console.error('[WebSocket] Parse error:', error);
        }
      };

      this.socket.onerror = (error) => {
        console.error('[WebSocket] Error:', error);
        this.isConnecting = false;
        this.metrics.failedConnections++;
        reject(error);
      };

      this.socket.onclose = () => {
        this.isConnected = false;
        console.log('[WebSocket] Connection closed');
        this._stopHeartbeat();
        this._emit('disconnected', {});
        this._attemptReconnect();
      };
    } catch (error) {
      this.isConnecting = false;
      reject(error);
    }
  }

  /**
   * Handle incoming message
   */
  _handleMessage(data) {
    const msgType = data.type || 'unknown';
    const msgSize = JSON.stringify(data).length;

    this.metrics.messagesReceived++;
    this.metrics.bytes_received += msgSize;

    this._emit(msgType, data);
  }

  /**
   * Send message to server
   */
  send(type, data = {}) {
    const message = {
      type: type,
      timestamp: Date.now(),
      ...data,
    };

    if (!this.isConnected) {
      console.warn('[WebSocket] Not connected, queuing message:', type);
      this.messageQueue.push(message);
      return false;
    }

    try {
      const msgJson = JSON.stringify(message);
      this.metrics.messagesSent++;
      this.metrics.bytes_sent += msgJson.length;

      if (this.socket.emit) {
        // socket.io
        this.socket.emit('message', message);
      } else if (this.socket.send) {
        // native WebSocket
        this.socket.send(msgJson);
      }

      return true;
    } catch (error) {
      console.error('[WebSocket] Send error:', error);
      return false;
    }
  }

  /**
   * Subscribe to event type
   */
  on(eventType, callback) {
    if (!this.listeners[eventType]) {
      this.listeners[eventType] = [];
    }
    this.listeners[eventType].push(callback);

    // Return unsubscribe function
    return () => {
      this.listeners[eventType] = this.listeners[eventType].filter(
        (cb) => cb !== callback
      );
    };
  }

  /**
   * Subscribe to event once
   */
  once(eventType, callback) {
    const unsubscribe = this.on(eventType, (data) => {
      callback(data);
      unsubscribe();
    });
    return unsubscribe;
  }

  /**
   * Emit event to listeners
   */
  _emit(eventType, data) {
    if (this.listeners[eventType]) {
      this.listeners[eventType].forEach((callback) => {
        try {
          callback(data);
        } catch (error) {
          console.error(`[WebSocket] Listener error for ${eventType}:`, error);
        }
      });
    }
  }

  /**
   * Start heartbeat monitoring
   */
  _startHeartbeat() {
    if (this.heartbeatTimer) clearInterval(this.heartbeatTimer);

    this.heartbeatTimer = setInterval(() => {
      if (this.isConnected) {
        this.send('heartbeat', {});

        // Set timeout for heartbeat response
        if (this.heartbeatCheckTimer) clearTimeout(this.heartbeatCheckTimer);
        this.heartbeatCheckTimer = setTimeout(() => {
          if (Date.now() - this.lastHeartbeat > this.heartbeatTimeout) {
            console.warn('[WebSocket] Heartbeat timeout, reconnecting...');
            this.disconnect();
            this._attemptReconnect();
          }
        }, this.heartbeatTimeout);
      }
    }, this.heartbeatInterval);
  }

  /**
   * Stop heartbeat monitoring
   */
  _stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    if (this.heartbeatCheckTimer) {
      clearTimeout(this.heartbeatCheckTimer);
      this.heartbeatCheckTimer = null;
    }
  }

  /**
   * Drain message queue
   */
  _drainMessageQueue() {
    while (this.messageQueue.length > 0) {
      const message = this.messageQueue.shift();
      this.send(message.type, message);
    }
  }

  /**
   * Attempt reconnection with exponential backoff
   */
  _attemptReconnect() {
    if (
      this.isConnected ||
      this.reconnectAttempts >= this.maxReconnectAttempts
    ) {
      if (this.reconnectAttempts >= this.maxReconnectAttempts) {
        console.error('[WebSocket] Max reconnection attempts reached');
        this._emit('reconnect_failed', {});
      }
      return;
    }

    this.reconnectAttempts++;
    this.metrics.reconnections++;

    const delay = Math.min(
      this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
      this.maxReconnectDelay
    );

    console.log(
      `[WebSocket] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`
    );

    setTimeout(() => {
      if (!this.isConnected) {
        this.connect(this.userId, this.auth.company_id, this.auth.role).catch(
          (error) => {
            console.error('[WebSocket] Reconnection failed:', error);
            this._attemptReconnect();
          }
        );
      }
    }, delay);
  }

  /**
   * Disconnect from server
   */
  disconnect() {
    this._stopHeartbeat();

    if (this.socket) {
      if (this.socket.disconnect) {
        this.socket.disconnect();
      } else if (this.socket.close) {
        this.socket.close();
      }
    }

    this.isConnected = false;
    this.isConnecting = false;
    this.sessionId = null;
  }

  /**
   * Get connection status
   */
  getStatus() {
    return {
      isConnected: this.isConnected,
      isConnecting: this.isConnecting,
      sessionId: this.sessionId,
      userId: this.userId,
      reconnectAttempts: this.reconnectAttempts,
      messageQueueSize: this.messageQueue.length,
    };
  }

  /**
   * Get metrics
   */
  getMetrics() {
    return {
      ...this.metrics,
      messageQueueSize: this.messageQueue.length,
      uptime: this.metrics.connections > 0 ? Date.now() : 0,
    };
  }

  /**
   * Clear queue
   */
  clearQueue() {
    const size = this.messageQueue.length;
    this.messageQueue = [];
    return size;
  }
}

// Export for use in different module systems
if (typeof module !== 'undefined' && module.exports) {
  module.exports = WebSocketClient;
}
