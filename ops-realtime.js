/**
 * SUPPIX ops live feed — Socket.IO when supported, otherwise silent HTTP polling.
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
    if (type === "worker.site_checkin" || type === "worker.proximity_login") {
      const worker = p.workerId || p.worker_id || "?";
      const label = type === "worker.proximity_login" ? "Standort-Login" : "Eingestempelt";
      return {
        html: `<strong>${worker}</strong> ${label}${p.proximity ? " (GPS)" : ""}`,
        at: evt.created_at || "",
      };
    }
    if (type === "access.app_login") {
      const worker = p.workerId || p.worker_id || "?";
      return {
        html: `<strong>${worker}</strong> Standort-Anmeldung`,
        at: evt.created_at || "",
      };
    }
    if (type === "access.app_logout") {
      const worker = p.workerId || p.worker_id || "?";
      return {
        html: `<strong>${worker}</strong> Standort verlassen`,
        at: evt.created_at || "",
      };
    }
    if (type === "access.check_out") {
      const worker = p.workerId || p.worker_id || "?";
      return {
        html: `<strong>${worker}</strong> Ausgestempelt (Standort verlassen)`,
        at: evt.created_at || "",
      };
    }
    if (type === "access.check_in") {
      const worker = p.workerId || p.worker_id || "?";
      return {
        html: `<strong>${worker}</strong> Eingestempelt @ ${p.gate || "Standort"}`,
        at: evt.created_at || "",
      };
    }
    if (type === "worker.site_leave") {
      const worker = p.workerId || p.worker_id || "?";
      return {
        html: `<strong>${worker}</strong> hat den Standort verlassen`,
        at: evt.created_at || "",
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

  function startPolling({ companyId, feedEl, onMode, onEvent }) {
    let stopped = false;
    let timer = null;
    let retryMs = 5000;
    let sinceId = null;
    const seen = new Set();
    const buffer = [];

    const remember = (evt) => {
      if (!evt?.id || seen.has(evt.id)) return false;
      seen.add(evt.id);
      if (seen.size > 300) {
        seen.forEach((id) => {
          if (seen.size <= 200) return;
          seen.delete(id);
        });
      }
      buffer.unshift(evt);
      while (buffer.length > 30) buffer.pop();
      onEvent?.(evt);
      renderFeed(feedEl, buffer);
      return true;
    };

    const poll = async () => {
      if (stopped) return;
      let url = "/api/v1/events/recent?limit=25";
      if (companyId) url += `&company_id=${encodeURIComponent(companyId)}`;
      if (sinceId) url += `&since_id=${encodeURIComponent(sinceId)}`;
      try {
        const response = await fetch(url, { credentials: "include", headers: { Accept: "application/json" } });
        if (!response.ok) {
          if (response.status === 401) {
            stopped = true;
            return;
          }
          timer = global.setTimeout(poll, retryMs);
          retryMs = Math.min(Math.round(retryMs * 1.4), 60000);
          return;
        }
        retryMs = 5000;
        const payload = await response.json();
        const events = Array.isArray(payload?.events) ? payload.events : [];
        if (events.length) {
          sinceId = events[events.length - 1].id || sinceId;
          events.forEach(remember);
        }
        onMode?.("polling");
      } catch {
        /* silent retry */
      }
      if (!stopped) timer = global.setTimeout(poll, retryMs);
    };

    poll();
    return () => {
      stopped = true;
      if (timer) global.clearTimeout(timer);
    };
  }

  function startSocketIo({ companyId, feedEl, onMode, onEvent }) {
    return new Promise((resolve) => {
      if (typeof global.io !== "function") {
        resolve(null);
        return;
      }
      const buffer = [];
      let stopped = false;
      let settled = false;
      let socket = null;

      const finish = (stopFn) => {
        if (settled) return;
        settled = true;
        resolve(stopFn);
      };

      const stop = () => {
        stopped = true;
        try {
          socket?.disconnect();
        } catch {
          /* ignore */
        }
      };

      try {
        socket = global.io({
          path: "/socket.io",
          transports: ["polling", "websocket"],
          withCredentials: true,
          reconnection: false,
          timeout: 8000,
          query: { company_id: companyId || "" },
        });
      } catch {
        finish(null);
        return;
      }

      socket.on("connect", () => {
        try {
          socket.emit("subscribe", { company_id: companyId || "" });
        } catch {
          stop();
          finish(null);
        }
      });

      socket.on("subscribed", (msg) => {
        if (msg && msg.ok === false) {
          stop();
          finish(null);
          return;
        }
        onMode?.("websocket");
        finish(() => {
          stopped = true;
          try {
            socket.disconnect();
          } catch {
            /* ignore */
          }
        });
      });

      socket.on("platform_event", (evt) => {
        if (stopped) return;
        buffer.unshift(evt);
        onEvent?.(evt);
        while (buffer.length > 30) buffer.pop();
        renderFeed(feedEl, buffer);
      });

      socket.on("connect_error", () => {
        stop();
        finish(null);
      });

      socket.on("disconnect", () => {
        if (!stopped && !settled) {
          stop();
          finish(null);
        }
      });

      global.setTimeout(() => {
        if (!stopped && !socket.connected) {
          stop();
          finish(null);
        }
      }, 8500);
    });
  }

  async function start({ companyId, feedEl, onMode, onEvent }) {
    try {
      const st = await fetch("/api/v1/realtime/status", { credentials: "include" }).then((r) =>
        r.ok ? r.json() : null,
      );
      const ws = st?.websocket;
      if (ws?.enabled && ws?.supported !== false) {
        const stopWs = await startSocketIo({ companyId, feedEl, onMode, onEvent });
        if (stopWs) return stopWs;
      }
    } catch {
      /* polling fallback */
    }
    return startPolling({ companyId, feedEl, onMode, onEvent });
  }

  global.SUPPIXOpsRealtime = { start, formatEventLine, renderFeed };
})(typeof window !== "undefined" ? window : globalThis);
