/**
 * SUPPIX chat media gallery — photos, files, voice notes from a conversation.
 */
(function initSuppixChatGallery(global) {
  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function isImage(filename, contentType) {
    const mime = String(contentType || "").toLowerCase();
    if (mime.startsWith("image/")) return true;
    return /\.(jpe?g|png|webp|gif)$/i.test(String(filename || ""));
  }

  function isAudio(filename, contentType, e2eMeta) {
    return Boolean(global.SUPPIXChatVoice?.isAudioAttachment?.(filename, contentType, e2eMeta));
  }

  function collectMediaItems(messages, labels = {}) {
    const items = [];
    (messages || []).forEach((msg) => {
      const attachments = Array.isArray(msg.attachments) ? msg.attachments : [];
      attachments.forEach((attachment) => {
        const id = String(attachment.id || "").trim();
        if (!id) return;
        const filename = String(attachment.filename || "file");
        const contentType = String(attachment.contentType || attachment.content_type || "");
        const e2eMeta = String(attachment.e2eMeta || attachment.e2e_meta || "");
        const kind = isAudio(filename, contentType, e2eMeta)
          ? "voice"
          : isImage(filename, contentType)
            ? "image"
            : "file";
        items.push({
          id,
          filename,
          contentType,
          e2eMeta,
          kind,
          createdAt: msg.createdAt || msg.created_at || "",
          senderType: msg.senderType || msg.sender_type || "",
        });
      });
    });
    return items.reverse();
  }

  function ensureStyles() {
    if (global.document.getElementById("suppixChatGalleryStyles")) return;
    const style = global.document.createElement("style");
    style.id = "suppixChatGalleryStyles";
    style.textContent = `
.chat-gallery-modal{position:fixed;inset:0;z-index:1600;display:flex;align-items:center;justify-content:center;padding:1rem;background:rgba(2,6,12,.72)}
.chat-gallery-modal.hidden{display:none}
.chat-gallery-inner{width:min(720px,96vw);max-height:min(82vh,760px);overflow:hidden;border-radius:16px;background:#0b141a;border:1px solid rgba(255,255,255,.08);display:flex;flex-direction:column;color:#e9edef}
.chat-gallery-head{display:flex;align-items:center;justify-content:space-between;padding:.85rem 1rem;border-bottom:1px solid rgba(255,255,255,.08)}
.chat-gallery-head h4{margin:0;font-size:1rem}
.chat-gallery-tabs{display:flex;gap:.35rem;padding:.55rem 1rem;border-bottom:1px solid rgba(255,255,255,.06)}
.chat-gallery-tabs button{border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.04);color:#e9edef;border-radius:999px;padding:.3rem .7rem;font-size:.75rem;cursor:pointer}
.chat-gallery-tabs button.is-active{background:rgba(0,168,132,.22);border-color:rgba(0,168,132,.45);color:#fff}
.chat-gallery-grid{flex:1;overflow:auto;padding:1rem;display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:.65rem}
.chat-gallery-item{border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:.55rem;background:rgba(255,255,255,.03);cursor:pointer;text-align:left}
.chat-gallery-item:hover{border-color:rgba(0,168,132,.35)}
.chat-gallery-item .kind{font-size:1.35rem;line-height:1}
.chat-gallery-item .name{display:block;margin-top:.35rem;font-size:.72rem;opacity:.85;word-break:break-word}
.chat-gallery-item .when{display:block;margin-top:.2rem;font-size:.66rem;opacity:.55}
.chat-gallery-empty{padding:1.25rem;color:rgba(233,237,239,.65);font-size:.9rem}
`;
    global.document.head.appendChild(style);
  }

  function ensureModal(labels = {}) {
    ensureStyles();
    let modal = global.document.getElementById("suppixChatGalleryModal");
    if (modal) return modal;
    modal = global.document.createElement("div");
    modal.id = "suppixChatGalleryModal";
    modal.className = "chat-gallery-modal hidden";
    modal.innerHTML = `
      <div class="chat-gallery-inner" role="dialog" aria-modal="true" aria-labelledby="chatGalleryTitle">
        <div class="chat-gallery-head">
          <h4 id="chatGalleryTitle">${escapeHtml(labels.title || "Medien")}</h4>
          <button type="button" id="chatGalleryClose" aria-label="${escapeHtml(labels.close || "Schließen")}">✕</button>
        </div>
        <div class="chat-gallery-tabs" id="chatGalleryTabs"></div>
        <div class="chat-gallery-grid" id="chatGalleryGrid"></div>
      </div>`;
    global.document.body.appendChild(modal);
    modal.addEventListener("click", (event) => {
      if (event.target === modal) modal.classList.add("hidden");
    });
    modal.querySelector("#chatGalleryClose")?.addEventListener("click", () => modal.classList.add("hidden"));
    return modal;
  }

  function openChatGallery({ messages, labels = {}, onOpenItem } = {}) {
    const modal = ensureModal(labels);
    const items = collectMediaItems(messages, labels);
    const tabs = modal.querySelector("#chatGalleryTabs");
    const grid = modal.querySelector("#chatGalleryGrid");
    const filters = [
      { id: "all", label: labels.all || "Alle" },
      { id: "image", label: labels.images || "Fotos" },
      { id: "voice", label: labels.voice || "Sprache" },
      { id: "file", label: labels.files || "Dateien" },
    ];
    let active = "all";

    const render = () => {
      const visible = active === "all" ? items : items.filter((item) => item.kind === active);
      if (tabs) {
        tabs.innerHTML = filters
          .map((filter) => `<button type="button" class="${filter.id === active ? "is-active" : ""}" data-filter="${filter.id}">${escapeHtml(filter.label)}</button>`)
          .join("");
        tabs.querySelectorAll("button").forEach((btn) => {
          btn.addEventListener("click", () => {
            active = btn.getAttribute("data-filter") || "all";
            render();
          });
        });
      }
      if (!grid) return;
      if (!visible.length) {
        grid.innerHTML = `<div class="chat-gallery-empty">${escapeHtml(labels.empty || "Keine Medien in dieser Unterhaltung.")}</div>`;
        return;
      }
      grid.innerHTML = visible
        .map((item) => {
          const icon = item.kind === "image" ? "🖼" : item.kind === "voice" ? "🎤" : "📎";
          const when = item.createdAt ? String(item.createdAt).slice(0, 16).replace("T", " ") : "";
          return `<button type="button" class="chat-gallery-item" data-id="${escapeHtml(item.id)}" data-kind="${escapeHtml(item.kind)}">
            <span class="kind" aria-hidden="true">${icon}</span>
            <span class="name">${escapeHtml(item.filename)}</span>
            <span class="when">${escapeHtml(when)}</span>
          </button>`;
        })
        .join("");
      grid.querySelectorAll(".chat-gallery-item").forEach((btn) => {
        btn.addEventListener("click", () => {
          const id = btn.getAttribute("data-id") || "";
          const kind = btn.getAttribute("data-kind") || "";
          const item = visible.find((entry) => entry.id === id);
          if (item) onOpenItem?.(item, { kind, id });
        });
      });
    };

    render();
    modal.classList.remove("hidden");
  }

  global.SUPPIXChatGallery = {
    collectMediaItems,
    openChatGallery,
  };
})(typeof window !== "undefined" ? window : globalThis);
