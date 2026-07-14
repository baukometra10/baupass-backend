/**
 * SUPPIX chat message context menu — WhatsApp-style long-press / right-click actions.
 */
(function initSuppixChatMessageMenu(global) {
  const LONG_PRESS_MS = 480;
  const MOVE_CANCEL_PX = 12;

  let overlayEl = null;
  let panelEl = null;
  let backdropEl = null;
  let activeBubble = null;
  let suppressClickUntil = 0;
  let stylesInjected = false;

  function ensureStyles() {
    if (stylesInjected || !global.document) return;
    stylesInjected = true;
    const style = global.document.createElement("style");
    style.id = "suppixChatMsgMenuStyles";
    style.textContent = [
      ".chat-msg-menu-overlay{position:fixed;inset:0;z-index:120}",
      ".chat-msg-menu-overlay.hidden{display:none}",
      ".chat-msg-menu-backdrop{position:absolute;inset:0;background:rgba(0,0,0,.42)}",
      ".chat-msg-menu-panel{position:fixed;z-index:121;min-width:210px;max-width:min(92vw,280px);background:#1f2c34;border:1px solid rgba(134,150,160,.22);border-radius:14px;padding:.35rem;box-shadow:0 12px 32px rgba(0,0,0,.38);display:flex;flex-direction:column;gap:.08rem}",
      ".chat-msg-menu-item{display:flex;align-items:center;gap:.55rem;width:100%;border:none;background:transparent;color:#e9edef;border-radius:10px;padding:.62rem .75rem;cursor:pointer;text-align:left;font:inherit;font-size:.88rem}",
      ".chat-msg-menu-item:hover{background:rgba(255,255,255,.06)}",
      ".chat-msg-menu-item.is-danger{color:#f87171}",
      ".chat-msg-menu-item.is-active{color:#53bdeb}",
      ".chat-pinned-bar{display:flex;flex-direction:column;gap:.35rem;margin:0 0 .65rem;padding:.45rem;border-radius:12px;background:rgba(0,168,132,.08);border:1px solid rgba(0,168,132,.18)}",
      ".chat-pinned-item{display:flex;align-items:center;gap:.45rem;width:100%;border:none;background:rgba(255,255,255,.04);color:inherit;border-radius:10px;padding:.45rem .55rem;cursor:pointer;text-align:left;font:inherit}",
      ".chat-pinned-item:hover{background:rgba(255,255,255,.08)}",
      ".chat-pinned-icon{flex-shrink:0;font-size:.82rem}",
      ".chat-pinned-text{flex:1;min-width:0;font-size:.78rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;opacity:.92}",
      ".chat-pinned-jump{flex-shrink:0;font-size:.68rem;color:#53bdeb;font-weight:700}",
    ].join("");
    global.document.head.appendChild(style);
  }

  function ensureOverlay() {
    ensureStyles();
    if (overlayEl) return overlayEl;
    const doc = global.document;
    if (!doc) return null;
    overlayEl = doc.createElement("div");
    overlayEl.id = "suppixChatMsgMenuOverlay";
    overlayEl.className = "chat-msg-menu-overlay hidden";
    overlayEl.innerHTML = `
      <div class="chat-msg-menu-backdrop" data-chat-menu-close="1"></div>
      <div class="chat-msg-menu-panel" role="menu"></div>
    `;
    doc.body.appendChild(overlayEl);
    backdropEl = overlayEl.querySelector(".chat-msg-menu-backdrop");
    panelEl = overlayEl.querySelector(".chat-msg-menu-panel");
    backdropEl?.addEventListener("click", closeMenu);
    doc.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeMenu();
    });
    return overlayEl;
  }

  function closeMenu() {
    if (activeBubble) {
      activeBubble.classList.remove("chat-msg-menu-active");
      activeBubble = null;
    }
    overlayEl?.classList.add("hidden");
    if (panelEl) panelEl.innerHTML = "";
  }

  function isInteractiveTarget(target) {
    if (!(target instanceof Element)) return false;
    return Boolean(target.closest(
      "button:not(.bubble-menu-btn), a, input, textarea, select, audio, video, iframe, .chat-image-preview, [data-attachment-id], [data-voice-callback], .chat-location-open, .chat-location-map-hit, .chat-location-map-embed",
    ));
  }

  function findBubble(target, rootEl, bubbleSelector) {
    if (!(target instanceof Element) || !rootEl) return null;
    const bubble = target.closest(bubbleSelector);
    if (!bubble || !rootEl.contains(bubble)) return null;
    const messageId = bubble.getAttribute("data-message-id") || "";
    if (!messageId || messageId.startsWith("pending-")) return null;
    return bubble;
  }

  function extractCopyText(msg, labels = {}) {
    if (!msg || typeof msg !== "object") return "";
    const voice = labels.voice || "Sprachnachricht";
    const photo = labels.photo || "Foto";
    const location = labels.location || "Standort";
    const encrypted = labels.encrypted || "Verschlüsselte Nachricht";
    const empty = labels.empty || "Nachricht";
    const call = labels.call || "Anruf";
    let body = String(msg.body || "").trim();
    const att = Array.isArray(msg.attachments) && msg.attachments[0] ? msg.attachments[0] : null;
    const meta = att?.e2eMeta || att?.e2e_meta || "";
    const contentType = att?.contentType || att?.content_type || "";
    const filename = att?.filename || "";
    if (att && global.SUPPIXChatVoice?.isAudioAttachment?.(filename, contentType, meta)) {
      return voice;
    }
    if (att && (/^image\//i.test(contentType) || /\.(jpe?g|png|webp|gif)$/i.test(filename))) {
      return photo;
    }
    if (global.SUPPIXChatVoice?.isVoiceOnlyBody?.(body, voice)) return voice;
    if (body.startsWith("@voice-call|")) return call;
    if (global.SUPPIXChatLocation?.isLocationBody?.(body)) {
      const parsed = global.SUPPIXChatLocation.parseLocationBody(body);
      if (parsed?.lat != null && parsed?.lng != null) {
        return `${location} (${parsed.lat}, ${parsed.lng})`;
      }
      return location;
    }
    if (
      body === "encrypted"
      || /verschlüssel|encrypted|decryption failed|entschlüsselung fehlgeschlagen/i.test(body)
    ) {
      return encrypted;
    }
    if (!body) return empty;
    return body;
  }

  function positionPanel(bubble) {
    if (!panelEl || !bubble) return;
    const rect = bubble.getBoundingClientRect();
    const panelRect = panelEl.getBoundingClientRect();
    const margin = 8;
    let top = rect.top - panelRect.height - margin;
    if (top < margin) top = rect.bottom + margin;
    let left = rect.left;
    if (left + panelRect.width > global.innerWidth - margin) {
      left = global.innerWidth - panelRect.width - margin;
    }
    if (left < margin) left = margin;
    panelEl.style.top = `${Math.round(top)}px`;
    panelEl.style.left = `${Math.round(left)}px`;
  }

  function buildMenuItem(action, label, { danger = false, active = false } = {}) {
    return `<button type="button" class="chat-msg-menu-item${danger ? " is-danger" : ""}${active ? " is-active" : ""}" role="menuitem" data-chat-menu-action="${action}">${label}</button>`;
  }

  function openMenu(bubble, msg, config) {
    ensureOverlay();
    if (!overlayEl || !panelEl || !bubble || !msg) return;
    closeMenu();
    activeBubble = bubble;
    bubble.classList.add("chat-msg-menu-active");
    const labels = config.labels || {};
    const threadId = config.getThreadId?.() || "";
    const prefs = global.SUPPIXChatMessagePrefs;
    const pinned = prefs?.isPinned?.(threadId, msg.id);
    const starred = prefs?.isStarred?.(threadId, msg.id);
    const copyText = extractCopyText(msg, labels.copy || {});
    const canCopy = Boolean(copyText && copyText !== labels.copy?.encrypted);
    const items = [];
    items.push(buildMenuItem("reply", labels.reply || "Antworten"));
    if (canCopy) items.push(buildMenuItem("copy", labels.copyAction || "Kopieren"));
    if (config.canForward?.(msg)) items.push(buildMenuItem("forward", labels.forward || "Weiterleiten"));
    items.push(buildMenuItem("pin", pinned ? (labels.unpin || "Loslösen") : (labels.pin || "Fixieren"), { active: pinned }));
    items.push(buildMenuItem("star", starred ? (labels.unstar || "Stern entfernen") : (labels.star || "Mit Stern markieren"), { active: starred }));
    if (config.canDelete?.(msg)) {
      items.push(buildMenuItem("delete", labels.delete || "Löschen", { danger: true }));
    }
    panelEl.innerHTML = items.join("");
    overlayEl.classList.remove("hidden");
    panelEl.style.visibility = "hidden";
    panelEl.style.top = "0";
    panelEl.style.left = "0";
    global.requestAnimationFrame(() => {
      positionPanel(bubble);
      panelEl.style.visibility = "";
    });
    panelEl.querySelectorAll("[data-chat-menu-action]").forEach((btn) => {
      btn.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const action = btn.getAttribute("data-chat-menu-action") || "";
        closeMenu();
        suppressClickUntil = Date.now() + 400;
        if (action === "reply") config.onReply?.(msg);
        else if (action === "copy") config.onCopy?.(msg, copyText);
        else if (action === "forward") config.onForward?.(msg);
        else if (action === "pin") config.onPinToggle?.(msg);
        else if (action === "star") config.onStarToggle?.(msg);
        else if (action === "delete") config.onDelete?.(msg);
      });
    });
  }

  function mountMessageMenu({
    rootEl,
    bubbleSelector = "[data-message-id]",
    getMessageById,
    getThreadId,
    labels = {},
    canDelete,
    canForward,
    onReply,
    onCopy,
    onForward,
    onPinToggle,
    onStarToggle,
    onDelete,
  } = {}) {
    if (!rootEl || rootEl.dataset.chatMenuBound === "1") {
      return { close: closeMenu };
    }
    rootEl.dataset.chatMenuBound = "1";
    ensureOverlay();

    const config = {
      labels,
      getThreadId,
      canDelete,
      canForward,
      onReply,
      onCopy,
      onForward,
      onPinToggle,
      onStarToggle,
      onDelete,
    };

    let pressTimer = null;
    let pressStart = null;

    function cancelPress() {
      if (pressTimer) {
        clearTimeout(pressTimer);
        pressTimer = null;
      }
      pressStart = null;
    }

    function openForBubble(bubble) {
      const messageId = bubble.getAttribute("data-message-id") || "";
      const msg = getMessageById?.(messageId);
      if (!msg) return;
      openMenu(bubble, msg, config);
    }

    rootEl.addEventListener("click", (event) => {
      if (Date.now() < suppressClickUntil) {
        event.preventDefault();
        event.stopPropagation();
        return;
      }
      const menuBtn = event.target instanceof Element ? event.target.closest("[data-chat-menu-id]") : null;
      if (menuBtn) {
        event.preventDefault();
        event.stopPropagation();
        const bubble = menuBtn.closest(bubbleSelector);
        if (bubble) openForBubble(bubble);
      }
    });

    rootEl.addEventListener("contextmenu", (event) => {
      if (!(event.target instanceof Element)) return;
      if (isInteractiveTarget(event.target)) return;
      const bubble = findBubble(event.target, rootEl, bubbleSelector);
      if (!bubble) return;
      event.preventDefault();
      openForBubble(bubble);
    });

    rootEl.addEventListener("touchstart", (event) => {
      if (!(event.target instanceof Element)) return;
      if (isInteractiveTarget(event.target)) return;
      const bubble = findBubble(event.target, rootEl, bubbleSelector);
      if (!bubble) return;
      pressStart = {
        x: event.touches[0]?.clientX || 0,
        y: event.touches[0]?.clientY || 0,
      };
      cancelPress();
      pressTimer = global.setTimeout(() => {
        pressTimer = null;
        suppressClickUntil = Date.now() + 500;
        openForBubble(bubble);
      }, LONG_PRESS_MS);
    }, { passive: true });

    rootEl.addEventListener("touchmove", (event) => {
      if (!pressTimer || !pressStart) return;
      const x = event.touches[0]?.clientX || 0;
      const y = event.touches[0]?.clientY || 0;
      if (Math.abs(x - pressStart.x) > MOVE_CANCEL_PX || Math.abs(y - pressStart.y) > MOVE_CANCEL_PX) {
        cancelPress();
      }
    }, { passive: true });

    rootEl.addEventListener("touchend", cancelPress, { passive: true });
    rootEl.addEventListener("touchcancel", cancelPress, { passive: true });

    return { close: closeMenu };
  }

  function escapeHtmlBasic(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderPinnedBarHtml({ threadId, messages, getPreview, labelPinned, labelJump }) {
    const prefs = global.SUPPIXChatMessagePrefs;
    const pinnedIds = prefs?.getPinnedIds?.(threadId) || [];
    if (!pinnedIds.length || !Array.isArray(messages)) return "";
    const byId = new Map(messages.map((m) => [String(m.id), m]));
    const rows = pinnedIds
      .map((id) => {
        const msg = byId.get(String(id));
        if (!msg) return "";
        const preview = escapeHtmlBasic(getPreview?.(msg) || "");
        return `<button type="button" class="chat-pinned-item" data-pinned-jump="${escapeHtmlBasic(id)}"><span class="chat-pinned-icon" aria-hidden="true">📌</span><span class="chat-pinned-text">${preview}</span><span class="chat-pinned-jump">${escapeHtmlBasic(labelJump || "Anzeigen")}</span></button>`;
      })
      .filter(Boolean)
      .slice(0, 3);
    if (!rows.length) return "";
    return `<div class="chat-pinned-bar" role="region" aria-label="${escapeHtmlBasic(labelPinned || "Fixierte Nachricht")}">${rows.join("")}</div>`;
  }

  function bindPinnedBar(rootEl, onJump) {
    if (!rootEl || rootEl.dataset.pinnedBarBound === "1") return;
    rootEl.dataset.pinnedBarBound = "1";
    rootEl.addEventListener("click", (event) => {
      const btn = event.target instanceof Element ? event.target.closest("[data-pinned-jump]") : null;
      if (!btn) return;
      event.preventDefault();
      const messageId = btn.getAttribute("data-pinned-jump") || "";
      if (messageId) onJump?.(messageId);
    });
  }

  global.SUPPIXChatMessageMenu = {
    mountMessageMenu,
    closeMenu,
    extractCopyText,
    renderPinnedBarHtml,
    bindPinnedBar,
  };
})(typeof window !== "undefined" ? window : globalThis);
