/**
 * BauPass ops live feed — Socket.IO (preferred) with SSE fallback.
 */
(function (global) {
  function formatEventLine(evt) {
    const type = evt.type || evt.event_type || "event";
    const p = evt.payload || {};
    if (type.startsWith("access") || type === "access") {
      const worker = p.worker_name || p.worker || p.workerId || "?";
      const gate = p.gate || p.gate_id || "—";
      const action = p.action || p.direction || "";
      return {
        html: `<strong>${worker}</strong> ${action} @ ${gate}`,
        at: evt.created_at || evt.at || p.at || "",
      };
    }
    if (type === "inbox.changed") {
      return {
        html: "<strong>Posteingang</strong> aktualisiert",
        at: evt.created_at || "",
      };
    }
    if (type === "push_sent") {
      const ch = (evt.channels || p.channels || []).join("+") || "push";
      return {
        html: `<strong>Push</strong> → ${p.workerId || evt.workerId || "?"} (${ch})`,
        at: evt.created_at || "",
      };
    }
    return {
      html: `<strong>${type}</strong> ${JSON.stringify(p).slice(0, 60)}`,
      at: evt.created_at || evt.at || "",
    };
  }

  function renderFeed(feedEl, events) {
    if (!feedEl || !events?.length) return;
    feedEl.innerHTML = events
      .slice(0, 25)
      .map((e) => {
        const { html, at } = formatEventLine(e);
        return `<div class="event-line">${html}<br><small>${String(at).slice(0, 19)}</small></div>`;
      })
      .join("");
  }

  function startSse({ companyId, feedEl, onMode, onEvent }) {
    let url = "/api/v1/stream/events";
    if (companyId) url += `?company_id=${encodeURIComponent(companyId)}`;
    let es = null;
    let stopped = false;
    let retryMs = 2000;
    const buffer = [];

    const connect = () => {
      if (stopped) return;
      es = new EventSource(url, { withCredentials: true });
      es.onopen = () => {
        retryMs = 2000;
        onMode?.("sse");
      };
      es.onmessage = (ev) => {
        try {
          const p = JSON.parse(ev.data);
          if (p.type !== "events" || !p.items?.length) return;
          p.items.forEach((item) => {
            buffer.unshift(item);
            onEvent?.(item);
          });
          while (buffer.length > 30) buffer.pop();
          renderFeed(feedEl, buffer);
        } catch {
          /* ignore */
        }
      };
      es.onerror = () => {
        try {
          es.close();
        } catch {
          /* ignore */
        }
        if (stopped) return;
        if (feedEl) {
          feedEl.innerHTML = `<span class="muted small">SSE neu verbinden in ${Math.round(retryMs / 1000)}s…</span>`;
        }
        window.setTimeout(connect, retryMs);
        retryMs = Math.min(retryMs * 1.5, 30000);
      };
    };

    connect();
    return () => {
      stopped = true;
      try {
        es?.close();
      } catch {
        /* ignore */
      }
    };
  }

  function startSocketIo({ companyId, feedEl, onMode, onEvent }) {
    return new Promise((resolve) => {
      if (typeof global.io !== "function") {
        resolve(null);
        return;
      }
      const buffer = [];
      try {
        const socket = global.io({
          path: "/socket.io",
          transports: ["websocket", "polling"],
          withCredentials: true,
          reconnection: true,
          reconnectionAttempts: 5,
          reconnectionDelay: 1000,
          reconnectionDelayMax: 5000,
          timeout: 10000,
          query: { company_id: companyId || "" },
          extraHeaders: { "X-Requested-With": "XMLHttpRequest" },
        });
        let stopped = false;

        const stop = () => {
          stopped = true;
          try {
            socket.disconnect();
          } catch {
            /* ignore */
          }
        };

        socket.on("connect", () => {
          try {
            socket.emit("subscribe", { company_id: companyId || "" });
          } catch (e) {
            console.error("Subscribe emit failed:", e);
            stop();
            resolve(null);
          }
        });

        socket.on("subscribed", (msg) => {
          if (msg && msg.ok === false) {
            console.warn("Subscribe failed:", msg.error);
            stop();
            resolve(null);
            return;
          }
          onMode?.("websocket");
          resolve(stop);
        });

        socket.on("platform_event", (evt) => {
          if (stopped) return;
          buffer.unshift(evt);
          onEvent?.(evt);
          while (buffer.length > 30) buffer.pop();
          renderFeed(feedEl, buffer);
        });

        socket.on("connect_error", (error) => {
          console.warn("WebSocket connect error:", error);
          if (!stopped) {
            stop();
            resolve(null);
          }
        });

        socket.on("disconnect", (reason) => {
          if (!stopped && reason === "io server disconnect") {
            console.warn("WebSocket disconnected by server:", reason);
            stop();
            resolve(null);
          }
        });

        if (socket.io) {
          socket.io.on("reconnect_failed", () => {
            if (!stopped) {
              console.warn("WebSocket reconnect failed");
              stop();
              resolve(null);
            }
          });
        }

        setTimeout(() => {
          if (!stopped && !socket.connected) {
            console.warn("WebSocket connection timeout");
            stop();
            resolve(null);
          }
        }, 10500);
      } catch (e) {
        console.error("Socket.io initialization failed:", e);
        resolve(null);
      }
    });
  }

  async function start({ companyId, feedEl, onMode, onEvent }) {
    try {
      const st = await fetch("/api/v1/realtime/status", { credentials: "include" }).then((r) =>
        r.ok ? r.json() : null,
      );
      if (st?.websocket?.enabled) {
        const stopWs = await startSocketIo({ companyId, feedEl, onMode, onEvent });
        if (stopWs) return stopWs;
      }
    } catch {
      /* fallback */
    }
    return startSse({ companyId, feedEl, onMode, onEvent });
  }

  global.BauPassOpsRealtime = { start, formatEventLine, renderFeed };
})(typeof window !== "undefined" ? window : globalThis);
