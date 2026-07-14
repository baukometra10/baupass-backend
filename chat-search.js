/**
 * SUPPIX in-conversation chat search (text + media filters).
 */
(function initSuppixChatSearch(global) {
  function normalizeQuery(value) {
    return String(value || "").trim().toLowerCase();
  }

  function messageSearchText(msg, labels) {
    const body = String(msg?.body || "").trim();
    if (!body) {
      const attachments = Array.isArray(msg?.attachments) ? msg.attachments : [];
      if (attachments.some((item) => /audio|voice|webm|ogg|mpeg/i.test(String(item?.contentType || "")))) {
        return labels.voice || "voice";
      }
      if (attachments.some((item) => /^image\//i.test(String(item?.contentType || "")))) {
        return labels.photo || "photo";
      }
    }
    if (body === "encrypted") return labels.encrypted || "encrypted";
    if (body === "voice") return labels.voice || "voice";
    if (body === "photo") return labels.photo || "photo";
    return body;
  }

  function filterMessages(messages, query, labels) {
    const q = normalizeQuery(query);
    if (!q) return [];
    const rows = Array.isArray(messages) ? messages : [];
    return rows.filter((msg) => {
      const text = normalizeQuery(messageSearchText(msg, labels));
      const attachments = Array.isArray(msg?.attachments) ? msg.attachments : [];
      const hasVoice = attachments.some((item) => /audio|voice|webm|ogg|mpeg/i.test(String(item?.contentType || "")))
        || text.includes("sprachnachricht") || text === "voice";
      const hasPhoto = attachments.some((item) => /^image\//i.test(String(item?.contentType || "")))
        || text === "photo" || text === "foto";
      if (q === "voice" || q === "sprachnachricht") return hasVoice;
      if (q === "photo" || q === "foto" || q === "bild") return hasPhoto;
      if (q === "encrypted" || q === "verschlüsselt") return text === "encrypted" || text.includes("verschlüssel");
      return text.includes(q);
    });
  }

  function highlightBubble(bubbleEl, active) {
    if (!bubbleEl) return;
    bubbleEl.classList.toggle("chat-search-hit", Boolean(active));
  }

  function scrollToMessage(messageId) {
    const id = String(messageId || "").trim();
    if (!id) return null;
    const bubble = global.document?.querySelector(`[data-message-id="${CSS.escape(id)}"]`);
    if (!bubble) return null;
    bubble.scrollIntoView({ behavior: "smooth", block: "center" });
    bubble.classList.add("chat-search-flash");
    global.setTimeout(() => bubble.classList.remove("chat-search-flash"), 1400);
    return bubble;
  }

  function mountSearchBar({
    containerEl,
    inputEl,
    resultsEl,
    getMessages,
    labels = {},
    onSelect,
  } = {}) {
    if (!inputEl || inputEl.dataset.searchBound) return () => {};
    inputEl.dataset.searchBound = "1";
    let timer = null;

    const renderResults = (matches) => {
      if (!resultsEl) return;
      if (!matches.length) {
        resultsEl.innerHTML = `<p class="chat-search-empty">${labels.empty || "Keine Treffer"}</p>`;
        resultsEl.classList.remove("hidden");
        return;
      }
      resultsEl.innerHTML = matches.slice(0, 12).map((msg) => {
        const text = messageSearchText(msg, labels).slice(0, 90);
        const time = String(msg?.createdAt || "").slice(11, 16);
        return `<button type="button" class="chat-search-result" data-search-id="${String(msg.id || "")}">
          <span class="chat-search-result-time">${time}</span>
          <span class="chat-search-result-text">${text}</span>
        </button>`;
      }).join("");
      resultsEl.classList.remove("hidden");
      resultsEl.querySelectorAll("[data-search-id]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const id = btn.getAttribute("data-search-id");
          onSelect?.(id);
          scrollToMessage(id);
          resultsEl.classList.add("hidden");
        });
      });
    };

    const runSearch = () => {
      const q = normalizeQuery(inputEl.value);
      if (!q) {
        resultsEl?.classList.add("hidden");
        return;
      }
      const matches = filterMessages(getMessages?.() || [], q, labels);
      renderResults(matches);
    };

    inputEl.addEventListener("input", () => {
      if (timer) global.clearTimeout(timer);
      timer = global.setTimeout(runSearch, 220);
    });
    inputEl.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        inputEl.value = "";
        resultsEl?.classList.add("hidden");
      }
    });
    global.document?.addEventListener("click", (event) => {
      if (!containerEl?.contains(event.target)) {
        resultsEl?.classList.add("hidden");
      }
    });

    return () => {
      if (timer) global.clearTimeout(timer);
      resultsEl?.classList.add("hidden");
    };
  }

  global.SUPPIXChatSearch = {
    filterMessages,
    messageSearchText,
    scrollToMessage,
    mountSearchBar,
    highlightBubble,
  };
})(typeof window !== "undefined" ? window : globalThis);
