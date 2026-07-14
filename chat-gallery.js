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
          messageId: String(msg.id || ""),
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
.chat-gallery-tabs{display:flex;gap:.35rem;padding:.55rem 1rem;border-bottom:1px solid rgba(255,255,255,.06);flex-wrap:wrap}
.chat-gallery-tabs button{border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.04);color:#e9edef;border-radius:999px;padding:.3rem .7rem;font-size:.75rem;cursor:pointer}
.chat-gallery-tabs button.is-active{background:rgba(0,168,132,.22);border-color:rgba(0,168,132,.45);color:#fff}
.chat-gallery-grid{flex:1;overflow:auto;padding:1rem;display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:.65rem}
.chat-gallery-item{border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:.45rem;background:rgba(255,255,255,.03);cursor:pointer;text-align:left;display:flex;flex-direction:column;gap:.35rem;min-height:120px}
.chat-gallery-item:hover{border-color:rgba(0,168,132,.35)}
.chat-gallery-item .thumb{width:100%;aspect-ratio:1;border-radius:8px;object-fit:cover;background:#1f2c34;display:block}
.chat-gallery-item .kind{font-size:1.35rem;line-height:1}
.chat-gallery-item .name{display:block;font-size:.72rem;opacity:.85;word-break:break-word}
.chat-gallery-item .when{display:block;font-size:.66rem;opacity:.55}
.chat-gallery-item .actions{display:flex;gap:.35rem;margin-top:auto}
.chat-gallery-item .actions button{flex:1;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.05);color:#e9edef;border-radius:8px;padding:.25rem;font-size:.65rem;cursor:pointer}
.chat-gallery-empty{padding:1.25rem;color:rgba(233,237,239,.65);font-size:.9rem}
.chat-media-lightbox{position:fixed;inset:0;z-index:1700;display:flex;flex-direction:column;background:rgba(0,0,0,.88);color:#fff}
.chat-media-lightbox.hidden{display:none}
.chat-media-lightbox-head{display:flex;align-items:center;justify-content:space-between;padding:.75rem 1rem;background:rgba(0,0,0,.35)}
.chat-media-lightbox-head button{border:none;background:transparent;color:#fff;font-size:1.4rem;cursor:pointer;padding:.25rem .5rem}
.chat-media-lightbox-body{flex:1;display:grid;place-items:center;padding:1rem;overflow:auto}
.chat-media-lightbox-body img,.chat-media-lightbox-body video{max-width:min(96vw,920px);max-height:min(78vh,820px);border-radius:8px;object-fit:contain}
.chat-media-lightbox-actions{display:flex;gap:.5rem;justify-content:center;padding:.85rem 1rem calc(.85rem + env(safe-area-inset-bottom,0px));background:rgba(0,0,0,.35)}
.chat-media-lightbox-actions button{border:none;border-radius:999px;padding:.55rem 1.1rem;font:inherit;font-weight:600;cursor:pointer;background:#00a884;color:#fff}
.chat-media-lightbox-actions button.ghost{background:rgba(255,255,255,.12)}
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

  function ensureLightbox() {
    ensureStyles();
    let box = global.document.getElementById("suppixChatMediaLightbox");
    if (box) return box;
    box = global.document.createElement("div");
    box.id = "suppixChatMediaLightbox";
    box.className = "chat-media-lightbox hidden";
    box.innerHTML = `
      <div class="chat-media-lightbox-head">
        <span id="chatMediaLightboxTitle"></span>
        <button type="button" id="chatMediaLightboxClose" aria-label="Schließen">✕</button>
      </div>
      <div class="chat-media-lightbox-body" id="chatMediaLightboxBody"></div>
      <div class="chat-media-lightbox-actions">
        <button type="button" id="chatMediaLightboxDownload">Herunterladen</button>
        <button type="button" class="ghost" id="chatMediaLightboxDismiss">Schließen</button>
      </div>`;
    global.document.body.appendChild(box);
    const close = () => box.classList.add("hidden");
    box.querySelector("#chatMediaLightboxClose")?.addEventListener("click", close);
    box.querySelector("#chatMediaLightboxDismiss")?.addEventListener("click", close);
    box.addEventListener("click", (event) => {
      if (event.target === box) close();
    });
    return box;
  }

  function openMediaLightbox({ title, url, kind, onDownload, labels = {} } = {}) {
    const box = ensureLightbox();
    const body = box.querySelector("#chatMediaLightboxBody");
    const titleEl = box.querySelector("#chatMediaLightboxTitle");
    const downloadBtn = box.querySelector("#chatMediaLightboxDownload");
    if (titleEl) titleEl.textContent = String(title || "");
    if (body) {
      body.innerHTML = kind === "image"
        ? `<img src="${escapeHtml(url)}" alt="${escapeHtml(title || "Bild")}" />`
        : `<p>${escapeHtml(title || "Datei")}</p>`;
    }
    if (downloadBtn) {
      downloadBtn.textContent = labels.download || "Herunterladen";
      downloadBtn.onclick = () => { if (typeof onDownload === "function") onDownload(); };
    }
    box.classList.remove("hidden");
  }

  function openChatGallery({ messages, labels = {}, onOpenItem, onDeleteItem, resolveItemUrl } = {}) {
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
          const thumb = item.kind === "image"
            ? `<img class="thumb" data-thumb-id="${escapeHtml(item.id)}" alt="" loading="lazy" />`
            : `<span class="kind" aria-hidden="true">${icon}</span>`;
          const deleteBtn = onDeleteItem && item.messageId
            ? `<button type="button" data-delete-msg="${escapeHtml(item.messageId)}">${escapeHtml(labels.delete || "Entfernen")}</button>`
            : "";
          return `<div class="chat-gallery-item" data-id="${escapeHtml(item.id)}" data-kind="${escapeHtml(item.kind)}" data-msg="${escapeHtml(item.messageId)}">
            ${thumb}
            <span class="name">${escapeHtml(item.filename)}</span>
            <span class="when">${escapeHtml(when)}</span>
            <div class="actions">
              <button type="button" data-open="1">${escapeHtml(labels.open || "Öffnen")}</button>
              ${deleteBtn}
            </div>
          </div>`;
        })
        .join("");
      grid.querySelectorAll(".chat-gallery-item").forEach((card) => {
        const id = card.getAttribute("data-id") || "";
        const kind = card.getAttribute("data-kind") || "";
        const item = visible.find((entry) => entry.id === id);
        card.querySelector("[data-open]")?.addEventListener("click", () => {
          if (item) onOpenItem?.(item, { kind, id });
        });
        card.querySelector("[data-delete-msg]")?.addEventListener("click", (event) => {
          event.stopPropagation();
          const messageId = card.getAttribute("data-msg") || "";
          if (messageId && item) onDeleteItem?.(item, { messageId });
        });
      });
      if (typeof resolveItemUrl === "function") {
        grid.querySelectorAll("img[data-thumb-id]").forEach((img) => {
          const id = img.getAttribute("data-thumb-id") || "";
          const item = visible.find((entry) => entry.id === id);
          if (!item) return;
          void resolveItemUrl(item).then((url) => {
            if (url) img.src = url;
          }).catch(() => {});
        });
      }
    };

    render();
    modal.classList.remove("hidden");
  }

  global.SUPPIXChatGallery = {
    collectMediaItems,
    openChatGallery,
    openMediaLightbox,
  };
})(typeof window !== "undefined" ? window : globalThis);
