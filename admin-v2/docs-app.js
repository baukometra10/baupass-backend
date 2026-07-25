/**
 * SUPPIX Docs — Quill-powered Word-like editor (jsdelivr, CSP-safe).
 */
(function () {
  const WP = window.WorkPassStorage;
  const TOKEN_KEY = WP?.KEYS?.ADMIN_TOKEN || "workpass-admin-token";
  const USER_KEY = WP?.KEYS?.ADMIN_USER || "workpass-admin-user";
  const COMPANY_KEY = WP?.KEYS?.ADMIN_COMPANY || "workpass-admin-company";

  /* Compact HTML only — whitespace between tags becomes empty Quill paragraphs. */
  /* Templates/snippets come from docs-i18n-content.js (8 languages). */
  function contentPack() {
    const lang = typeof window.getDocsPageLang === "function" ? window.getDocsPageLang() : "de";
    const all = window.DocsContentI18n || {};
    return all[lang] || all.en || all.de || {};
  }

  function getTemplateHtml(key) {
    const pack = contentPack();
    if (key === "blank") return pack.blank || "<p><br></p>";
    return pack[key] || pack.blank || "<p><br></p>";
  }

  function getSnippetHtml(key) {
    const map = {
      greeting: "snGreeting",
      closing: "snClosing",
      address_block: "snAddress",
      worker_line: "snWorker",
      date_line: "snDate",
      signature: "snSign",
    };
    const pack = contentPack();
    return pack[map[key] || key] || "";
  }

  const TEMPLATE_META_IDS = [
    { id: "letter", titleKey: "tplLetter", blurbKey: "tplLetterBlurb", topic: "correspondence" },
    { id: "invitation", titleKey: "tplInvitation", blurbKey: "tplInvitationBlurb", topic: "correspondence" },
    { id: "reminder", titleKey: "tplReminder", blurbKey: "tplReminderBlurb", topic: "correspondence" },
    { id: "complaint_ack", titleKey: "tplComplaintAck", blurbKey: "tplComplaintAckBlurb", topic: "correspondence" },
    { id: "warning", titleKey: "tplWarning", blurbKey: "tplWarningBlurb", topic: "hr" },
    { id: "certificate", titleKey: "tplCertificate", blurbKey: "tplCertificateBlurb", topic: "hr" },
    { id: "praise", titleKey: "tplPraise", blurbKey: "tplPraiseBlurb", topic: "hr" },
    { id: "absence", titleKey: "tplAbsence", blurbKey: "tplAbsenceBlurb", topic: "hr" },
    { id: "vacation", titleKey: "tplVacation", blurbKey: "tplVacationBlurb", topic: "hr" },
    { id: "access", titleKey: "tplAccess", blurbKey: "tplAccessBlurb", topic: "ops" },
    { id: "visitor", titleKey: "tplVisitor", blurbKey: "tplVisitorBlurb", topic: "ops" },
    { id: "site_rules", titleKey: "tplSiteRules", blurbKey: "tplSiteRulesBlurb", topic: "ops" },
    { id: "toolbox", titleKey: "tplToolbox", blurbKey: "tplToolboxBlurb", topic: "safety" },
    { id: "damage", titleKey: "tplDamage", blurbKey: "tplDamageBlurb", topic: "ops" },
    { id: "material", titleKey: "tplMaterial", blurbKey: "tplMaterialBlurb", topic: "ops" },
    { id: "handover", titleKey: "tplHandover", blurbKey: "tplHandoverBlurb", topic: "ops" },
    { id: "induction", titleKey: "tplInduction", blurbKey: "tplInductionBlurb", topic: "ops" },
    { id: "policy", titleKey: "tplPolicy", blurbKey: "tplPolicyBlurb", topic: "safety" },
    { id: "meeting", titleKey: "tplMeeting", blurbKey: "tplMeetingBlurb", topic: "meetings" },
    { id: "blank", titleKey: "tplBlank", blurbKey: "tplBlankBlurb", topic: "blank" },
  ];

  const TOPIC_ORDER = ["team", "custom", "correspondence", "hr", "ops", "safety", "meetings", "blank"];
  const TOPIC_LABEL_KEYS = {
    team: "topicTeam",
    custom: "topicCustom",
    correspondence: "topicCorrespondence",
    hr: "topicHr",
    ops: "topicOps",
    safety: "topicSafety",
    meetings: "topicMeetings",
    blank: "topicBlank",
  };

  function dt(key, vars) {
    return typeof window.docsPageT === "function" ? window.docsPageT(key, vars) : key;
  }

  function templateMetaList() {
    return TEMPLATE_META_IDS.map((t) => ({
      id: t.id,
      topic: t.topic,
      title: dt(t.titleKey),
      blurb: dt(t.blurbKey),
    }));
  }

  let lastTemplateKey = "";
  let skipTemplateConfirmOnce = false;
  let activeTopicFilter = "all";
  let tplSearchQuery = "";
  const RECENT_TPL_KEY = "workpass-docs-recent-templates";

  function loadRecentTemplates() {
    try {
      const raw = JSON.parse(localStorage.getItem(RECENT_TPL_KEY) || "[]");
      return Array.isArray(raw) ? raw.map(String).filter(Boolean).slice(0, 8) : [];
    } catch {
      return [];
    }
  }

  function pushRecentTemplate(id) {
    const key = String(id || "").trim();
    if (!key) return;
    const next = [key, ...loadRecentTemplates().filter((x) => x !== key)].slice(0, 8);
    try {
      localStorage.setItem(RECENT_TPL_KEY, JSON.stringify(next));
    } catch {
      /* ignore */
    }
  }

  function templatePreviewSnippet(t) {
    let html = "";
    try {
      if (t.team || t.custom) {
        html = String(t.previewHtml || t.blurb || "");
      } else {
        html = getTemplateHtml(t.id) || "";
      }
    } catch {
      html = "";
    }
    const text = String(html)
      .replace(/<[^>]+>/g, " ")
      .replace(/\{\{\s*[^}]+\s*\}\}/g, "…")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 96);
    return text || t.blurb || "";
  }

  function isRtlLang() {
    return (typeof window.getDocsPageLang === "function" ? window.getDocsPageLang() : "de") === "ar";
  }

  function syncEditorWritingDirection(opts = {}) {
    const rtl = isRtlLang();
    document.body.classList.toggle("docs-editor-rtl", rtl);
    if (!quill?.root) return;
    quill.root.setAttribute("dir", rtl ? "rtl" : "ltr");
    quill.root.style.direction = rtl ? "rtl" : "ltr";
    quill.root.style.textAlign = rtl ? "right" : "";
    const paper = document.querySelector(".docs-paper");
    if (paper) paper.setAttribute("dir", rtl ? "rtl" : "ltr");

    // Quill paragraph formats so caret/typing follow RTL from the right edge.
    try {
      const len = quill.getLength();
      if (len > 1) {
        if (rtl) {
          quill.formatText(0, len - 1, { direction: "rtl", align: "right" }, "silent");
        } else {
          quill.formatText(0, len - 1, { direction: false, align: false }, "silent");
        }
      }
      quill.root.querySelectorAll(".wp-doc-title, .wp-subtitle, .wp-center, .wp-caption").forEach((el) => {
        el.style.textAlign = "center";
        el.classList.remove("ql-align-right", "ql-align-left");
        el.classList.add("ql-align-center");
        if (el.getAttribute("style")?.includes("text-align")) {
          /* keep center */
        }
      });
      if (rtl) {
        quill.root.querySelectorAll(":scope > p, :scope > h1, :scope > h2, :scope > h3, :scope > h4, :scope > ol, :scope > ul, :scope > li").forEach((el) => {
          if (el.classList.contains("wp-doc-title") || el.classList.contains("wp-subtitle") || el.classList.contains("wp-center") || el.classList.contains("wp-caption")) return;
          el.style.direction = "rtl";
          if (!el.style.textAlign || el.style.textAlign === "left" || el.style.textAlign === "start") {
            el.style.textAlign = "right";
          }
        });
      }
    } catch {
      /* ignore format errors on empty docs */
    }

    if (opts.focusStart !== false) {
      try {
        quill.setSelection(0, 0, "silent");
      } catch {
        /* ignore */
      }
    }
  }

  function wpGet(key) {
    return WP ? WP.getItem(key) : localStorage.getItem(key);
  }

  function $(id) {
    return document.getElementById(id);
  }

  function qs() {
    return new URLSearchParams(location.search);
  }

  function activeCompanyId() {
    const fromUrl = (qs().get("company_id") || "").trim();
    if (fromUrl) return fromUrl;
    return (wpGet(COMPANY_KEY) || "").trim();
  }

  function authHeaders() {
    const token = wpGet(TOKEN_KEY);
    const headers = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    return headers;
  }

  function companyQuery(extra = {}) {
    const params = new URLSearchParams();
    const cid = activeCompanyId();
    if (cid) params.set("company_id", cid);
    Object.entries(extra).forEach(([k, v]) => {
      if (v != null && String(v).trim() !== "") params.set(k, String(v));
    });
    const s = params.toString();
    return s ? `?${s}` : "";
  }

  function currentUserRole() {
    try {
      const raw = wpGet(USER_KEY);
      const user = raw ? JSON.parse(raw) : null;
      return String(user?.role || "").trim().toLowerCase();
    } catch {
      return "";
    }
  }

  let ownerUnlock = null;

  function setStatus(el, text, kind = "") {
    if (!el) return;
    el.textContent = text || "";
    el.classList.toggle("is-ok", kind === "ok");
    el.classList.toggle("is-err", kind === "err");
  }

  function getOwnerUnlock() {
    if (ownerUnlock) return ownerUnlock;
    const factory = window.BaupassOwnerUnlock?.create;
    if (!factory) return null;
    ownerUnlock = factory({
      t: (key, fallback) => {
        const v = dt(key);
        return v && v !== key ? v : fallback || key;
      },
      getCompanyId: () => activeCompanyId(),
      onStatus: (text, kind) => setStatus($("saveStatus"), text, kind || ""),
      onVerified: async () => {
        $("docsLockNowBtn")?.classList.remove("hidden");
      },
      api: async (path, options = {}) => {
        const res = await fetch(path, {
          ...options,
          headers: { ...authHeaders(), ...(options.headers || {}) },
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          const err = new Error(data.message || data.error || `http_${res.status}`);
          err.status = res.status;
          err.body = data;
          err.data = data;
          throw err;
        }
        return data;
      },
    });
    return ownerUnlock;
  }

  function isContractContext(doc = currentDoc) {
    if (doc && (doc.contract_id || String(doc.mode || "").toLowerCase() === "contract")) return true;
    return !!(qs().get("contract_id") || "").trim();
  }

  async function api(path, options = {}) {
    const res = await fetch(path, {
      ...options,
      headers: { ...authHeaders(), ...(options.headers || {}) },
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = new Error(data.message || data.error || `http_${res.status}`);
      err.status = res.status;
      err.body = data;
      // Owner-OTP nur bei Arbeitsvertrag / contract-linked docs
      if (isContractContext(data.document) || err.body?.error === "contracts_locked" || err.body?.ownerSetupRequired) {
        if (isContractContext() || err.body?.error === "contracts_locked" || err.body?.ownerSetupRequired) {
          const unlock = getOwnerUnlock();
          if (unlock) await unlock.handleApiError(err);
        }
      }
      throw err;
    }
    if (data.document && isContractContext(data.document) && !data.document.bodyRedacted) {
      getOwnerUnlock()?.markUnlocked(true);
    }
    return data;
  }

  async function apiUpload(path, formData) {
    const headers = {};
    const token = wpGet(TOKEN_KEY);
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(path, { method: "POST", headers, body: formData });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = new Error(data.message || data.error || `http_${res.status}`);
      err.status = res.status;
      err.body = data;
      if (isContractContext() || err.body?.error === "contracts_locked" || err.body?.ownerSetupRequired) {
        const unlock = getOwnerUnlock();
        if (unlock) await unlock.handleApiError(err);
      }
      throw err;
    }
    return data;
  }

  function formatWhen(iso) {
    const raw = String(iso || "").trim();
    if (!raw) return "—";
    return raw.slice(0, 19).replace("T", " ");
  }

  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function plainToHtml(text) {
    const lines = String(text || "").split(/\r?\n/);
    if (!lines.length) return "<p><br></p>";
    return lines.map((line) => (line.trim() ? `<p>${escapeHtml(line)}</p>` : "<p><br></p>")).join("");
  }

  function todayIso() {
    const d = new Date();
    const dd = String(d.getDate()).padStart(2, "0");
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    return `${dd}.${mm}.${d.getFullYear()}`;
  }

  let quill = null;
  let currentDoc = null;
  let dirty = false;
  let saveTimer = null;
  let zoom = 1;
  let selectedWorkerId = "";
  let autoFit = true;
  let fitScale = 1;
  let layout = {
    pageSize: "a4",
    marginTopMm: 22,
    marginRightMm: 20,
    marginBottomMm: 22,
    marginLeftMm: 25,
    showHeader: true,
    showFooter: true,
    lineSpacing: 1.15,
    watermark: "",
  };

  const PAPER_SIZES = {
    a4: { id: "a4", label: "A4", w: 794, h: 1123, print: "A4" },
    a3: { id: "a3", label: "A3", w: 1123, h: 1587, print: "A3" },
    a1: { id: "a1", label: "A1", w: 2245, h: 3178, print: "A1" },
  };
  // Small desk gap between sheets; edge spacers keep text off the break line.
  const PAGE_GAP_PX = 16;
  const PAGE_EDGE_PAD_PX = 22;
  let pageCount = 1;
  let pageSyncRaf = 0;
  let pageSyncCoalesce = false;
  let editorResizeObs = null;
  let lastFrameKey = "";
  let lastStackH = 0;
  let lastPaperId = "";
  let cachedChromeH = 0;
  let chromeCacheTs = 0;
  let suppressEditorResize = false;
  let suppressTextSideEffects = false;
  let lastTypedContentH = 0;
  let lastEdgeKey = "";
  let currentPageView = 1;
  let findMatches = [];
  let findIndex = -1;
  let findReplaceMode = false;
  let commentsTimer = 0;
  let commentsFilter = "open";
  let statsTimer = 0;
  let selectionSyncRaf = 0;
  let diffVersionHtml = "";
  let diffVersionMeta = null;

  function getPaper() {
    return PAPER_SIZES[layout.pageSize] || PAPER_SIZES.a4;
  }

  function measureBandHeight(el, enabled) {
    if (!enabled || !el) return 0;
    return Math.max(0, Math.ceil(el.getBoundingClientRect().height));
  }

  function getChromeHeight(force = false) {
    const now = performance.now();
    if (!force && now - chromeCacheTs < 400) return cachedChromeH;
    const headerH = measureBandHeight($("docHeader"), layout.showHeader);
    const footerH = measureBandHeight($("docFooter"), layout.showFooter);
    cachedChromeH = headerH + footerH;
    chromeCacheTs = now;
    return cachedChromeH;
  }

  function syncDocUrl(docId) {
    try {
      const url = new URL(location.href);
      const cid = activeCompanyId();
      if (cid) url.searchParams.set("company_id", cid);
      if (docId) url.searchParams.set("id", String(docId));
      else url.searchParams.delete("id");
      history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
    } catch {
      /* ignore */
    }
  }

  function maybeAutoWatermark(status) {
    // Only stamp saved drafts — template preview / empty start must stay clean.
    if (!currentDoc?.id) return;
    const st = String(status || currentDoc?.status || "draft");
    if (st === "draft" && !String(layout.watermark || "").trim()) {
      layout.watermark = "draft";
      if ($("watermarkSelect")) $("watermarkSelect").value = "draft";
      refreshWatermarkFrames();
    } else if (st === "approved" && layout.watermark === "draft") {
      layout.watermark = "";
      if ($("watermarkSelect")) $("watermarkSelect").value = "";
      refreshWatermarkFrames();
    }
  }

  function refreshTocBlocks() {
    if (!quill?.root) return false;
    const toc = quill.root.querySelector(".wp-toc");
    if (!toc) return false;
    const heads = [...quill.root.querySelectorAll("h1, h2, h3")].filter(
      (h) => (h.textContent || "").trim() && !toc.contains(h),
    );
    if (!heads.length) return false;
    heads.forEach((h, i) => {
      if (!h.id) h.id = `sec-${i + 1}`;
    });
    const items = heads
      .map((h) => {
        const level = h.tagName === "H1" ? 1 : h.tagName === "H2" ? 2 : 3;
        return `<li class="toc-l${level}"><a href="#${escapeHtml(h.id)}">${escapeHtml((h.textContent || "").trim())}</a></li>`;
      })
      .join("");
    toc.innerHTML = `<p><strong>${escapeHtml(dt("tocTitle"))}</strong></p><ul>${items}</ul>`;
    return true;
  }

  function parseCommentMeta(raw) {
    const s = String(raw || "");
    if (s.startsWith("{")) {
      try {
        const o = JSON.parse(s);
        return {
          text: String(o.text || o.note || ""),
          assignee: String(o.assignee || ""),
          done: !!o.done,
        };
      } catch {
        /* fall through */
      }
    }
    let done = false;
    let assignee = "";
    let text = s;
    if (/^\[done\]/i.test(text)) {
      done = true;
      text = text.replace(/^\[done\]\s*/i, "");
    }
    const m = text.match(/^\[@([^\]]+)\]\s*/);
    if (m) {
      assignee = m[1].trim();
      text = text.slice(m[0].length);
    }
    return { text, assignee, done };
  }

  function serializeCommentMeta(meta) {
    return JSON.stringify({
      text: String(meta.text || "").trim(),
      assignee: String(meta.assignee || "").trim(),
      done: !!meta.done,
    });
  }

  let liveRev = 0;
  let appliedLiveRev = 0;
  let liveFollow = false;
  let latestPeerLive = null;
  let qesStatusCache = null;
  let docsSocket = null;

  function markDirty() {
    if (!dirty) {
      dirty = true;
      setStatus($("saveStatus"), dt("unsaved"), "");
    }
    liveRev += 1;
    scheduleOfflineDraft();
  }

  function getBodyHtml() {
    return quill ? quill.root.innerHTML : "<p><br></p>";
  }

  function getHeaderHtml() {
    return ($("docHeader")?.innerHTML || "").trim();
  }

  function getFooterHtml() {
    return ($("docFooter")?.innerHTML || "").trim();
  }

  function getHtml() {
    // Full document HTML for export / merge / print persistence
    const parts = [];
    if (layout.showHeader && getHeaderHtml()) {
      parts.push(`<header class="wp-doc-header">${getHeaderHtml()}</header>`);
    }
    parts.push(`<main class="wp-doc-body">${getBodyHtml()}</main>`);
    if (layout.showFooter && getFooterHtml()) {
      parts.push(`<footer class="wp-doc-footer">${getFooterHtml()}</footer>`);
    }
    return parts.join("");
  }

  function getText() {
    const header = ($("docHeader")?.innerText || "").trim();
    const footer = ($("docFooter")?.innerText || "").trim();
    const body = quill ? String(quill.getText() || "").trim() : "";
    return [header, body, footer].filter(Boolean).join("\n");
  }

  function compactHtml(html) {
    return String(html || "")
      .replace(/>\s+</g, "><")
      .trim();
  }

  const WP_BLOCK_CLASSES = [
    "wp-letter",
    "wp-recipient",
    "wp-date",
    "wp-subject",
    "wp-sign",
    "wp-meta",
    "wp-center",
    "wp-subtitle",
    "wp-caption",
    "wp-title",
    "wp-doc-title",
    "wp-page-break",
    "wp-body-hint",
  ];

  function reinjectLtrSpans(sourceHtml) {
    if (!quill?.root || !isRtlLang()) return;
    const src = document.createElement("div");
    src.innerHTML = String(sourceHtml || "");
    const marks = [...src.querySelectorAll("span.wp-ltr[dir='ltr'], span.wp-ltr[dir=\"ltr\"]")];
    if (!marks.length) {
      // Fallback: wrap known contact tokens if template used bare placeholders.
      const tokens = ["{{company.email}}", "{{company.contact}}", "{{worker.badge}}"];
      tokens.forEach((token) => {
        const walker = document.createTreeWalker(quill.root, NodeFilter.SHOW_TEXT);
        const nodes = [];
        while (walker.nextNode()) nodes.push(walker.currentNode);
        nodes.forEach((node) => {
          const val = node.nodeValue || "";
          const idx = val.indexOf(token);
          if (idx < 0) return;
          if (node.parentElement?.classList?.contains("wp-ltr")) return;
          const before = val.slice(0, idx);
          const after = val.slice(idx + token.length);
          const wrap = document.createElement("span");
          wrap.className = "wp-ltr";
          wrap.setAttribute("dir", "ltr");
          wrap.textContent = token;
          const parent = node.parentNode;
          if (!parent) return;
          if (before) parent.insertBefore(document.createTextNode(before), node);
          parent.insertBefore(wrap, node);
          if (after) parent.insertBefore(document.createTextNode(after), node);
          parent.removeChild(node);
        });
      });
      return;
    }
    marks.forEach((span) => {
      const needle = span.textContent || "";
      if (!needle) return;
      const walker = document.createTreeWalker(quill.root, NodeFilter.SHOW_TEXT);
      let node = walker.nextNode();
      while (node) {
        const val = node.nodeValue || "";
        const idx = val.indexOf(needle);
        if (idx >= 0 && !node.parentElement?.classList?.contains("wp-ltr")) {
          const before = val.slice(0, idx);
          const after = val.slice(idx + needle.length);
          const wrap = document.createElement("span");
          wrap.className = "wp-ltr";
          wrap.setAttribute("dir", "ltr");
          wrap.textContent = needle;
          const parent = node.parentNode;
          if (!parent) break;
          if (before) parent.insertBefore(document.createTextNode(before), node);
          parent.insertBefore(wrap, node);
          if (after) parent.insertBefore(document.createTextNode(after), node);
          parent.removeChild(node);
          break;
        }
        node = walker.nextNode();
      }
    });
  }

  function restoreWpClasses(sourceHtml) {
    if (!quill?.root) return;
    const src = document.createElement("div");
    src.innerHTML = String(sourceHtml || "");
    const srcBlocks = [...src.querySelectorAll("p, h1, h2, h3, h4")];
    const dstBlocks = [...quill.root.querySelectorAll(":scope > p, :scope > h1, :scope > h2, :scope > h3, :scope > h4")];
    srcBlocks.forEach((el, i) => {
      const dst = dstBlocks[i];
      if (!dst) return;
      WP_BLOCK_CLASSES.forEach((cls) => {
        if (el.classList.contains(cls)) dst.classList.add(cls);
      });
      const align = el.style?.textAlign || el.getAttribute("align");
      if (align) dst.style.textAlign = align;
    });
    reinjectLtrSpans(sourceHtml);
    reinjectPlaceholderChips();
  }

  function reinjectPlaceholderChips() {
    if (!quill?.root) return;
    const walk = document.createTreeWalker(quill.root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walk.nextNode()) nodes.push(walk.currentNode);
    nodes.forEach((node) => {
      const raw = node.nodeValue || "";
      if (node.parentElement?.closest?.(".wp-ph-chip, .wp-hint-chip")) return;
      const hasMerge = /\{\{\s*[a-zA-Z0-9_.-]+\s*\}\}/.test(raw);
      const hasHint = /\[[^\]\n]{3,120}\]/.test(raw);
      if (!hasMerge && !hasHint) return;
      const wrap = document.createElement("span");
      let html = escapeHtml(raw);
      if (hasMerge) {
        html = html.replace(
          /(\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\})/g,
          '<span class="wp-ph-chip" data-wp-ph="$2">$1</span>',
        );
      }
      if (hasHint) {
        html = html.replace(
          /\[([^\]\n]{3,120})\]/g,
          '<span class="wp-hint-chip" data-wp-hint="1">$1</span>',
        );
      }
      wrap.innerHTML = html;
      node.parentNode?.replaceChild(wrap, node);
      // unwrap helper span
      while (wrap.firstChild) wrap.parentNode?.insertBefore(wrap.firstChild, wrap);
      wrap.remove();
    });
  }

  function setHtml(html) {
    if (!quill) return;
    const raw = String(html || "").trim() || "<p><br></p>";
    // If full envelope HTML, extract body; else treat as body
    const mainMatch = /<main[^>]*class="wp-doc-body"[^>]*>([\s\S]*?)<\/main>/i.exec(raw);
    const headerMatch = /<header[^>]*class="wp-doc-header"[^>]*>([\s\S]*?)<\/header>/i.exec(raw);
    const footerMatch = /<footer[^>]*class="wp-doc-footer"[^>]*>([\s\S]*?)<\/footer>/i.exec(raw);
    const isEnvelope = !!(mainMatch || headerMatch || footerMatch);
    if (isEnvelope) {
      // Envelope replace must clear missing bands — do not keep previous doc chrome.
      if ($("docHeader")) {
        $("docHeader").innerHTML = headerMatch ? wrapMergePlaceholders(headerMatch[1]) : "";
      }
      if ($("docFooter")) {
        $("docFooter").innerHTML = footerMatch ? wrapMergePlaceholders(footerMatch[1]) : "";
      }
    }
    // Collapse inter-tag whitespace — Quill otherwise inserts empty <p><br></p> gaps.
    const body = wrapMergePlaceholders(compactHtml(mainMatch ? mainMatch[1] : raw) || "<p><br></p>");
    quill.setContents([]);
    quill.clipboard.dangerouslyPasteHTML(body);
    restoreWpClasses(body);
    quill.history.clear();
    syncEditorWritingDirection({ focusStart: false });
    schedulePaperSync({ force: true });
  }

  function wrapMergePlaceholders(html) {
    const s = String(html || "");
    const parts = s.split(/(<span\b[^>]*\bwp-ph-chip\b[^>]*>[\s\S]*?<\/span>)/i);
    return parts
      .map((part, i) => {
        if (i % 2 === 1) return part;
        return part.replace(
          /\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}/g,
          '<span class="wp-ph-chip" data-wp-ph="$1">{{$1}}</span>',
        );
      })
      .join("");
  }

  function toggleFocusMode(force) {
    const on = typeof force === "boolean" ? force : !document.body.classList.contains("docs-fullscreen");
    document.body.classList.toggle("docs-fullscreen", on);
    const exit = $("exitFocusBtn");
    if (exit) {
      exit.hidden = !on;
      exit.classList.toggle("is-on", on);
    }
    scheduleFit();
  }

  function applyLayoutToDom() {
    const root = document.documentElement;
    const paper = getPaper();
    root.style.setProperty("--m-top", `${layout.marginTopMm}mm`);
    root.style.setProperty("--m-right", `${layout.marginRightMm}mm`);
    root.style.setProperty("--m-bottom", `${layout.marginBottomMm}mm`);
    root.style.setProperty("--m-left", `${layout.marginLeftMm}mm`);
    root.style.setProperty("--doc-lh", String(layout.lineSpacing || 1.15));
    root.style.setProperty("--paper-w", `${paper.w}px`);
    root.style.setProperty("--paper-h", `${paper.h}px`);
    root.style.setProperty("--page-gap", `${PAGE_GAP_PX}px`);
    document.body.classList.toggle("hide-header", !layout.showHeader);
    document.body.classList.toggle("hide-footer", !layout.showFooter);
    document.body.classList.remove("page-a4", "page-a3", "page-a1");
    document.body.classList.add(`page-${paper.id}`);
    if ($("marginTop")) $("marginTop").value = String(layout.marginTopMm);
    if ($("marginBottom")) $("marginBottom").value = String(layout.marginBottomMm);
    if ($("marginLeft")) $("marginLeft").value = String(layout.marginLeftMm);
    if ($("marginRight")) $("marginRight").value = String(layout.marginRightMm);
    if ($("lineSpacingSelect")) $("lineSpacingSelect").value = String(layout.lineSpacing || 1.15);
    if ($("pageSizeSelect")) $("pageSizeSelect").value = paper.id;
    if ($("watermarkSelect")) $("watermarkSelect").value = String(layout.watermark || "");
    syncPaperWatermark();
    chromeCacheTs = 0;
    lastFrameKey = "";
    lastStackH = 0;
    lastPaperId = "";
    lastEdgeKey = "";
    syncPaperPages({ force: true, fit: true });
  }

  function syncPaperWatermark() {
    const kind = String(layout.watermark || "").trim();
    document.body.setAttribute("data-watermark", kind || "none");
    const el = $("paperWatermark");
    if (el) {
      el.hidden = true;
      el.textContent = "";
    }
  }

  function refreshWatermarkFrames() {
    syncPaperWatermark();
    lastFrameKey = "";
    schedulePaperSync({ force: true });
  }

  function customTemplatesKey() {
    return `baupass-docs-user-templates:${activeCompanyId() || "none"}`;
  }

  function loadCustomTemplates() {
    try {
      const raw = localStorage.getItem(customTemplatesKey());
      const list = raw ? JSON.parse(raw) : [];
      return Array.isArray(list) ? list : [];
    } catch {
      return [];
    }
  }

  function saveCustomTemplates(list) {
    try {
      localStorage.setItem(customTemplatesKey(), JSON.stringify(list.slice(0, 40)));
    } catch {
      setStatus($("saveStatus"), dt("templateSaveFail"), "err");
    }
  }

  function saveCurrentAsTemplate() {
    const title = window.prompt(dt("templateNamePrompt"), ($("docTitle")?.value || "").trim() || dt("tplBlank"));
    if (title === null) return;
    const name = String(title || "").trim() || dt("tplBlank");
    const list = loadCustomTemplates();
    const id = `user_${Date.now().toString(36)}`;
    const entry = {
      id,
      title: name,
      blurb: dt("customTemplateBlurb"),
      html: getHtml(),
      layout: { ...layout },
      createdAt: new Date().toISOString(),
    };
    list.unshift(entry);
    saveCustomTemplates(list);
    activeTopicFilter = "custom";
    setSideTab("templates");
    renderTemplateGallery();
    setStatus($("saveStatus"), dt("templateSaved", { name }), "ok");
    if (activeCompanyId() && confirm(dt("shareTeamTemplate"))) {
      api(`/api/v2/docs/templates${companyQuery()}`, {
        method: "POST",
        body: JSON.stringify({
          company_id: activeCompanyId(),
          title: name,
          blurb: dt("teamTemplateBlurb"),
          contentHtml: getBodyHtml(),
          layout: { ...layout },
        }),
      })
        .then(() => renderTemplateGallery())
        .catch(() => {});
    }
  }

  async function applyCustomTemplate(id) {
    const tpl = loadCustomTemplates().find((t) => t.id === id);
    if (!tpl) return;
    if (getText() && !confirm(dt("confirmTemplate"))) return;
    if (tpl.layout) Object.assign(layout, tpl.layout);
    applyLayoutToDom();
    const html = tpl.html || "<p><br></p>";
    const title = tpl.title || dt("tplBlank");
    if (!currentDoc?.id && activeCompanyId()) {
      try {
        await createBlank({ title, contentHtml: html, mode: "general" });
      } catch (e) {
        setStatus($("saveStatus"), e.message || dt("saveFail"), "err");
        setHtml(html);
      }
    } else {
      setHtml(html);
    }
    lastTemplateKey = `custom:${id}`;
    markDirty();
    if ($("docTitle") && (!$("docTitle").value || ["Unbenannt", dt("untitled"), dt("tplBlank")].includes($("docTitle").value))) {
      $("docTitle").value = title;
    }
    setStatus($("saveStatus"), dt("templateReady", { name: title }), "ok");
    syncEmptyState();
    schedulePaperSync({ force: true, fit: true });
  }

  function deleteCustomTemplate(id) {
    if (!confirm(dt("confirmDeleteTemplate"))) return;
    saveCustomTemplates(loadCustomTemplates().filter((t) => t.id !== id));
    renderTemplateGallery();
  }

  function buildPreflightItems() {
    const title = ($("docTitle")?.value || "").trim();
    const placeholders = collectOpenPlaceholders();
    const words = countDocStats().words;
    const items = [
      {
        id: "title",
        ok: title.length >= 2 && title !== dt("untitled") && title !== dt("tplBlank"),
        label: dt("preflightTitleOk"),
        fail: dt("preflightTitleFail"),
      },
      {
        id: "content",
        ok: words >= 8,
        label: dt("preflightContentOk", { n: words }),
        fail: dt("preflightContentFail"),
      },
      {
        id: "placeholders",
        ok: placeholders.length === 0,
        label: dt("preflightPhOk"),
        fail: dt("preflightPhFail", {
          n: placeholders.length,
          list: placeholders.map((p) => p.token).slice(0, 4).join(", "),
        }),
      },
      {
        id: "saved",
        ok: !!currentDoc?.id && !dirty,
        label: dt("preflightSavedOk"),
        fail: dt("preflightSavedFail"),
      },
      {
        id: "company",
        ok: !!activeCompanyId(),
        label: dt("preflightCompanyOk"),
        fail: dt("preflightCompanyFail"),
      },
    ];
    if (preflightAction === "publish") {
      items.push({
        id: "merge",
        ok: placeholders.length === 0,
        label: dt("preflightMergeOk"),
        fail: dt("preflightMergeFail", { n: placeholders.length }),
      });
    }
    return { items, allOk: items.every((i) => i.ok) };
  }

  let preflightAction = null;

  function openPreflight(action) {
    const modal = $("preflightModal");
    const list = $("preflightList");
    if (!modal || !list) return;
    preflightAction = action;
    const { items, allOk } = buildPreflightItems();
    list.innerHTML = items
      .map(
        (it) =>
          `<li class="preflight-item ${it.ok ? "is-ok" : "is-fail"}">` +
          `<span class="preflight-mark">${it.ok ? "✓" : "!"}</span>` +
          `<span>${escapeHtml(it.ok ? it.label : it.fail)}</span>` +
          `</li>`,
      )
      .join("");
    if (allOk) {
      closePreflight();
      runPreflightAction(action);
      return;
    }
    modal.hidden = false;
    window.DocsIcons?.mountAll(modal, true);
  }

  function closePreflight() {
    const modal = $("preflightModal");
    if (modal) modal.hidden = true;
  }

  function runPreflightAction(action) {
    const act = action || preflightAction;
    preflightAction = null;
    if (act === "approve") setDocStatus("approved").catch(() => {});
    else if (act === "review") setDocStatus("in_review").catch(() => {});
    else if (act === "publish") publishToWorker({ skipPreflight: true }).catch(() => {});
  }

  function renderPageFrames(pages, paper) {
    const host = $("pageFrames");
    if (!host) return;
    const wm = String(layout.watermark || "").trim();
    const wmLabel =
      wm === "draft"
        ? dt("wmDraft")
        : wm === "confidential"
          ? dt("wmConfidential")
          : wm === "copy"
            ? dt("wmCopy")
            : "";
    const key = `${paper.id}:${pages}:${PAGE_EDGE_PAD_PX}:${wm}`;
    if (key === lastFrameKey && host.childElementCount === pages) return;
    lastFrameKey = key;
    const step = paper.h + PAGE_GAP_PX;
    const parts = new Array(pages);
    for (let i = 0; i < pages; i += 1) {
      const near =
        pages <= 24 || Math.abs(i + 1 - (currentPageView || 1)) <= 3 || i === 0 || i === pages - 1;
      parts[i] =
        `<div class="page-frame${near ? "" : " is-sparse"}" data-page="${i + 1}" style="top:${i * step}px;height:${paper.h}px">` +
        (near
          ? `<span class="page-frame-num">${escapeHtml(dt("pageOf", { cur: i + 1, pages }))}</span>`
          : "") +
        (wmLabel && near ? `<span class="page-frame-wm">${escapeHtml(wmLabel)}</span>` : "") +
        `</div>`;
    }
    host.innerHTML = parts.join("");
    syncPaperWatermark();
  }

  function findIndexNearY(targetTop) {
    if (!quill) return 0;
    const len = Math.max(0, quill.getLength() - 1);
    let lo = 0;
    let hi = len;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      const b = quill.getBounds(mid, 1);
      const top = b ? b.top : 0;
      if (top < targetTop) lo = mid + 1;
      else hi = mid;
    }
    return lo;
  }

  function removePageEdgeSpacers() {
    if (!quill) return;
    const nodes = [...quill.root.querySelectorAll(".wp-page-edge")];
    if (!nodes.length) return;
    const ranges = [];
    nodes.forEach((node) => {
      const blot = window.Quill.find(node);
      if (!blot) return;
      ranges.push({ index: quill.getIndex(blot), len: blot.length() });
    });
    ranges
      .sort((a, b) => b.index - a.index)
      .forEach((r) => quill.deleteText(r.index, r.len, "silent"));
  }

  function reconcilePageEdgeSpacers(pages, paper, headerH) {
    if (!quill) return;
    const edgeKey = `${paper.id}:${pages}:${headerH}:${PAGE_EDGE_PAD_PX}`;
    // Always rebuild when page count/paper changes; skip identical geometry.
    if (edgeKey === lastEdgeKey && quill.root.querySelectorAll(".wp-page-edge").length === Math.max(0, pages - 1)) {
      return;
    }
    lastEdgeKey = edgeKey;
    suppressTextSideEffects = true;
    try {
      removePageEdgeSpacers();
      if (pages <= 1) return;
      // Insert from last boundary → first so earlier indices stay stable.
      for (let i = pages - 1; i >= 1; i -= 1) {
        // Spacer = bottom pad + desk gap + top pad of next sheet.
        const targetTop = i * (paper.h + PAGE_GAP_PX) - headerH - PAGE_EDGE_PAD_PX;
        const idx = findIndexNearY(Math.max(0, targetTop));
        quill.insertEmbed(idx, "wpPageEdge", true, "silent");
      }
    } catch {
      /* ignore geometry races while Quill settles */
    } finally {
      requestAnimationFrame(() => {
        suppressTextSideEffects = false;
      });
    }
  }

  function syncPaperPages({ force = false, fit = false } = {}) {
    const paper = getPaper();
    const root = document.documentElement;
    const headerH = measureBandHeight($("docHeader"), layout.showHeader);
    const footerH = measureBandHeight($("docFooter"), layout.showFooter);
    const chrome = headerH + footerH;
    cachedChromeH = chrome;
    chromeCacheTs = performance.now();

    root.style.setProperty("--page-pad-y", `${PAGE_EDGE_PAD_PX}px`);
    // Keep editor min-height exactly one sheet body so empty/short docs stay on page 1.
    const bodyBudget = Math.max(120, paper.h - chrome);
    root.style.setProperty("--chrome-h", `${chrome}px`);
    root.style.setProperty("--body-budget", `${bodyBudget}px`);

    const stage = $("docsStage");
    const prevScroll = stage ? stage.scrollTop : 0;
    const prevPages = pageCount;

    let contentH = bodyBudget;
    if (quill?.root) {
      if (quill.root.style.minHeight) quill.root.style.minHeight = "";
      contentH = Math.max(1, quill.root.scrollHeight | 0);
    }

    // Only open page N+1 once content actually fills page N (no early pad boost).
    let pages = pagesForContentHeight(contentH, bodyBudget);
    let stackH = pages * paper.h + Math.max(0, pages - 1) * PAGE_GAP_PX;
    const paperChanged = paper.id !== lastPaperId;
    const stackChanged = stackH !== lastStackH || pages !== pageCount || paperChanged;

    if (!force && !stackChanged) {
      if (fit) scheduleFit();
      return;
    }

    pageCount = pages;
    lastStackH = stackH;
    lastPaperId = paper.id;
    lastTypedContentH = contentH;

    suppressEditorResize = true;
    if (paperChanged || force) {
      root.style.setProperty("--paper-w", `${paper.w}px`);
      root.style.setProperty("--paper-h", `${paper.h}px`);
      root.style.setProperty("--page-gap", `${PAGE_GAP_PX}px`);
    }
    root.style.setProperty("--page-count", String(pages));
    root.style.setProperty("--stack-h", `${stackH}px`);

    const paperEl = $("docsPaper");
    if (paperEl) {
      paperEl.style.height = `${stackH}px`;
      paperEl.style.minHeight = `${paper.h}px`;
    }
    const stackEl = $("paperStack");
    if (stackEl) stackEl.style.height = `${stackH}px`;

    renderPageFrames(pages, paper);
    reconcilePageEdgeSpacers(pages, paper, headerH);

    // Spacers add height — bump one more sheet if needed (single pass).
    if (quill?.root) {
      const h2 = Math.max(1, quill.root.scrollHeight | 0);
      const pages2 = pagesForContentHeight(h2, bodyBudget);
      if (pages2 > pages) {
        pages = pages2;
        pageCount = pages;
        stackH = pages * paper.h + Math.max(0, pages - 1) * PAGE_GAP_PX;
        lastStackH = stackH;
        lastTypedContentH = h2;
        root.style.setProperty("--page-count", String(pages));
        root.style.setProperty("--stack-h", `${stackH}px`);
        if (paperEl) paperEl.style.height = `${stackH}px`;
        if (stackEl) stackEl.style.height = `${stackH}px`;
        lastEdgeKey = "";
        renderPageFrames(pages, paper);
        reconcilePageEdgeSpacers(pages, paper, headerH);
      }
    }

    // Growing a new empty sheet must not yank the viewport off page 1 while typing.
    if (stage && pages > prevPages) {
      const caretStillOnFirst = (() => {
        try {
          const range = quill?.getSelection?.();
          if (!range) return prevScroll < paper.h * 0.85;
          const b = quill.getBounds(range.index, Math.max(1, range.length || 1));
          return !b || headerH + b.top < paper.h - 48;
        } catch {
          return true;
        }
      })();
      if (caretStillOnFirst) stage.scrollTop = prevScroll;
    }

    updatePageLabel();
    requestAnimationFrame(() => {
      suppressEditorResize = false;
    });

    if (fit || paperChanged) scheduleFit();
  }

  function pagesForContentHeight(contentH, bodyBudget) {
    const budget = Math.max(1, bodyBudget | 0);
    const h = Math.max(1, contentH | 0);
    // Ignore tiny sub-pixel overflow so short docs stay on page 1.
    const effective = Math.max(1, h - 4);
    return Math.min(200, Math.max(1, Math.ceil(effective / budget)));
  }

  function schedulePaperSync(opts = {}) {
    const options = typeof opts === "boolean" ? { force: opts, fit: opts } : opts;
    pageSyncCoalesce = {
      force: !!(pageSyncCoalesce && pageSyncCoalesce.force) || !!options.force,
      fit: !!(pageSyncCoalesce && pageSyncCoalesce.fit) || !!options.fit,
    };
    if (pageSyncRaf) return;
    pageSyncRaf = requestAnimationFrame(() => {
      pageSyncRaf = 0;
      const next = pageSyncCoalesce || {};
      pageSyncCoalesce = false;
      syncPaperPages(next);
    });
  }

  function bindEditorPageObservers() {
    if (!window.ResizeObserver) return;
    if (editorResizeObs) editorResizeObs.disconnect();
    // Do NOT observe quill.root — typing would re-enter sync every frame.
    // Header/footer size changes are rare; debounce via rAF coalesce.
    editorResizeObs = new ResizeObserver(() => {
      if (suppressEditorResize) return;
      chromeCacheTs = 0;
      schedulePaperSync({ force: true });
    });
    const headerEl = $("docHeader");
    const footerEl = $("docFooter");
    if (headerEl) editorResizeObs.observe(headerEl);
    if (footerEl) editorResizeObs.observe(footerEl);
  }

  function computeFitScale() {
    const stage = $("docsStage");
    if (!stage) return 1;
    const pad = 28;
    const available = Math.max(240, stage.clientWidth - pad);
    const paperW = getPaper().w;
    return Math.min(1.15, Math.max(0.22, available / paperW));
  }

  function applyFitScale() {
    fitScale = autoFit ? computeFitScale() : fitScale;
    const effective = Math.min(1.35, Math.max(0.18, fitScale * zoom));
    document.documentElement.style.setProperty("--fit-scale", String(effective));
    if ($("zoomLabel")) {
      $("zoomLabel").textContent = autoFit && zoom === 1 ? dt("auto") : `${Math.round(effective * 100)}%`;
    }
    updatePageLabel();
  }

  let fitRaf = 0;
  function scheduleFit() {
    if (fitRaf) cancelAnimationFrame(fitRaf);
    fitRaf = requestAnimationFrame(() => {
      fitRaf = 0;
      applyFitScale();
    });
  }

  function updatePageLabel() {
    if ($("pageLabel")) {
      const paper = getPaper();
      const pct = Math.round(fitScale * zoom * 100);
      const text = dt("pageLabel", {
        size: paper.label,
        pages: pageCount,
        pct,
        left: layout.marginLeftMm,
        right: layout.marginRightMm,
      });
      if ($("pageLabel").textContent !== text) $("pageLabel").textContent = text;
    }
    updatePagePosLabel();
  }

  function updatePagePosLabel() {
    const el = $("pagePosLabel");
    if (!el) return;
    const cur = Math.min(pageCount, Math.max(1, currentPageView));
    const text = dt("pagePos", { cur, pages: pageCount });
    if (el.textContent !== text) el.textContent = text;
    syncFooterPageLabels(cur);
  }

  function syncFooterPageLabels(cur) {
    const page = Math.min(pageCount, Math.max(1, cur || currentPageView || 1));
    const label = dt("pageOf", { cur: page, pages: pageCount });
    document.querySelectorAll(".wp-page-num, .wp-page-xy").forEach((node) => {
      if (node.textContent !== label) node.textContent = label;
    });
  }

  function countDocStats() {
    if (!quill) return { words: 0, chars: 0 };
    const raw = String(quill.getText() || "")
      .replace(/\u200b/g, "")
      .trim();
    if (!raw) return { words: 0, chars: 0 };
    const words = raw.split(/\s+/).filter(Boolean).length;
    return { words, chars: raw.length };
  }

  function updateWordCountLabel() {
    const el = $("wordCountLabel");
    if (!el) return;
    const { words, chars } = countDocStats();
    const text = dt("wordCount", { words, chars });
    if (el.textContent !== text) el.textContent = text;
  }

  function scheduleStats() {
    if (statsTimer) return;
    statsTimer = window.setTimeout(() => {
      statsTimer = 0;
      updateWordCountLabel();
      updateReadTimeLabel();
      updateCurrentPageFromScroll();
    }, 280);
  }

  function effectiveScale() {
    return Math.min(1.35, Math.max(0.18, fitScale * zoom));
  }

  function updateCurrentPageFromScroll() {
    const stage = $("docsStage");
    if (!stage) return;
    const paper = getPaper();
    const step = (paper.h + PAGE_GAP_PX) * effectiveScale();
    if (step <= 1) return;
    const y = stage.scrollTop + stage.clientHeight * 0.28;
    currentPageView = Math.min(pageCount, Math.max(1, Math.floor(y / step) + 1));
    updatePagePosLabel();
  }

  function detectParagraphStyle() {
    if (!quill) return "normal";
    const range = quill.getSelection();
    if (!range) return $("styleSelect")?.value || "normal";
    const formats = quill.getFormat(range);
    const [leaf] = quill.getLeaf(range.index);
    let el = leaf?.domNode;
    if (el?.nodeType === 3) el = el.parentElement;
    while (el && el !== quill.root) {
      if (el.classList?.contains("wp-title") || el.classList?.contains("wp-doc-title")) return "title";
      if (el.classList?.contains("wp-subtitle")) return "subtitle";
      if (el.classList?.contains("wp-caption")) return "caption";
      if (el.classList?.contains("wp-letter")) return "letter";
      if (el.tagName === "BLOCKQUOTE" || formats.blockquote) return "quote";
      if (el.tagName === "H1" || formats.header === 1) return "h1";
      if (el.tagName === "H2" || formats.header === 2) return "h2";
      if (el.tagName === "H3" || formats.header === 3) return "h3";
      el = el.parentElement;
    }
    if (formats.header === 1) return "h1";
    if (formats.header === 2) return "h2";
    if (formats.header === 3) return "h3";
    if (formats.blockquote) return "quote";
    return "normal";
  }

  function syncStyleSelectFromSelection() {
    const sel = $("styleSelect");
    if (!sel) return;
    const next = detectParagraphStyle();
    if (sel.value !== next) sel.value = next;
  }

  function clearFindHighlights() {
    /* selection-based find — no DOM marks to clear */
  }

  function setFindReplaceUi(enabled) {
    findReplaceMode = !!enabled;
    const bar = $("docsFind");
    bar?.classList.toggle("is-replace", findReplaceMode);
    const replaceField = $("findReplaceField");
    if (replaceField) replaceField.hidden = !findReplaceMode;
    if ($("replaceOneBtn")) $("replaceOneBtn").hidden = !findReplaceMode;
    if ($("replaceAllBtn")) $("replaceAllBtn").hidden = !findReplaceMode;
  }

  function openFindBar(opts = {}) {
    const bar = $("docsFind");
    if (!bar) return;
    setFindReplaceUi(!!opts.replace);
    bar.hidden = false;
    const focusEl = opts.replace && $("replaceInput") && String($("findInput")?.value || "").trim()
      ? $("replaceInput")
      : $("findInput");
    focusEl?.focus();
    focusEl?.select();
    if (String($("findInput")?.value || "").trim()) runFind($("findInput").value);
  }

  function closeFindBar() {
    const bar = $("docsFind");
    if (bar) bar.hidden = true;
    setFindReplaceUi(false);
    findMatches = [];
    findIndex = -1;
    if ($("findCount")) $("findCount").textContent = "";
    quill?.focus();
  }

  function findNeedleLen() {
    return Math.max(1, String($("findInput")?.value || "").trim().length);
  }

  function runFind(query) {
    findMatches = [];
    findIndex = -1;
    const q = String(query || "").trim();
    if (!q || !quill) {
      if ($("findCount")) $("findCount").textContent = "";
      return;
    }
    const hay = String(quill.getText() || "").toLowerCase();
    const needle = q.toLowerCase();
    let from = 0;
    while (from < hay.length) {
      const at = hay.indexOf(needle, from);
      if (at < 0) break;
      findMatches.push(at);
      from = at + Math.max(1, needle.length);
    }
    if ($("findCount")) {
      $("findCount").textContent = findMatches.length
        ? dt("findCount", { n: findMatches.length })
        : dt("findNone");
    }
    if (findMatches.length) focusFindMatch(0);
  }

  function focusFindMatch(i) {
    if (!quill || !findMatches.length) return;
    findIndex = ((i % findMatches.length) + findMatches.length) % findMatches.length;
    const start = findMatches[findIndex];
    const len = findNeedleLen();
    quill.setSelection(start, len, "silent");
    const bounds = quill.getBounds(start, len);
    const stage = $("docsStage");
    if (bounds && stage) {
      const scale = effectiveScale();
      const headerH = measureBandHeight($("docHeader"), layout.showHeader);
      const absY = (headerH + bounds.top) * scale;
      stage.scrollTo({ top: Math.max(0, absY - stage.clientHeight * 0.3), behavior: "smooth" });
    }
    if ($("findCount")) {
      $("findCount").textContent = dt("findPos", {
        cur: findIndex + 1,
        n: findMatches.length,
      });
    }
    updateCurrentPageFromScroll();
  }

  function replaceOne() {
    if (!quill) return;
    const needle = String($("findInput")?.value || "").trim();
    if (!needle) return;
    if (!findMatches.length) {
      runFind(needle);
      if (!findMatches.length) return;
    }
    const start = findMatches[findIndex < 0 ? 0 : findIndex];
    const replacement = String($("replaceInput")?.value || "");
    const keep = findIndex < 0 ? 0 : findIndex;
    suppressTextSideEffects = true;
    try {
      quill.deleteText(start, needle.length, "user");
      if (replacement) quill.insertText(start, replacement, "user");
    } finally {
      suppressTextSideEffects = false;
    }
    markDirty();
    scheduleAutosave();
    schedulePaperSync();
    runFind(needle);
    if (findMatches.length) focusFindMatch(Math.min(keep, findMatches.length - 1));
    else setStatus($("saveStatus"), dt("replaceDone", { n: 1 }), "ok");
  }

  function replaceAll() {
    if (!quill) return;
    const needle = String($("findInput")?.value || "").trim();
    if (!needle) return;
    runFind(needle);
    if (!findMatches.length) return;
    const replacement = String($("replaceInput")?.value || "");
    const count = findMatches.length;
    suppressTextSideEffects = true;
    try {
      for (let i = findMatches.length - 1; i >= 0; i -= 1) {
        const start = findMatches[i];
        quill.deleteText(start, needle.length, "user");
        if (replacement) quill.insertText(start, replacement, "user");
      }
    } finally {
      suppressTextSideEffects = false;
    }
    markDirty();
    scheduleAutosave();
    schedulePaperSync();
    runFind(needle);
    setStatus($("saveStatus"), dt("replaceDone", { n: count }), "ok");
  }

  function buildTablePicker() {
    const grid = $("tablePickerGrid");
    if (!grid || grid.childElementCount) return;
    const maxR = 8;
    const maxC = 8;
    for (let r = 1; r <= maxR; r += 1) {
      for (let c = 1; c <= maxC; c += 1) {
        const cell = document.createElement("button");
        cell.type = "button";
        cell.className = "table-picker-cell";
        cell.dataset.rows = String(r);
        cell.dataset.cols = String(c);
        cell.setAttribute("aria-label", `${r}×${c}`);
        cell.addEventListener("mouseenter", () => {
          grid.querySelectorAll(".table-picker-cell").forEach((el) => {
            const er = Number(el.dataset.rows);
            const ec = Number(el.dataset.cols);
            el.classList.toggle("is-hot", er <= r && ec <= c);
          });
          if ($("tablePickerLabel")) $("tablePickerLabel").textContent = `${r} × ${c}`;
        });
        cell.addEventListener("click", () => {
          insertTable(r, c);
          closeTablePicker();
        });
        grid.appendChild(cell);
      }
    }
    grid.style.gridTemplateColumns = `repeat(${maxC}, 1fr)`;
  }

  function openTablePicker() {
    buildTablePicker();
    const panel = $("tablePicker");
    const btn = $("insertTableBtn");
    if (!panel) return;
    panel.hidden = false;
    btn?.setAttribute("aria-expanded", "true");
  }

  function closeTablePicker() {
    const panel = $("tablePicker");
    if (panel) panel.hidden = true;
    $("insertTableBtn")?.setAttribute("aria-expanded", "false");
  }

  let bubbleRaf = 0;
  let cmdPaletteIndex = 0;
  let cmdPaletteItems = [];

  function hideSelBubble() {
    const bubble = $("selBubble");
    if (bubble) bubble.hidden = true;
  }

  function syncSelBubbleActive() {
    const bubble = $("selBubble");
    if (!bubble || !quill) return;
    const formats = quill.getFormat();
    bubble.querySelectorAll("[data-fmt]").forEach((btn) => {
      const fmt = btn.getAttribute("data-fmt");
      const on = fmt === "link" ? !!formats.link : !!formats[fmt];
      btn.classList.toggle("is-active", on);
    });
    bubble.querySelectorAll("[data-align]").forEach((btn) => {
      const align = btn.getAttribute("data-align") || "left";
      const cur = formats.align || "left";
      btn.classList.toggle("is-active", cur === align || (!formats.align && align === "left"));
    });
  }

  function updateSelBubble() {
    const bubble = $("selBubble");
    if (!bubble || !quill) return;
    const range = quill.getSelection();
    if (!range || range.length < 1) {
      hideSelBubble();
      return;
    }
    if ($("cmdPalette") && !$("cmdPalette").hidden) {
      hideSelBubble();
      return;
    }
    // Use native selection rect — correct even with scaled paper.
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) {
      hideSelBubble();
      return;
    }
    const rect = sel.getRangeAt(0).getBoundingClientRect();
    if (!rect || (rect.width === 0 && rect.height === 0)) {
      hideSelBubble();
      return;
    }
    const left = Math.min(window.innerWidth - 24, Math.max(24, rect.left + rect.width / 2));
    const top = Math.max(12, rect.top - 10);
    bubble.hidden = false;
    bubble.style.left = `${left}px`;
    bubble.style.top = `${top}px`;
    bubble.style.transform = "translate(-50%, -100%)";
    syncSelBubbleActive();
    if (window.DocsIcons) window.DocsIcons.mountAll(bubble, true);
  }

  function scheduleSelBubble() {
    if (bubbleRaf) return;
    bubbleRaf = requestAnimationFrame(() => {
      bubbleRaf = 0;
      updateSelBubble();
    });
  }

  function applyBubbleFormat(fmt) {
    if (!quill) return;
    const range = quill.getSelection(true);
    if (!range) return;
    if (fmt === "link") {
      const cur = quill.getFormat(range).link;
      if (cur) {
        quill.format("link", false);
      } else {
        const url = window.prompt(dt("linkPrompt"), "https://");
        if (url) quill.format("link", url);
      }
    } else if (fmt === "blockquote") {
      quill.format("blockquote", !quill.getFormat(range).blockquote);
    } else {
      quill.format(fmt, !quill.getFormat(range)[fmt]);
    }
    markDirty();
    scheduleAutosave();
    syncSelBubbleActive();
  }

  function applyBubbleAlign(align) {
    if (!quill) return;
    const range = quill.getSelection(true);
    if (!range) return;
    quill.format("align", align === "left" ? false : align);
    markDirty();
    scheduleAutosave();
    syncSelBubbleActive();
  }

  function commandCatalog() {
    return [
      { id: "save", label: dt("save"), hint: "Ctrl+S", icon: "save", run: () => saveDoc().catch(() => {}) },
      { id: "find", label: dt("find"), hint: "Ctrl+F", icon: "search", run: () => openFindBar() },
      { id: "replace", label: dt("replace"), hint: "Ctrl+H", icon: "search", run: () => openFindBar({ replace: true }) },
      { id: "undo", label: dt("undo"), hint: "Ctrl+Z", icon: "undo", run: () => quill?.history?.undo() },
      { id: "redo", label: dt("redo"), hint: "Ctrl+Y", icon: "redo", run: () => quill?.history?.redo() },
      { id: "new", label: dt("newDoc"), hint: "", icon: "plus", run: () => createBlank().catch(() => {}) },
      { id: "table", label: dt("table"), hint: "", icon: "table", run: () => openTablePicker() },
      {
        id: "pagebreak",
        label: dt("pageBreak"),
        hint: "",
        icon: "pageBreak",
        run: () =>
          insertHtmlAtCursor(
            `<p class="wp-page-break" data-label="${escapeHtml(dt("pageBreak"))}"><br></p><p><br></p>`,
          ),
      },
      { id: "hr", label: dt("hr"), hint: "", icon: "hr", run: () => insertHtmlAtCursor("<hr /><p><br></p>") },
      { id: "sign", label: dt("snSign"), hint: "", icon: "signature", run: () => insertSignatureBlock() },
      { id: "shortcuts", label: dt("shortcuts"), hint: "Ctrl+/", icon: "command", run: () => openShortcutsModal() },
      {
        id: "focus",
        label: dt("focus"),
        hint: "",
        icon: "zoomFit",
        run: () => {
          toggleFocusMode();
        },
      },
      {
        id: "zoomfit",
        label: dt("zoomFit"),
        hint: "",
        icon: "zoomFit",
        run: () => resetAutoFit(),
      },
      {
        id: "zoom100",
        label: "100%",
        hint: "",
        icon: "zoomIn",
        run: () => {
          autoFit = false;
          fitScale = 1;
          zoom = 1;
          applyFitScale();
        },
      },
      {
        id: "image",
        label: dt("insertImage"),
        hint: "",
        icon: "image",
        run: () => openImagePicker(),
      },
      { id: "h1", label: dt("styleH1"), hint: "", icon: "quote", run: () => applyParagraphStyle("h1") },
      { id: "h2", label: dt("styleH2"), hint: "", icon: "quote", run: () => applyParagraphStyle("h2") },
      { id: "normal", label: dt("styleNormal"), hint: "", icon: "clean", run: () => applyParagraphStyle("normal") },
      { id: "saveTemplate", label: dt("saveAsTemplate"), hint: "", icon: "save", run: () => saveCurrentAsTemplate() },
      {
        id: "shareLink",
        label: dt("shareLink"),
        hint: "",
        icon: "link",
        run: () => createShareLink().catch(() => {}),
      },
      {
        id: "copyEditorLink",
        label: dt("copyEditorLink"),
        hint: "",
        icon: "link",
        run: () => copyEditorLink().catch(() => {}),
      },
      {
        id: "importDocx",
        label: dt("importDocx"),
        hint: "",
        icon: "pageBreak",
        run: () => pickImportDocx(),
      },
      {
        id: "insertToc",
        label: dt("insertToc"),
        hint: "",
        icon: "listBullet",
        run: () => insertTableOfContents(),
      },
      {
        id: "review",
        label: dt("workflowNext"),
        hint: "",
        icon: "command",
        run: () => openPreflight("review"),
      },
      {
        id: "approve",
        label: dt("workflowApprove"),
        hint: "",
        icon: "command",
        run: () => openPreflight("approve"),
      },
      {
        id: "print",
        label: dt("printPreview"),
        hint: "Ctrl+P",
        icon: "print",
        run: () => openPrintPreviewPdf().catch(() => {}),
      },
      {
        id: "comments",
        label: dt("commentsPanel"),
        hint: "",
        icon: "comment",
        run: () => {
          const panel = $("docComments");
          if (!panel) return;
          panel.hidden = false;
          $("commentsToggleBtn")?.setAttribute("aria-expanded", "true");
          renderCommentsPanel();
          scheduleFit();
        },
      },
      {
        id: "comment",
        label: dt("addComment"),
        hint: "",
        icon: "comment",
        run: () => addCommentOnSelection(),
      },
    ];
  }

  function renderCmdPaletteList(filter) {
    const list = $("cmdPaletteList");
    if (!list) return;
    const q = String(filter || "")
      .trim()
      .toLowerCase();
    cmdPaletteItems = commandCatalog().filter((c) => {
      if (!q) return true;
      return c.label.toLowerCase().includes(q) || c.id.includes(q);
    });
    cmdPaletteIndex = Math.min(cmdPaletteIndex, Math.max(0, cmdPaletteItems.length - 1));
    list.innerHTML = cmdPaletteItems
      .map((c, i) => {
        const ico = window.DocsIcons?.svg(c.icon) || "";
        return (
          `<li class="cmd-palette-item${i === cmdPaletteIndex ? " is-active" : ""}" role="option" data-idx="${i}">` +
          `<span class="wp-ico">${ico}</span>` +
          `<span class="cmd-palette-label">${escapeHtml(c.label)}</span>` +
          (c.hint ? `<kbd>${escapeHtml(c.hint)}</kbd>` : "") +
          `</li>`
        );
      })
      .join("");
  }

  function openCmdPalette() {
    const host = $("cmdPalette");
    if (!host) return;
    hideSelBubble();
    closeTablePicker();
    host.hidden = false;
    cmdPaletteIndex = 0;
    if ($("cmdPaletteInput")) $("cmdPaletteInput").value = "";
    renderCmdPaletteList("");
    if (window.DocsIcons) window.DocsIcons.mountAll(host, true);
    $("cmdPaletteInput")?.focus();
  }

  function closeCmdPalette() {
    const host = $("cmdPalette");
    if (host) host.hidden = true;
    cmdPaletteItems = [];
    quill?.focus();
  }

  function runCmdPaletteItem(idx) {
    const item = cmdPaletteItems[idx];
    if (!item) return;
    closeCmdPalette();
    try {
      item.run();
    } catch {
      /* ignore command errors */
    }
  }

  let slashIndex = 0;
  let slashItems = [];
  let slashStart = -1;
  let outlineTimer = 0;

  function slashCatalog() {
    return [
      { id: "h1", label: dt("styleH1"), icon: "quote", run: () => applyParagraphStyle("h1") },
      { id: "h2", label: dt("styleH2"), icon: "quote", run: () => applyParagraphStyle("h2") },
      { id: "h3", label: dt("styleH3"), icon: "quote", run: () => applyParagraphStyle("h3") },
      { id: "quote", label: dt("styleQuote"), icon: "quote", run: () => applyParagraphStyle("quote") },
      { id: "bullet", label: dt("slashBullet"), icon: "listBullet", run: () => quill?.format("list", "bullet") },
      { id: "ordered", label: dt("slashOrdered"), icon: "listOrdered", run: () => quill?.format("list", "ordered") },
      { id: "table", label: dt("table"), icon: "table", run: () => insertTable(3, 3) },
      { id: "image", label: dt("insertImage"), icon: "image", run: () => openImagePicker() },
      {
        id: "pagebreak",
        label: dt("pageBreak"),
        icon: "pageBreak",
        run: () =>
          insertHtmlAtCursor(
            `<p class="wp-page-break" data-label="${escapeHtml(dt("pageBreak"))}"><br></p><p><br></p>`,
          ),
      },
      { id: "hr", label: dt("hr"), icon: "hr", run: () => insertHtmlAtCursor("<hr /><p><br></p>") },
      { id: "sign", label: dt("snSign"), icon: "signature", run: () => insertSignatureBlock() },
      { id: "commands", label: dt("cmdPalette"), icon: "command", run: () => openCmdPalette() },
      { id: "comment", label: dt("addComment"), icon: "comment", run: () => addCommentOnSelection() },
    ];
  }

  function hideSlashMenu() {
    const menu = $("slashMenu");
    if (menu) menu.hidden = true;
    slashItems = [];
    slashStart = -1;
  }

  function renderSlashMenu(filter) {
    const menu = $("slashMenu");
    if (!menu) return;
    const q = String(filter || "")
      .trim()
      .toLowerCase();
    slashItems = slashCatalog().filter((c) => !q || c.label.toLowerCase().includes(q) || c.id.includes(q));
    slashIndex = Math.min(slashIndex, Math.max(0, slashItems.length - 1));
    menu.innerHTML = slashItems
      .map((c, i) => {
        const ico = window.DocsIcons?.svg(c.icon) || "";
        return (
          `<button type="button" class="slash-item${i === slashIndex ? " is-active" : ""}" role="option" data-idx="${i}">` +
          `<span class="wp-ico">${ico}</span>` +
          `<span>${escapeHtml(c.label)}</span>` +
          `</button>`
        );
      })
      .join("");
    menu.hidden = slashItems.length === 0;
    if (window.DocsIcons) window.DocsIcons.mountAll(menu, true);
  }

  function positionSlashMenu() {
    const menu = $("slashMenu");
    if (!menu || !quill || slashStart < 0) return;
    const bounds = quill.getBounds(slashStart, 1);
    if (!bounds) return;
    const editorRect = quill.root.getBoundingClientRect();
    const scale = effectiveScale();
    // Approximate with native caret when available
    const sel = window.getSelection();
    let left = editorRect.left + 24;
    let top = editorRect.top + 24;
    if (sel && sel.rangeCount) {
      const rect = sel.getRangeAt(0).getBoundingClientRect();
      if (rect && (rect.width || rect.height)) {
        left = rect.left;
        top = rect.bottom + 8;
      } else {
        left = editorRect.left + bounds.left * scale;
        top = editorRect.top + bounds.bottom * scale + 8;
      }
    }
    menu.style.left = `${Math.min(window.innerWidth - 280, Math.max(12, left))}px`;
    menu.style.top = `${Math.min(window.innerHeight - 220, Math.max(12, top))}px`;
  }

  function openSlashMenu(startIndex, filter) {
    slashStart = startIndex;
    slashIndex = 0;
    hideSelBubble();
    renderSlashMenu(filter);
    positionSlashMenu();
  }

  function consumeSlashTrigger() {
    if (!quill || slashStart < 0) return;
    const range = quill.getSelection(true);
    if (!range) return;
    const len = Math.max(0, range.index - slashStart);
    if (len > 0) quill.deleteText(slashStart, len, "user");
    quill.setSelection(slashStart, 0, "silent");
  }

  function runSlashItem(idx) {
    const item = slashItems[idx];
    if (!item) return;
    consumeSlashTrigger();
    hideSlashMenu();
    try {
      item.run();
    } catch {
      /* ignore */
    }
    markDirty();
    scheduleOutline();
  }

  function detectSlashFromTextChange(delta, source) {
    if (source !== "user" || !quill) return;
    const range = quill.getSelection();
    if (!range || range.length) {
      hideSlashMenu();
      hideMergeMenu();
      return;
    }
    const idx = range.index;
    const look = Math.min(48, idx);
    const text = quill.getText(Math.max(0, idx - look), look);
    const mergeMatch = /\{\{([a-zA-Z0-9_.-]*)$/.exec(text);
    if (mergeMatch) {
      hideSlashMenu();
      const filter = mergeMatch[1] || "";
      const start = idx - filter.length - 2;
      openMergeMenu(start, filter);
      return;
    }
    hideMergeMenu();
    const m = /(?:^|\n)\/([^\n]*)$/.exec(text);
    if (!m) {
      hideSlashMenu();
      return;
    }
    const filter = m[1] || "";
    const start = idx - filter.length - 1;
    openSlashMenu(start, filter);
  }

  const MERGE_FIELD_DEFS = [
    { token: "{{company.name}}", labelKey: "chipCompany" },
    { token: "{{company.address}}", labelKey: "chipAddress" },
    { token: "{{company.email}}", labelKey: "chipEmail" },
    { token: "{{company.contact}}", labelKey: "chipContact" },
    { token: "{{worker.name}}", labelKey: "chipName" },
    { token: "{{worker.badge}}", labelKey: "chipBadge" },
    { token: "{{site.name}}", labelKey: "chipSite" },
    { token: "{{manager.name}}", labelKey: "chipManager" },
    { token: "{{date.today}}", labelKey: "chipDate" },
  ];

  let mergeItems = [];
  let mergeIndex = 0;
  let mergeStart = -1;

  function mergeFieldLabel(def) {
    const translated = dt(def.labelKey);
    if (translated && translated !== def.labelKey) return translated;
    const fallbacks = {
      chipContact: "Kontakt",
      chipBadge: "Badge",
      chipManager: "Leitung",
    };
    return fallbacks[def.labelKey] || def.token;
  }

  function mergeCatalog() {
    return MERGE_FIELD_DEFS.map((d) => ({
      token: d.token,
      label: `${mergeFieldLabel(d)} · ${d.token}`,
      run: () => insertMergeToken(d.token),
    }));
  }

  function hideMergeMenu() {
    const menu = $("mergeMenu");
    if (menu) menu.hidden = true;
    mergeItems = [];
    mergeStart = -1;
  }

  function renderMergeMenu(filter) {
    const menu = $("mergeMenu");
    if (!menu) return;
    const q = String(filter || "")
      .trim()
      .toLowerCase();
    mergeItems = mergeCatalog().filter(
      (c) => !q || c.token.toLowerCase().includes(q) || c.label.toLowerCase().includes(q),
    );
    mergeIndex = Math.min(mergeIndex, Math.max(0, mergeItems.length - 1));
    menu.innerHTML = mergeItems
      .map((c, i) => {
        return (
          `<button type="button" class="slash-item${i === mergeIndex ? " is-active" : ""}" role="option" data-merge-idx="${i}">` +
          `<span class="merge-token">${escapeHtml(c.token)}</span>` +
          `<span>${escapeHtml(c.label.split(" · ")[0] || c.label)}</span>` +
          `</button>`
        );
      })
      .join("");
    menu.hidden = mergeItems.length === 0;
  }

  function positionMergeMenu() {
    const menu = $("mergeMenu");
    if (!menu || !quill || mergeStart < 0) return;
    const bounds = quill.getBounds(mergeStart, 1);
    if (!bounds) return;
    const editorRect = quill.root.getBoundingClientRect();
    const scale = effectiveScale();
    const sel = window.getSelection();
    let left = editorRect.left + 24;
    let top = editorRect.top + 24;
    if (sel && sel.rangeCount) {
      const rect = sel.getRangeAt(0).getBoundingClientRect();
      if (rect && (rect.width || rect.height)) {
        left = rect.left;
        top = rect.bottom + 8;
      } else {
        left = editorRect.left + bounds.left * scale;
        top = editorRect.top + bounds.bottom * scale + 8;
      }
    }
    menu.style.left = `${Math.min(window.innerWidth - 300, Math.max(12, left))}px`;
    menu.style.top = `${Math.min(window.innerHeight - 220, Math.max(12, top))}px`;
  }

  function openMergeMenu(startIndex, filter) {
    mergeStart = startIndex;
    mergeIndex = 0;
    hideSelBubble();
    hideSlashMenu();
    renderMergeMenu(filter);
    positionMergeMenu();
  }

  function consumeMergeTrigger() {
    if (!quill || mergeStart < 0) return;
    const range = quill.getSelection(true);
    if (!range) return;
    const len = Math.max(0, range.index - mergeStart);
    if (len > 0) quill.deleteText(mergeStart, len, "user");
    quill.setSelection(mergeStart, 0, "silent");
  }

  function insertMergeToken(token) {
    if (!quill) return;
    const html = wrapMergePlaceholders(String(token || ""));
    if (mergeStart >= 0) {
      consumeMergeTrigger();
      quill.clipboard.dangerouslyPasteHTML(mergeStart, html, "user");
      quill.setSelection(mergeStart + String(token || "").length, 0, "user");
    } else {
      insertHtmlAtCursor(html);
    }
    hideMergeMenu();
    markDirty();
  }

  function runMergeItem(idx) {
    const item = mergeItems[idx];
    if (!item) return;
    try {
      item.run();
    } catch {
      /* ignore */
    }
  }

  function shortcutsCatalog() {
    return [
      { keys: "Ctrl+S", label: dt("save") },
      { keys: "Ctrl+F", label: dt("find") },
      { keys: "Ctrl+H", label: dt("replace") },
      { keys: "Ctrl+K", label: dt("cmdPalette") },
      { keys: "Ctrl+/", label: dt("shortcuts") },
      { keys: "Ctrl+P", label: dt("printPreview") },
      { keys: "Ctrl+D", label: dt("duplicate") || "Duplizieren" },
      { keys: "Ctrl+Z / Y", label: `${dt("undo")} / ${dt("redo")}` },
      { keys: "/", label: dt("slashMenu") },
      { keys: "{{", label: dt("mergeMenu") },
      { keys: "Esc", label: dt("close") },
    ];
  }

  function openShortcutsModal() {
    const modal = $("shortcutsModal");
    const body = $("shortcutsBody");
    if (!modal || !body) return;
    body.innerHTML = shortcutsCatalog()
      .map(
        (row) =>
          `<div class="shortcuts-row"><kbd>${escapeHtml(row.keys)}</kbd><span>${escapeHtml(row.label)}</span></div>`,
      )
      .join("");
    modal.hidden = false;
    window.DocsIcons?.mountAll(modal, true);
  }

  function closeShortcutsModal() {
    const modal = $("shortcutsModal");
    if (modal) modal.hidden = true;
  }

  const OFFLINE_PREFIX = "baupass-docs-offline:";
  let offlineTimer = 0;
  let pendingOfflineDraft = null;

  function offlineDraftStorageKey(docId) {
    const cid = activeCompanyId() || "none";
    const id = docId || currentDoc?.id || "new";
    return `${OFFLINE_PREFIX}${cid}:${id}`;
  }

  function persistOfflineDraft() {
    try {
      const payload = {
        ts: Date.now(),
        docId: currentDoc?.id || "",
        companyId: activeCompanyId() || "",
        title: ($("docTitle")?.value || "").trim(),
        mode: $("docMode")?.value || "general",
        html: getHtml(),
        headerHtml: getHeaderHtml(),
        footerHtml: getFooterHtml(),
        layout: { ...layout },
      };
      localStorage.setItem(offlineDraftStorageKey(payload.docId || "new"), JSON.stringify(payload));
      if (payload.docId) {
        localStorage.setItem(offlineDraftStorageKey("new"), JSON.stringify(payload));
      }
    } catch {
      /* quota / private mode */
    }
  }

  function scheduleOfflineDraft() {
    if (offlineTimer) return;
    offlineTimer = window.setTimeout(() => {
      offlineTimer = 0;
      if (dirty) persistOfflineDraft();
    }, 900);
  }

  function clearOfflineDraft(docId) {
    try {
      localStorage.removeItem(offlineDraftStorageKey(docId || currentDoc?.id || "new"));
      if (docId) localStorage.removeItem(offlineDraftStorageKey("new"));
    } catch {
      /* ignore */
    }
  }

  function readOfflineDraft(docId) {
    try {
      const raw = localStorage.getItem(offlineDraftStorageKey(docId || currentDoc?.id || "new"));
      if (!raw) return null;
      const data = JSON.parse(raw);
      if (!data?.html || !data?.ts) return null;
      return data;
    } catch {
      return null;
    }
  }

  function hideOfflineBanner() {
    const banner = $("offlineBanner");
    if (banner) banner.hidden = true;
    pendingOfflineDraft = null;
  }

  function showOfflineBanner(draft) {
    pendingOfflineDraft = draft;
    const banner = $("offlineBanner");
    const text = $("offlineBannerText");
    if (!banner || !text || !draft) return;
    text.textContent = dt("offlineFound", {
      when: formatRelativeWhen(new Date(draft.ts).toISOString()),
    });
    banner.hidden = false;
  }

  function applyOfflineDraft(draft) {
    if (!draft) return;
    if (draft.title && $("docTitle")) $("docTitle").value = draft.title;
    if (draft.mode && $("docMode")) $("docMode").value = draft.mode;
    if (draft.layout) Object.assign(layout, draft.layout);
    applyLayoutToDom();
    if (draft.headerHtml != null && $("docHeader")) $("docHeader").innerHTML = draft.headerHtml;
    if (draft.footerHtml != null && $("docFooter")) $("docFooter").innerHTML = draft.footerHtml;
    setHtml(draft.html || "<p><br></p>");
    hideOfflineBanner();
    dirty = true;
    setStatus($("saveStatus"), dt("offlineRestored"), "ok");
    schedulePaperSync({ force: true, fit: true });
    scheduleOutline();
  }

  function maybeOfferOfflineDraft(doc) {
    hideOfflineBanner();
    const draft = readOfflineDraft(doc?.id || "new");
    if (!draft) return;
    const serverTs = Date.parse(String(doc?.updated_at || "")) || 0;
    if (serverTs && draft.ts <= serverTs + 2000) {
      clearOfflineDraft(doc?.id || "new");
      return;
    }
    // Same content → ignore
    if (compactHtml(draft.html) === compactHtml(getHtml())) {
      clearOfflineDraft(doc?.id || "new");
      return;
    }
    showOfflineBanner(draft);
  }

  function openImagePicker() {
    $("insertImageInput")?.click();
  }

  function insertImageFromFile(file) {
    if (!quill || !file || !String(file.type || "").startsWith("image/")) return;
    if (file.size > 4.5 * 1024 * 1024) {
      setStatus($("saveStatus"), dt("imageTooBig"), "err");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result || "");
      if (!dataUrl) return;
      const range = quill.getSelection(true) || { index: Math.max(0, quill.getLength() - 1) };
      quill.insertEmbed(range.index, "image", dataUrl, "user");
      quill.insertText(range.index + 1, "\n", "user");
      // Default medium width for nicer layout.
      requestAnimationFrame(() => {
        const imgs = quill.root.querySelectorAll("img");
        const last = imgs[imgs.length - 1];
        if (last && !last.className.includes("wp-img-")) {
          last.classList.add("wp-img-md");
        }
        schedulePaperSync();
      });
      quill.setSelection(range.index + 2, 0, "user");
      markDirty();
      scheduleAutosave();
      scheduleOutline();
      setStatus($("saveStatus"), dt("imageInserted"), "ok");
    };
    reader.readAsDataURL(file);
  }

  let activeImageEl = null;
  let diffVersionId = "";

  function hideImgSizeBar() {
    const bar = $("imgSizeBar");
    if (bar) bar.hidden = true;
    if (activeImageEl) activeImageEl.classList.remove("wp-img-active");
    activeImageEl = null;
  }

  function showImgSizeBar(img) {
    const bar = $("imgSizeBar");
    if (!bar || !img) return;
    if (activeImageEl) activeImageEl.classList.remove("wp-img-active");
    activeImageEl = img;
    img.classList.add("wp-img-active");
    if (!/wp-img-(sm|md|lg|full)/.test(img.className)) img.classList.add("wp-img-md");
    const rect = img.getBoundingClientRect();
    bar.hidden = false;
    bar.style.left = `${Math.min(window.innerWidth - 20, Math.max(20, rect.left + rect.width / 2))}px`;
    bar.style.top = `${Math.max(12, rect.top - 10)}px`;
    bar.style.transform = "translate(-50%, -100%)";
    bar.querySelectorAll("[data-img-size]").forEach((btn) => {
      const size = btn.getAttribute("data-img-size");
      btn.classList.toggle("is-active", img.classList.contains(`wp-img-${size}`));
    });
  }

  function setImageSize(size) {
    if (!activeImageEl) return;
    activeImageEl.classList.remove("wp-img-sm", "wp-img-md", "wp-img-lg", "wp-img-full");
    activeImageEl.classList.add(`wp-img-${size}`);
    markDirty();
    scheduleAutosave();
    schedulePaperSync();
    showImgSizeBar(activeImageEl);
  }

  function addCommentOnSelection() {
    if (!quill) return;
    const range = quill.getSelection(true);
    if (!range || range.length < 1) {
      setStatus($("saveStatus"), dt("commentNeedSelection"), "err");
      return;
    }
    const existing = quill.getFormat(range).wpComment;
    const preset = typeof existing === "string" ? parseCommentMeta(existing).text : "";
    const note = window.prompt(dt("commentPrompt"), preset || "");
    if (note === null) return;
    if (!String(note).trim()) {
      quill.formatText(range.index, range.length, "wpComment", false, "user");
    } else {
      const assignee = window.prompt(dt("commentAssigneePrompt"), "") || "";
      quill.formatText(
        range.index,
        range.length,
        "wpComment",
        serializeCommentMeta({ text: String(note).trim(), assignee: String(assignee).trim(), done: false }),
        "user",
      );
    }
    markDirty();
    scheduleAutosave();
    scheduleSelBubble();
    scheduleComments();
    const panel = $("docComments");
    if (panel && panel.hidden) {
      panel.hidden = false;
      $("commentsToggleBtn")?.setAttribute("aria-expanded", "true");
      renderCommentsPanel();
      scheduleFit();
    }
  }

  function collectComments() {
    if (!quill) return [];
    const delta = quill.getContents();
    const out = [];
    let index = 0;
    (delta.ops || []).forEach((op) => {
      const insert = op.insert;
      const len = typeof insert === "string" ? insert.length : 1;
      const note = op.attributes?.wpComment;
      if (note) {
        const text = typeof insert === "string" ? insert.replace(/\s+/g, " ") : "";
        const meta = parseCommentMeta(note);
        const last = out[out.length - 1];
        if (last && last.raw === note && last.index + last.length === index) {
          last.length += len;
          last.excerpt = `${last.excerpt}${text}`.slice(0, 120);
        } else {
          out.push({
            index,
            length: len,
            note: meta.text,
            assignee: meta.assignee,
            done: meta.done,
            raw: String(note),
            excerpt: text.slice(0, 120),
          });
        }
      }
      index += len;
    });
    return out;
  }

  function renderCommentsPanel() {
    const list = $("docCommentsList");
    const empty = $("docCommentsEmpty");
    if (!list) return;
    const all = collectComments();
    const items = all.filter((c) => {
      if (commentsFilter === "done") return c.done;
      if (commentsFilter === "open") return !c.done;
      return true;
    });
    list.innerHTML = items
      .map((c) => {
        const idx = all.indexOf(c);
        const excerpt = String(c.excerpt || "").trim() || "…";
        const who = c.assignee ? `<em class="doc-comments-assignee">@${escapeHtml(c.assignee)}</em>` : "";
        return (
          `<li class="doc-comments-item${c.done ? " is-done" : ""}">` +
          `<button type="button" class="doc-comments-jump" data-cmt="${idx}">` +
          `<strong class="doc-comments-note">${escapeHtml(c.note)}</strong>${who}` +
          `<span class="doc-comments-excerpt">${escapeHtml(excerpt)}</span>` +
          `</button>` +
          `<div class="doc-comments-actions">` +
          `<button type="button" class="cmd quiet" data-cmt-assign="${idx}">${escapeHtml(dt("commentAssign"))}</button>` +
          `<button type="button" class="cmd quiet" data-cmt-edit="${idx}">${escapeHtml(dt("commentEdit"))}</button>` +
          `<button type="button" class="cmd quiet" data-cmt-resolve="${idx}">${escapeHtml(c.done ? dt("commentReopen") : dt("commentResolve"))}</button>` +
          `</div>` +
          `</li>`
        );
      })
      .join("");
    if (empty) empty.hidden = items.length > 0;
    list.hidden = items.length === 0;
    document.querySelectorAll("[data-cmt-filter]").forEach((btn) => {
      btn.classList.toggle("active", btn.getAttribute("data-cmt-filter") === commentsFilter);
    });
  }

  function scheduleComments() {
    if (commentsTimer) return;
    commentsTimer = window.setTimeout(() => {
      commentsTimer = 0;
      if ($("docComments") && !$("docComments").hidden) renderCommentsPanel();
    }, 220);
  }

  function jumpToComment(index) {
    const items = collectComments();
    const item = items[index];
    if (!item || !quill) return;
    quill.setSelection(item.index, item.length, "silent");
    const bounds = quill.getBounds(item.index, item.length);
    const stage = $("docsStage");
    if (bounds && stage) {
      const scale = effectiveScale();
      const headerH = measureBandHeight($("docHeader"), layout.showHeader);
      const absY = (headerH + bounds.top) * scale;
      stage.scrollTo({ top: Math.max(0, absY - stage.clientHeight * 0.3), behavior: "smooth" });
    }
    scheduleSelBubble();
  }

  function editCommentAt(index) {
    const items = collectComments();
    const item = items[index];
    if (!item || !quill) return;
    const note = window.prompt(dt("commentPrompt"), item.note || "");
    if (note === null) return;
    if (!String(note).trim()) {
      quill.formatText(item.index, item.length, "wpComment", false, "user");
    } else {
      quill.formatText(
        item.index,
        item.length,
        "wpComment",
        serializeCommentMeta({ text: String(note).trim(), assignee: item.assignee || "", done: !!item.done }),
        "user",
      );
    }
    markDirty();
    scheduleAutosave();
    renderCommentsPanel();
  }

  function assignCommentAt(index) {
    const items = collectComments();
    const item = items[index];
    if (!item || !quill) return;
    const who = window.prompt(dt("commentAssigneePrompt"), item.assignee || "");
    if (who === null) return;
    quill.formatText(
      item.index,
      item.length,
      "wpComment",
      serializeCommentMeta({ text: item.note, assignee: String(who).trim(), done: !!item.done }),
      "user",
    );
    markDirty();
    scheduleAutosave();
    renderCommentsPanel();
  }

  function resolveCommentAt(index) {
    const items = collectComments();
    const item = items[index];
    if (!item || !quill) return;
    if (item.done) {
      quill.formatText(
        item.index,
        item.length,
        "wpComment",
        serializeCommentMeta({ text: item.note, assignee: item.assignee || "", done: false }),
        "user",
      );
    } else {
      quill.formatText(
        item.index,
        item.length,
        "wpComment",
        serializeCommentMeta({ text: item.note, assignee: item.assignee || "", done: true }),
        "user",
      );
    }
    markDirty();
    scheduleAutosave();
    renderCommentsPanel();
  }

  function openPrintPreview(opts = {}) {
    const modal = $("printPreviewModal");
    const body = $("printPreviewBody");
    const stack = $("paperStack");
    if (!modal || !body || !stack) return;
    hideAiOperatorForPrint(true);
    const showMarks = !!opts.showMarks;
    const openPh = collectOpenPlaceholders();
    if (openPh.length) {
      renderPlaceholderCheck();
      setStatus(
        $("saveStatus"),
        showMarks ? dt("placeholdersOpen", { n: openPh.length }) : dt("printCleanWarn", { n: openPh.length }),
        showMarks ? "err" : "",
      );
    }
    body.innerHTML = "";
    const clone = stack.cloneNode(true);
    clone.removeAttribute("id");
    clone.classList.add("print-preview-stack");
    if (!showMarks) clone.classList.add("clean-print");
    clone.querySelectorAll("[id]").forEach((el) => el.removeAttribute("id"));
    clone.querySelectorAll("[contenteditable]").forEach((el) => el.removeAttribute("contenteditable"));
    clone.querySelector(".page-frames")?.remove();
    clone.querySelectorAll(".ql-clipboard, .ql-tooltip").forEach((el) => el.remove());
    // Drop empty header/footer so "Kopfzeile" ghost never appears in preview/print.
    clone.querySelectorAll(".docs-hf").forEach((el) => {
      const text = String(el.textContent || "").replace(/\u00a0/g, " ").trim();
      if (!text) {
        el.innerHTML = "";
        el.classList.add("is-empty-hf");
      }
    });
    if (showMarks) {
      const walk = document.createTreeWalker(clone, NodeFilter.SHOW_TEXT);
      const textNodes = [];
      while (walk.nextNode()) textNodes.push(walk.currentNode);
      textNodes.forEach((node) => {
        const raw = node.nodeValue || "";
        if (!/\{\{[^}]+\}\}/.test(raw)) return;
        const wrap = document.createElement("span");
        wrap.innerHTML = raw.replace(
          /(\{\{\s*[a-zA-Z0-9_.-]+\s*\}\})/g,
          '<mark class="wp-ph-warn">$1</mark>',
        );
        node.parentNode?.replaceChild(wrap, node);
      });
    }
    body.appendChild(clone);
    const paper = getPaper();
    if ($("printPreviewMeta")) {
      $("printPreviewMeta").textContent = dt("printPreviewMeta", {
        size: paper.label,
        pages: pageCount,
      });
    }
    modal.hidden = false;
    window.DocsIcons?.mountAll(modal, true);
  }

  async function runCleanBrowserPrint() {
    document.body.classList.add("docs-printing-locked", "docs-print-clean");
    hideAiOperatorForPrint(true);
    try {
      const modal = $("printPreviewModal");
      const body = $("printPreviewBody");
      let iframe = body?.querySelector("iframe.print-pdf-frame");
      if (!(iframe && modal && !modal.hidden)) {
        await openPrintPreviewPdf();
        iframe = body?.querySelector("iframe.print-pdf-frame");
      }
      if (iframe) {
        const printFrame = () => {
          try {
            iframe.contentWindow?.focus();
            iframe.contentWindow?.print();
          } catch {
            /* ignore */
          }
          window.setTimeout(() => {
            document.body.classList.remove("docs-printing-locked", "docs-print-clean");
          }, 400);
        };
        if (iframe.contentDocument?.readyState === "complete") {
          window.setTimeout(printFrame, 250);
        } else {
          iframe.addEventListener("load", () => window.setTimeout(printFrame, 250), { once: true });
          window.setTimeout(printFrame, 1200);
        }
        return;
      }
    } catch {
      /* fall through to HTML print */
    }
    document.querySelectorAll(".docs-hf").forEach((el) => {
      if (!String(el.textContent || "").replace(/\u00a0/g, " ").trim()) el.classList.add("is-empty-hf");
    });
    closePrintPreview();
    window.setTimeout(() => {
      window.print();
      document.body.classList.remove("docs-printing-locked", "docs-print-clean");
    }, 40);
  }

  function closePrintPreview() {
    const body = $("printPreviewBody");
    if (body?._pdfUrl) {
      try {
        URL.revokeObjectURL(body._pdfUrl);
      } catch {
        /* ignore */
      }
      body._pdfUrl = null;
    }
    const modal = $("printPreviewModal");
    if (modal) modal.hidden = true;
    if (body) body.innerHTML = "";
    if (!document.body.classList.contains("docs-printing-locked")) {
      hideAiOperatorForPrint(false);
    }
  }

  function computeLineDiff(oldText, newText) {
    const a = String(oldText || "").split(/\r?\n/).slice(0, 1800);
    const b = String(newText || "").split(/\r?\n/).slice(0, 1800);
    const n = a.length;
    const m = b.length;
    const dp = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
    for (let i = n - 1; i >= 0; i -= 1) {
      for (let j = m - 1; j >= 0; j -= 1) {
        dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
    const out = [];
    let i = 0;
    let j = 0;
    while (i < n && j < m) {
      if (a[i] === b[j]) {
        out.push({ type: "same", text: a[i] });
        i += 1;
        j += 1;
      } else if (dp[i + 1][j] >= dp[i][j + 1]) {
        out.push({ type: "del", text: a[i] });
        i += 1;
      } else {
        out.push({ type: "add", text: b[j] });
        j += 1;
      }
    }
    while (i < n) {
      out.push({ type: "del", text: a[i] });
      i += 1;
    }
    while (j < m) {
      out.push({ type: "add", text: b[j] });
      j += 1;
    }
    return out;
  }

  function closeDiffModal() {
    const modal = $("diffModal");
    if (modal) modal.hidden = true;
    diffVersionId = "";
  }

  let diffRowsCache = [];
  let diffTextCache = { oldText: "", newText: "" };

  function renderDiffBody() {
    const body = $("diffModalBody");
    if (!body) return;
    const onlyChanges = !!$("diffOnlyChanges")?.checked;
    const unified = !!$("diffUnifiedView")?.checked;
    const rows = diffRowsCache || [];
    let add = 0;
    let del = 0;
    let same = 0;
    rows.forEach((r) => {
      if (r.type === "add") add += 1;
      else if (r.type === "del") del += 1;
      else same += 1;
    });
    if ($("diffStats")) $("diffStats").textContent = dt("diffStats", { add, del, same });
    body.classList.toggle("diff-unified-only", unified);
    body.classList.toggle("diff-side-only", !unified);
    const out = [];
    let idx = 0;
    let lineNo = 1;
    while (idx < rows.length) {
      const r = rows[idx];
      if (onlyChanges && r.type === "same") {
        let j = idx;
        while (j < rows.length && rows[j].type === "same") j += 1;
        const n = j - idx;
        if (n > 4) {
          out.push(
            `<div class="diff-line is-collapsed" data-expand-from="${idx}"><span class="diff-mark">…</span><pre>${escapeHtml(dt("diffCollapsed", { n }))}</pre></div>`,
          );
          lineNo += n;
          idx = j;
          continue;
        }
      }
      const cls = r.type === "add" ? "is-add" : r.type === "del" ? "is-del" : "is-same";
      const mark = r.type === "add" ? "+" : r.type === "del" ? "−" : " ";
      out.push(
        `<div class="diff-line ${cls}"><span class="diff-ln">${lineNo}</span><span class="diff-mark">${mark}</span><pre>${escapeHtml(r.text || " ")}</pre></div>`,
      );
      idx += 1;
      lineNo += 1;
    }
    body.innerHTML =
      `<div class="diff-col"><h4>${escapeHtml(dt("diffOld"))}</h4><pre class="diff-plain">${escapeHtml(diffTextCache.oldText || " ")}</pre></div>` +
      `<div class="diff-col"><h4>${escapeHtml(dt("diffNew"))}</h4><pre class="diff-plain">${escapeHtml(diffTextCache.newText || " ")}</pre></div>` +
      `<div class="diff-unified">${out.join("")}</div>`;
    body.querySelectorAll("[data-expand-from]").forEach((el) => {
      el.addEventListener("click", () => {
        if ($("diffOnlyChanges")) $("diffOnlyChanges").checked = false;
        renderDiffBody();
      });
    });
  }

  async function openVersionDiff(versionId) {
    if (!currentDoc?.id || !versionId) return;
    setStatus($("saveStatus"), dt("diffLoading"));
    try {
      const data = await api(
        `/api/v2/docs/${encodeURIComponent(currentDoc.id)}/versions/${encodeURIComponent(versionId)}${companyQuery()}`,
      );
      const version = data.version || {};
      diffVersionId = String(version.id || versionId);
      diffVersionHtml = String(version.contentHtml || version.content_html || "");
      diffVersionMeta = version;
      const oldText = String(version.contentText || version.content_text || "");
      const newText = getText();
      diffTextCache = { oldText, newText };
      diffRowsCache = computeLineDiff(oldText, newText);
      renderDiffBody();
      if ($("diffModalTitle")) $("diffModalTitle").textContent = dt("diffTitle");
      if ($("diffModalMeta")) {
        $("diffModalMeta").textContent = dt("diffMeta", {
          ver: version.version_no ?? "?",
          when: formatWhen(version.created_at),
          note: version.note || dt("versionNote"),
        });
      }
      const modal = $("diffModal");
      if (modal) modal.hidden = false;
      if (window.DocsIcons) window.DocsIcons.mountAll(modal, true);
      setStatus($("saveStatus"), dt("diffReady"), "ok");
    } catch (e) {
      setStatus($("saveStatus"), e.message || dt("diffFail"), "err");
    }
  }

  async function saveDiffAsCopy() {
    if (!diffVersionHtml && !diffVersionMeta) return;
    const copy = await createBlank({
      title: `${($("docTitle")?.value || dt("untitled")).trim()} · v${diffVersionMeta?.version_no || "?"}`.slice(0, 120),
      mode: $("docMode")?.value || "general",
      workerId: selectedWorkerId || currentDoc?.worker_id || "",
      contractId: "",
      contentHtml: diffVersionHtml || plainToHtml(String(diffVersionMeta?.contentText || diffVersionMeta?.content_text || "")),
      contentText: String(diffVersionMeta?.contentText || diffVersionMeta?.content_text || ""),
      contentJson: JSON.stringify(buildEnvelope()),
    });
    if (copy) {
      closeDiffModal();
      setStatus($("saveStatus"), dt("diffCopySaved"), "ok");
    }
  }

  function collectOutline() {
    if (!quill?.root) return [];
    const nodes = [...quill.root.querySelectorAll("h1, h2, h3")];
    return nodes.map((el, i) => ({
      id: `h-${i}`,
      level: Number(el.tagName.slice(1)),
      text: String(el.textContent || "").trim() || dt("outlineUntitled"),
      el,
    }));
  }

  function renderOutline() {
    const list = $("docOutlineList");
    const empty = $("docOutlineEmpty");
    if (!list) return;
    const items = collectOutline();
    list.innerHTML = items
      .map(
        (it, i) =>
          `<li><button type="button" class="doc-outline-item level-${it.level}" data-outline="${i}">${escapeHtml(it.text)}</button></li>`,
      )
      .join("");
    if (empty) empty.hidden = items.length > 0;
    list.hidden = items.length === 0;
  }

  function scheduleOutline() {
    if (outlineTimer) return;
    outlineTimer = window.setTimeout(() => {
      outlineTimer = 0;
      renderOutline();
      scheduleComments();
    }, 220);
  }

  function jumpToOutline(index) {
    const items = collectOutline();
    const item = items[index];
    if (!item?.el || !quill) return;
    item.el.scrollIntoView({ block: "center", behavior: "smooth" });
    try {
      const blot = window.Quill.find(item.el);
      if (blot) {
        const idx = quill.getIndex(blot);
        quill.setSelection(idx, 0, "silent");
      }
    } catch {
      /* ignore */
    }
  }

  function updateReadTimeLabel() {
    const el = $("readTimeLabel");
    if (!el) return;
    const { words } = countDocStats();
    const mins = Math.max(1, Math.ceil(words / 180));
    const text = words ? dt("readTime", { mins }) : dt("readTimeEmpty");
    if (el.textContent !== text) el.textContent = text;
  }

  function formatRelativeWhen(iso) {
    const t = Date.parse(String(iso || ""));
    if (!Number.isFinite(t)) return formatWhen(iso);
    const sec = Math.round((Date.now() - t) / 1000);
    if (sec < 8) return dt("justNow");
    if (sec < 60) return dt("secondsAgo", { n: sec });
    const min = Math.round(sec / 60);
    if (min < 60) return dt("minutesAgo", { n: min });
    return formatWhen(iso);
  }

  function readLayoutFromInputs() {
    layout.marginTopMm = Number($("marginTop")?.value || layout.marginTopMm);
    layout.marginBottomMm = Number($("marginBottom")?.value || layout.marginBottomMm);
    layout.marginLeftMm = Number($("marginLeft")?.value || layout.marginLeftMm);
    layout.marginRightMm = Number($("marginRight")?.value || layout.marginRightMm);
    applyLayoutToDom();
    markDirty();
  }

  function buildEnvelope() {
    return {
      schema: "workpass-doc-v2",
      bodyDelta: quill ? quill.getContents() : { ops: [] },
      headerHtml: getHeaderHtml(),
      footerHtml: getFooterHtml(),
      layout: { ...layout },
    };
  }

  function insertTextAtCursor(text) {
    if (!quill) return;
    const range = quill.getSelection(true);
    const index = range ? range.index : quill.getLength();
    quill.insertText(index, text, "user");
    quill.setSelection(index + text.length, 0, "user");
  }

  function insertHtmlAtCursor(html) {
    if (!quill) return;
    const range = quill.getSelection(true);
    const index = range ? range.index : Math.max(0, quill.getLength() - 1);
    quill.clipboard.dangerouslyPasteHTML(index, html, "user");
    markDirty();
    updatePageLabel();
  }

  const PASTE_KEEP_TAGS = new Set([
    "P", "BR", "DIV", "SPAN", "STRONG", "B", "EM", "I", "U", "S", "STRIKE",
    "H1", "H2", "H3", "H4", "UL", "OL", "LI", "BLOCKQUOTE", "A", "IMG",
    "TABLE", "THEAD", "TBODY", "TR", "TH", "TD", "HR", "SUB", "SUP", "MARK",
  ]);
  const PASTE_STRIP_ATTR = /^(on|xmlns|xml|mso-|data-mso)/i;

  function cleanPastedHtml(html) {
    const raw = String(html || "");
    if (!raw.trim()) return "";
    let cleaned = raw
      .replace(/<!--\[if[\s\S]*?<!\[endif\]-->/gi, "")
      .replace(/<!--[\s\S]*?-->/g, "")
      .replace(/<\/?(?:xml|o:|v:|w:)[^>]*>/gi, "");
    let doc;
    try {
      doc = new DOMParser().parseFromString(cleaned, "text/html");
    } catch {
      return "";
    }
    doc.querySelectorAll("style, script, meta, link, title, noscript").forEach((el) => el.remove());
    const walk = (node) => {
      [...node.childNodes].forEach((child) => {
        if (child.nodeType === Node.COMMENT_NODE) {
          child.remove();
          return;
        }
        if (child.nodeType !== Node.ELEMENT_NODE) return;
        const tag = child.tagName;
        if (tag === "FONT") {
          const parent = child.parentNode;
          while (child.firstChild) parent.insertBefore(child.firstChild, child);
          child.remove();
          return;
        }
        if (!PASTE_KEEP_TAGS.has(tag)) {
          const parent = child.parentNode;
          while (child.firstChild) parent.insertBefore(child.firstChild, child);
          child.remove();
          return;
        }
        [...child.attributes].forEach((attr) => {
          const name = attr.name;
          const val = attr.value || "";
          if (PASTE_STRIP_ATTR.test(name) || name === "class" || name === "id") {
            child.removeAttribute(name);
            return;
          }
          if (name === "style") {
            const keep = val
              .split(";")
              .map((s) => s.trim())
              .filter((s) => {
                if (!s || /mso-|page-break|tab-stops|font-family:\s*["']?Calibri/i.test(s)) return false;
                return /^(color|background-color|font-weight|font-style|text-decoration|text-align|font-size)\s*:/i.test(s);
              })
              .join("; ");
            if (keep) child.setAttribute("style", keep);
            else child.removeAttribute("style");
            return;
          }
          if (tag === "A" && name === "href") return;
          if (tag === "IMG" && (name === "src" || name === "alt" || name === "width" || name === "height")) return;
          if ((tag === "TD" || tag === "TH") && (name === "colspan" || name === "rowspan")) return;
          child.removeAttribute(name);
        });
        if (tag === "IMG") {
          const src = child.getAttribute("src") || "";
          if (!src || /^(file:|blob:)/i.test(src)) child.remove();
          else child.classList.add("wp-img-md");
        }
        if (tag === "TABLE") child.classList.add("wp-table");
        walk(child);
      });
    };
    walk(doc.body);
    return compactHtml(doc.body.innerHTML);
  }

  function bindCleanPaste() {
    if (!quill?.root) return;
    quill.root.addEventListener(
      "paste",
      (e) => {
        const cd = e.clipboardData;
        if (!cd) return;
        const html = cd.getData("text/html");
        const text = cd.getData("text/plain");
        if (!html && !text) return;
        // Keep Quill default for plain text / tiny fragments without Word junk.
        const looksDirty =
          html &&
          (/class=["']?Mso|mso-|schemas-microsoft|urn:schemas-microsoft|<!--\[if/i.test(html) ||
            /style=["'][^"']*(?:mso-|Calibri|Times New Roman)/i.test(html) ||
            /<\/?(?:o:|w:|v:)/i.test(html));
        if (!looksDirty && !html) return;
        if (!looksDirty && html && html.length < 40) return;
        e.preventDefault();
        e.stopPropagation();
        const range = quill.getSelection(true) || { index: Math.max(0, quill.getLength() - 1), length: 0 };
        if (range.length) quill.deleteText(range.index, range.length, "user");
        let inserted = false;
        if (html) {
          const clean = cleanPastedHtml(html);
          if (clean) {
            quill.clipboard.dangerouslyPasteHTML(range.index, clean, "user");
            inserted = true;
            setStatus($("saveStatus"), dt("pasteCleaned"), "ok");
          }
        }
        if (!inserted && text) {
          quill.insertText(range.index, text, "user");
          quill.setSelection(range.index + text.length, 0, "user");
        }
        markDirty();
        scheduleAutosave();
        schedulePaperSync();
      },
      true,
    );
  }

  function getSignatureBlockHtml() {
    const pack = getSnippetHtml("signature");
    if (pack && /wp-sign-block/.test(pack)) return compactHtml(pack).replaceAll("{{date.today}}", todayIso());
    return compactHtml(`
      <div class="wp-sign-block">
        <p><br></p>
        <p class="wp-sign-line">_______________________________</p>
        <p class="wp-sign-name">{{manager.name}}</p>
        <p class="wp-sign-meta">{{company.name}}</p>
        <p class="wp-sign-date">${escapeHtml(dt("signDateLabel"))}: {{date.today}}</p>
      </div>
      <p><br></p>
    `).replaceAll("{{date.today}}", todayIso());
  }

  let signDrawing = false;
  let signHasInk = false;

  function resizeSignCanvas() {
    const canvas = $("signCanvas");
    if (!canvas) return;
    const cssW = canvas.clientWidth || 520;
    const cssH = Math.max(140, Math.round(cssW * (180 / 520)));
    const dpr = Math.min(window.devicePixelRatio || 1, 2.5);
    const w = Math.round(cssW * dpr);
    const h = Math.round(cssH * dpr);
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }
    canvas.style.height = `${cssH}px`;
  }

  function clearSignCanvas() {
    const canvas = $("signCanvas");
    if (!canvas) return;
    resizeSignCanvas();
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = "#0f172a";
    ctx.lineWidth = Math.max(2.4, canvas.width / 220);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    signHasInk = false;
  }

  function bindSignCanvas() {
    const canvas = $("signCanvas");
    if (!canvas || canvas.dataset.bound) return;
    canvas.dataset.bound = "1";
    resizeSignCanvas();
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    let last = null;
    const pos = (e) => {
      const rect = canvas.getBoundingClientRect();
      const src = e.touches ? e.touches[0] : e;
      const force = typeof src.force === "number" && src.force > 0 ? src.force : 0.5;
      return {
        x: ((src.clientX - rect.left) / Math.max(rect.width, 1)) * canvas.width,
        y: ((src.clientY - rect.top) / Math.max(rect.height, 1)) * canvas.height,
        force,
      };
    };
    const start = (e) => {
      signDrawing = true;
      last = pos(e);
      ctx.beginPath();
      ctx.moveTo(last.x, last.y);
      e.preventDefault();
    };
    const move = (e) => {
      if (!signDrawing) return;
      const p = pos(e);
      if (!last) {
        last = p;
        return;
      }
      const midX = (last.x + p.x) / 2;
      const midY = (last.y + p.y) / 2;
      ctx.lineWidth = Math.max(1.6, (canvas.width / 220) * (0.65 + p.force));
      ctx.quadraticCurveTo(last.x, last.y, midX, midY);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(midX, midY);
      last = p;
      signHasInk = true;
      e.preventDefault();
    };
    const end = () => {
      signDrawing = false;
      last = null;
    };
    canvas.addEventListener("mousedown", start);
    canvas.addEventListener("mousemove", move);
    window.addEventListener("mouseup", end);
    canvas.addEventListener("touchstart", start, { passive: false });
    canvas.addEventListener("touchmove", move, { passive: false });
    canvas.addEventListener("touchend", end);
    window.addEventListener("resize", () => {
      if (!$("signModal") || $("signModal").hidden) return;
      clearSignCanvas();
    });
  }

  async function refreshQesStatus() {
    const note = $("qesStatusNote");
    const btn = $("signQesBtn");
    if (note) note.textContent = dt("qesStatusLoading");
    try {
      const data = await api(`/api/v2/docs/signatures/qes/status${companyQuery()}`);
      qesStatusCache = data;
      if (btn) btn.disabled = !data.configured;
      if (note) {
        note.textContent = data.configured
          ? dt("qesReady", { provider: data.provider || "TSP" })
          : dt("qesNotConfigured");
      }
    } catch {
      qesStatusCache = { configured: false };
      if (btn) btn.disabled = true;
      if (note) note.textContent = dt("qesNotConfigured");
    }
  }

  async function startQesSignature() {
    if (!currentDoc?.id) {
      try {
        await saveDoc();
      } catch {
        /* ignore */
      }
    }
    if (!currentDoc?.id) {
      setStatus($("signModalStatus"), dt("needSave"), "err");
      return;
    }
    setStatus($("signModalStatus"), dt("qesStatusLoading"));
    try {
      const data = await api(`/api/v2/docs/${encodeURIComponent(currentDoc.id)}/signatures/qes/start${companyQuery()}`, {
        method: "POST",
        body: JSON.stringify({
          company_id: activeCompanyId(),
          signerName: String($("signNameInput")?.value || "").trim(),
        }),
      });
      setStatus($("signModalStatus"), dt("qesStarted"), "ok");
      refreshSignatures().catch(() => {});
      if (data.sessionUrl && confirm(dt("qesOpenSession"))) {
        window.open(data.sessionUrl, "_blank", "noopener");
      }
    } catch (e) {
      setStatus($("signModalStatus"), e.body?.message || e.message || dt("qesNotConfigured"), "err");
    }
  }

  function openSignModal() {
    const modal = $("signModal");
    if (!modal) {
      insertSignatureBlockLineOnly();
      return;
    }
    if ($("signNameInput") && !$("signNameInput").value) {
      $("signNameInput").value = companyBranding?.companyName
        ? ""
        : String(($("workerSelect")?.selectedOptions?.[0]?.textContent || "").trim() || "");
    }
    if ($("signPinInput")) $("signPinInput").value = "";
    bindSignCanvas();
    clearSignCanvas();
    setStatus($("signModalStatus"), "");
    refreshQesStatus().catch(() => {});
    modal.hidden = false;
  }

  function closeSignModal() {
    const modal = $("signModal");
    if (modal) modal.hidden = true;
    signDrawing = false;
  }

  function insertSignatureBlockLineOnly() {
    const signer = String($("signNameInput")?.value || window.prompt(dt("signNamePrompt"), "") || "").trim();
    const when = todayIso();
    const nameLine = signer
      ? `<p class="wp-sign-name">${escapeHtml(signer)}</p>`
      : `<p class="wp-sign-line">_______________________________</p>`;
    const stamp = $("signStampCheck")?.checked
      ? `<p class="wp-sign-stamp">${escapeHtml(dt("signStamp"))}</p>`
      : "";
    const html =
      `<div class="wp-sign-block${stamp ? " is-signed" : ""}" contenteditable="false">` +
      `<p class="wp-sign-label">${escapeHtml(dt("snSign"))}</p>` +
      nameLine +
      stamp +
      `<p class="wp-sign-date">${escapeHtml(dt("signDateLabel"))}: ${escapeHtml(when)}</p>` +
      `</div><p><br></p>`;
    insertHtmlAtCursor(html);
    setStatus($("saveStatus"), dt("signInserted"), "ok");
    closeSignModal();
  }

  async function insertSignatureFromModal() {
    const canvas = $("signCanvas");
    const signer = String($("signNameInput")?.value || "").trim();
    const pin = String($("signPinInput")?.value || "").trim();
    const when = todayIso();
    const stampOn = !!$("signStampCheck")?.checked;
    const lockAfter = !!$("signLockCheck")?.checked;
    if (pin.length < 4) {
      setStatus($("signModalStatus"), dt("signPinRequired"), "err");
      $("signPinInput")?.focus();
      return;
    }
    let imageHtml = "";
    if (canvas && signHasInk) {
      try {
        imageHtml = `<p class="wp-sign-img-wrap"><img class="wp-sign-img" src="${canvas.toDataURL("image/png")}" alt="${escapeHtml(dt("snSign"))}" /></p>`;
      } catch {
        imageHtml = "";
      }
    }
    if (!imageHtml && !signer) {
      setStatus($("signModalStatus"), dt("signNeedInk"), "err");
      return;
    }
    const nameLine = signer
      ? `<p class="wp-sign-name">${escapeHtml(signer)}</p>`
      : "";
    const stamp = stampOn ? `<p class="wp-sign-stamp">${escapeHtml(dt("signStamp"))}</p>` : "";
    const line = imageHtml ? "" : `<p class="wp-sign-line">_______________________________</p>`;
    const html =
      `<div class="wp-sign-block${stampOn ? " is-signed" : ""}" contenteditable="false">` +
      `<p class="wp-sign-label">${escapeHtml(dt("snSign"))}</p>` +
      imageHtml +
      line +
      nameLine +
      stamp +
      `<p class="wp-sign-date">${escapeHtml(dt("signDateLabel"))}: ${escapeHtml(when)}</p>` +
      `<p class="wp-sign-aes">${escapeHtml(dt("signAesNote"))}</p>` +
      `</div><p><br></p>`;
    insertHtmlAtCursor(html);
    setStatus($("saveStatus"), dt("signInserted"), "ok");
    try {
      await saveDoc();
    } catch {
      /* still try audit */
    }
    try {
      await recordSignatureAudit({
        signerName: signer,
        stamped: stampOn,
        signatureData: canvas && signHasInk ? canvas.toDataURL("image/png") : "",
        pin,
        lockAfter: lockAfter && stampOn,
      });
      setStatus($("signModalStatus"), dt("signAuditOk"), "ok");
    } catch (e) {
      setStatus($("signModalStatus"), e.body?.message || e.message || dt("signPinRequired"), "err");
      return;
    }
    closeSignModal();
  }

  function insertSignatureBlock() {
    openSignModal();
  }

  const SPELL_LANG_KEY = "baupass-docs-spell-lang";
  const SPELL_BCP47 = {
    de: "de-DE",
    en: "en-US",
    ar: "ar",
    tr: "tr-TR",
    fr: "fr-FR",
    es: "es-ES",
    it: "it-IT",
    pl: "pl-PL",
  };

  function applySpellcheck() {
    if (!quill?.root) return;
    const sel = $("spellLangSelect");
    let code = String(sel?.value || localStorage.getItem(SPELL_LANG_KEY) || "").trim();
    if (!code) {
      code = typeof window.getDocsPageLang === "function" ? window.getDocsPageLang() : "de";
    }
    if (sel && [...sel.options].some((o) => o.value === code)) sel.value = code;
    localStorage.setItem(SPELL_LANG_KEY, code);
    if (code === "off") {
      quill.root.setAttribute("spellcheck", "false");
      quill.root.removeAttribute("lang");
      $("docHeader")?.setAttribute("spellcheck", "false");
      $("docFooter")?.setAttribute("spellcheck", "false");
      return;
    }
    const bcp = SPELL_BCP47[code] || code;
    quill.root.setAttribute("spellcheck", "true");
    quill.root.setAttribute("lang", bcp);
    $("docHeader")?.setAttribute("spellcheck", "true");
    $("docHeader")?.setAttribute("lang", bcp);
    $("docFooter")?.setAttribute("spellcheck", "true");
    $("docFooter")?.setAttribute("lang", bcp);
  }

  function insertTable(rows, cols) {
    if (!quill) return;
    const rCount = Math.min(20, Math.max(1, Number(rows ?? $("tableRows")?.value ?? 3) || 3));
    const cCount = Math.min(12, Math.max(1, Number(cols ?? $("tableCols")?.value ?? 3) || 3));
    let html = '<table class="wp-table"><tbody>';
    for (let r = 0; r < rCount; r += 1) {
      html += "<tr>";
      for (let c = 0; c < cCount; c += 1) {
        html += r === 0 ? "<th>&nbsp;</th>" : "<td>&nbsp;</td>";
      }
      html += "</tr>";
    }
    html += "</tbody></table>";
    const range = quill.getSelection(true) || { index: Math.max(0, quill.getLength() - 1) };
    // Custom blot keeps tables (Quill would otherwise strip them)
    quill.insertEmbed(range.index, "wpTable", html, "user");
    quill.insertText(range.index + 1, "\n", "user");
    quill.setSelection(range.index + 2, 0, "user");
    markDirty();
    updatePageLabel();
    setStatus($("saveStatus"), dt("tableInserted", { rows: rCount, cols: cCount }), "ok");
  }

  function getActiveTable() {
    if (!quill) return null;
    const sel = window.getSelection();
    let node = sel?.anchorNode || null;
    if (node && node.nodeType === 3) node = node.parentElement;
    while (node && node !== quill.root) {
      if (node.tagName === "TABLE") return node;
      node = node.parentElement;
    }
    return quill.root.querySelector("table.wp-table-active") || quill.root.querySelector("table.wp-table") || null;
  }

  function highlightActiveTable() {
    if (!quill) return;
    quill.root.querySelectorAll("table.wp-table-active").forEach((t) => t.classList.remove("wp-table-active"));
    const table = getActiveTable();
    if (table) table.classList.add("wp-table-active");
    if ($("tableHint")) {
      $("tableHint").textContent = table ? dt("tableActive") : dt("tableCursor");
    }
  }

  function tableAddRow() {
    const table = getActiveTable();
    if (!table) {
      setStatus($("saveStatus"), dt("noTable"), "err");
      return;
    }
    const body = table.tBodies[0] || table;
    const cols = body.rows[0]?.cells.length || 1;
    const tr = document.createElement("tr");
    for (let i = 0; i < cols; i += 1) {
      const td = document.createElement("td");
      td.innerHTML = "<p><br></p>";
      tr.appendChild(td);
    }
    body.appendChild(tr);
    markDirty();
    scheduleAutosave();
  }

  function tableDelRow() {
    const table = getActiveTable();
    if (!table) return;
    const body = table.tBodies[0] || table;
    if (body.rows.length <= 1) {
      setStatus($("saveStatus"), dt("minRow"), "err");
      return;
    }
    const sel = window.getSelection();
    let row = sel?.anchorNode;
    if (row && row.nodeType === 3) row = row.parentElement;
    while (row && row.tagName !== "TR") row = row.parentElement;
    if (row && body.contains(row)) row.remove();
    else body.rows[body.rows.length - 1]?.remove();
    markDirty();
    scheduleAutosave();
  }

  function tableAddCol() {
    const table = getActiveTable();
    if (!table) {
      setStatus($("saveStatus"), dt("noTable"), "err");
      return;
    }
    const body = table.tBodies[0] || table;
    [...body.rows].forEach((row, idx) => {
      const cell = document.createElement(idx === 0 && row.cells[0]?.tagName === "TH" ? "th" : "td");
      cell.innerHTML = "<p><br></p>";
      row.appendChild(cell);
    });
    markDirty();
    scheduleAutosave();
  }

  function tableDelCol() {
    const table = getActiveTable();
    if (!table) return;
    const body = table.tBodies[0] || table;
    if (!body.rows[0] || body.rows[0].cells.length <= 1) {
      setStatus($("saveStatus"), dt("minCol"), "err");
      return;
    }
    const sel = window.getSelection();
    let cell = sel?.anchorNode;
    if (cell && cell.nodeType === 3) cell = cell.parentElement;
    while (cell && cell.tagName !== "TD" && cell.tagName !== "TH") cell = cell.parentElement;
    let idx = cell && cell.parentElement ? [...cell.parentElement.cells].indexOf(cell) : -1;
    if (idx < 0) idx = body.rows[0].cells.length - 1;
    [...body.rows].forEach((row) => row.cells[idx]?.remove());
    markDirty();
    scheduleAutosave();
  }

  function tableToggleHeaderRow() {
    const table = getActiveTable();
    if (!table) return;
    const body = table.tBodies[0] || table;
    const first = body.rows[0];
    if (!first) return;
    const useTh = first.cells[0]?.tagName !== "TH";
    [...first.cells].forEach((old) => {
      const neu = document.createElement(useTh ? "th" : "td");
      neu.innerHTML = old.innerHTML || "<p><br></p>";
      old.replaceWith(neu);
    });
    markDirty();
    scheduleAutosave();
  }

  function tableSetBorders(mode) {
    const table = getActiveTable();
    if (!table) {
      setStatus($("saveStatus"), dt("noTable"), "err");
      return;
    }
    table.classList.remove("wp-table-lines-none", "wp-table-lines-outer");
    if (mode === "none") table.classList.add("wp-table-lines-none");
    else if (mode === "outer") table.classList.add("wp-table-lines-outer");
    markDirty();
    scheduleAutosave();
  }

  function clearParagraphExtras(range) {
    const len = Math.max(1, range.length || 1);
    quill.formatLine(range.index, len, "header", false);
    quill.format("blockquote", false);
    quill.format("align", false);
    // strip helper classes from selected block(s)
    const [leaf] = quill.getLeaf(range.index);
    let block = leaf?.parent;
    while (block && block.domNode && !block.domNode.classList?.contains?.("ql-editor")) {
      if (block.domNode.tagName === "P" || /^H[1-6]$/.test(block.domNode.tagName || "")) {
        block.domNode.classList.remove(
          "wp-title",
          "wp-subtitle",
          "wp-caption",
          "wp-letter",
          "wp-recipient",
          "wp-date",
          "wp-subject",
          "wp-sign",
          "wp-meta",
          "wp-center",
          "wp-doc-title",
        );
        break;
      }
      block = block.parent;
    }
  }

  function applyParagraphStyle(style) {
    if (!quill) return;
    const range = quill.getSelection(true) || { index: 0, length: 0 };
    clearParagraphExtras(range);
    const len = Math.max(1, range.length || 1);
    if (style === "normal") {
      quill.format("size", "16px");
    } else if (style === "title") {
      quill.formatLine(range.index, len, "header", 1);
      quill.format("size", "32px");
      quill.format("align", "center");
      const [leaf] = quill.getLeaf(range.index);
      let block = leaf?.parent;
      while (block?.domNode && block.domNode.tagName !== "H1") block = block.parent;
      if (block?.domNode) block.domNode.classList.add("wp-title");
    } else if (style === "subtitle") {
      quill.format("size", "18px");
      quill.format("align", "center");
      const [leaf] = quill.getLeaf(range.index);
      let el = leaf?.domNode;
      if (el?.nodeType === 3) el = el.parentElement;
      while (el && el !== quill.root && el.tagName !== "P") el = el.parentElement;
      if (el?.classList) el.classList.add("wp-subtitle");
    } else if (style === "h1") quill.formatLine(range.index, len, "header", 1);
    else if (style === "h2") quill.formatLine(range.index, len, "header", 2);
    else if (style === "h3") quill.formatLine(range.index, len, "header", 3);
    else if (style === "quote") quill.format("blockquote", true);
    else if (style === "caption") {
      quill.format("size", "12px");
      quill.format("align", "center");
      const [leaf] = quill.getLeaf(range.index);
      let el = leaf?.domNode;
      if (el?.nodeType === 3) el = el.parentElement;
      while (el && el !== quill.root && el.tagName !== "P") el = el.parentElement;
      if (el?.classList) el.classList.add("wp-caption");
    } else if (style === "letter") {
      quill.format("size", "14px");
      const [leaf] = quill.getLeaf(range.index);
      let el = leaf?.domNode;
      if (el?.nodeType === 3) el = el.parentElement;
      while (el && el !== quill.root && el.tagName !== "P") el = el.parentElement;
      if (el?.classList) el.classList.add("wp-letter");
    }
    markDirty();
  }

  function applyHeaderPreset(kind) {
    const el = $("docHeader");
    if (!el) return;
    layout.showHeader = true;
    if (kind === "clear") el.innerHTML = "";
    else if (kind === "company") {
      el.innerHTML = `<div class="wp-hf-grid">
        <div class="wp-hf-l"><span class="wp-hf-brand">{{company.name}}</span></div>
        <div class="wp-hf-c"><span class="wp-hf-meta">{{date.today}}</span></div>
        <div class="wp-hf-r"><span class="wp-hf-meta">{{site.name}}</span></div>
      </div>`;
    } else if (kind === "letter") {
      el.innerHTML = `<div class="wp-hf-l"><span class="wp-hf-brand">{{company.name}}</span><div class="wp-hf-meta">{{site.name}}</div></div>`;
    } else if (kind === "confidential") {
      el.innerHTML = `<div class="wp-hf-grid">
        <div class="wp-hf-l"></div>
        <div class="wp-hf-c"><strong>${escapeHtml(dt("confidential"))}</strong></div>
        <div class="wp-hf-r"><span class="wp-hf-meta">{{date.today}}</span></div>
      </div>`;
    }
    applyLayoutToDom();
    markDirty();
  }

  function applyFooterPreset(kind) {
    const el = $("docFooter");
    if (!el) return;
    layout.showFooter = true;
    if (kind === "clear") el.innerHTML = "";
    else if (kind === "page") {
      el.innerHTML = `<div class="wp-hf-grid">
        <div class="wp-hf-l"><span class="wp-hf-meta">{{company.name}}</span></div>
        <div class="wp-hf-c"><span class="wp-page-xy" data-wp-page-xy="1">${escapeHtml(dt("pageOf", { cur: currentPageView || 1, pages: pageCount || 1 }))}</span></div>
        <div class="wp-hf-r"><span class="wp-hf-meta">{{date.today}}</span></div>
      </div>`;
    } else if (kind === "pageOnly") {
      el.innerHTML = `<div class="wp-hf-grid">
        <div class="wp-hf-l"></div>
        <div class="wp-hf-c"><span class="wp-page-xy" data-wp-page-xy="1">${escapeHtml(dt("pageOf", { cur: currentPageView || 1, pages: pageCount || 1 }))}</span></div>
        <div class="wp-hf-r"></div>
      </div>`;
    } else if (kind === "confidential") {
      el.innerHTML = `<div class="wp-hf-grid">
        <div class="wp-hf-l"><span class="wp-hf-meta">${escapeHtml(dt("confidential"))}</span></div>
        <div class="wp-hf-c"></div>
        <div class="wp-hf-r"><span class="wp-hf-meta">{{date.today}}</span></div>
      </div>`;
    }
    applyLayoutToDom();
    markDirty();
  }

  function payloadFromEditor() {
    const workerId =
      selectedWorkerId ||
      ($("workerSelect")?.value || "").trim() ||
      currentDoc?.worker_id ||
      qs().get("worker_id") ||
      "";
    return {
      title: ($("docTitle")?.value || "").trim() || dt("untitled"),
      mode: $("docMode")?.value || "general",
      contentJson: JSON.stringify(buildEnvelope()),
      contentHtml: getHtml(),
      contentText: getText(),
      company_id: activeCompanyId(),
      contractId: currentDoc?.contract_id || qs().get("contract_id") || "",
      workerId,
    };
  }

  function syncWorkerSelect(workerId) {
    selectedWorkerId = String(workerId || "").trim();
    const sel = $("workerSelect");
    if (!sel) return;
    if (selectedWorkerId && ![...sel.options].some((o) => o.value === selectedWorkerId)) {
      const opt = document.createElement("option");
      opt.value = selectedWorkerId;
      opt.textContent = dt("workerShort", { id: selectedWorkerId.slice(0, 8) });
      sel.appendChild(opt);
    }
    sel.value = selectedWorkerId;
  }

  let companyBranding = null;
  let companyLetterhead = null;

  async function loadMergeContext() {
    const cid = activeCompanyId();
    if (!cid) return;
    try {
      const data = await api(
        `/api/v2/docs/merge-context${companyQuery({ worker_id: selectedWorkerId || undefined })}`,
      );
      companyBranding = data.branding || null;
      companyLetterhead = data.letterhead || null;
      renderBrandPreview();
      if ($("useLetterhead")) $("useLetterhead").checked = true;
      // Replace empty headers or accidental SUPPIX+Firma dual branding.
      if (currentDoc?.id) ensureCompanyLetterhead({ silent: true });

      const workers = data.workers || [];
      const sel = $("workerSelect");
      if (sel) {
        const keep = selectedWorkerId || currentDoc?.worker_id || qs().get("worker_id") || "";
        sel.innerHTML =
          `<option value="">${escapeHtml(dt("workerNone"))}</option>` +
          workers
            .map((w) => {
              const extra = [w.badgeId, w.role].filter(Boolean).join(" · ");
              return `<option value="${escapeHtml(w.id)}" data-email="${escapeHtml(String(w.email || ""))}">${escapeHtml(w.name || w.id)}${
                extra ? ` (${escapeHtml(extra)})` : ""
              }</option>`;
            })
            .join("");
        syncWorkerSelect(keep);
      }
      if ($("workersHint")) {
        $("workersHint").textContent = workers.length
          ? dt("workersCount", { n: workers.length })
          : dt("workersNone");
        $("workersHint").className = workers.length ? "status is-ok" : "status";
      }
    } catch (e) {
      if ($("workersHint")) {
        $("workersHint").textContent = e.message || dt("workersLoadFail");
        $("workersHint").className = "status is-err";
      }
    }
  }

  function renderBrandPreview() {
    const preview = $("brandPreview");
    const hint = $("brandHint");
    if (!companyBranding) {
      if (preview) preview.hidden = true;
      if (hint) hint.textContent = dt("brandLoading");
      return;
    }
    const name = companyBranding.companyName || dt("companyFallback");
    const meta = [companyBranding.address, companyBranding.email, companyBranding.contact]
      .filter((x) => x && x !== "—")
      .join(" · ");
    if ($("brandName")) $("brandName").textContent = name;
    if ($("brandMeta")) $("brandMeta").textContent = meta || dt("brandContactHint");
    const logo = $("brandLogo");
    if (logo) {
      if (companyBranding.logoData && String(companyBranding.logoData).startsWith("data:image/")) {
        logo.src = companyBranding.logoData;
        logo.hidden = false;
      } else {
        logo.removeAttribute("src");
        logo.hidden = true;
      }
    }
    if (preview) preview.hidden = false;
    if (hint) {
      hint.textContent = companyBranding.logoData
        ? dt("brandLogoOk")
        : dt("brandLogoMissing");
    }
  }

  function headerHasPlatformBrand(html) {
    return /suppix|workpass\s*ai|baupass\s*ai/i.test(String(html || ""));
  }

  function applyCompanyLetterhead(opts = {}) {
    if (!companyLetterhead) {
      if (!opts.silent) setStatus($("saveStatus"), dt("letterheadNeedBrand"), "err");
      return false;
    }
    const nextHeader = companyLetterhead.headerHtml || "";
    const nextFooter = companyLetterhead.footerHtml || "";
    // Compare normalized HTML — browsers rewrite whitespace/attrs after innerHTML set.
    const beforeH = compactHtml($("docHeader")?.innerHTML || "");
    const beforeF = compactHtml($("docFooter")?.innerHTML || "");
    const needLayout = !layout.showHeader || !layout.showFooter;
    layout.showHeader = true;
    layout.showFooter = true;
    if ($("docHeader")) $("docHeader").innerHTML = nextHeader;
    if ($("docFooter")) $("docFooter").innerHTML = nextFooter;
    if ($("useLetterhead")) $("useLetterhead").checked = true;
    applyLayoutToDom();
    const afterH = compactHtml($("docHeader")?.innerHTML || "");
    const afterF = compactHtml($("docFooter")?.innerHTML || "");
    const changed = needLayout || beforeH !== afterH || beforeF !== afterF;
    if (changed) markDirty();
    if (!opts.silent) setStatus($("saveStatus"), dt("letterheadSet"), "ok");
    return true;
  }

  function clearCompanyLetterhead() {
    if ($("docHeader")) $("docHeader").innerHTML = "";
    if ($("docFooter")) $("docFooter").innerHTML = "";
    if ($("useLetterhead")) $("useLetterhead").checked = false;
    applyLayoutToDom();
    markDirty();
    setStatus($("saveStatus"), dt("letterheadCleared"), "ok");
  }

  function syncLetterheadFromToggle() {
    const on = !!$("useLetterhead")?.checked;
    if (on) applyCompanyLetterhead();
    else clearCompanyLetterhead();
  }

  /** Put company letterhead on paper: always for new docs; replace empty/platform dual-brand headers. */
  function ensureCompanyLetterhead(opts = {}) {
    if (!companyLetterhead) return false;
    if ($("useLetterhead") && !$("useLetterhead").checked && !opts.force) return false;
    const hdr = $("docHeader")?.innerHTML || "";
    const empty = !String(hdr).trim();
    const platform = headerHasPlatformBrand(hdr);
    if (opts.force || empty || platform || opts.replace) {
      return applyCompanyLetterhead({ silent: !!opts.silent });
    }
    return false;
  }

  function insertSnippet(key) {
    if (key === "signature") {
      insertSignatureBlock();
      return;
    }
    const html = getSnippetHtml(key);
    if (!html) return;
    insertHtmlAtCursor(wrapMergePlaceholders(compactHtml(html).replaceAll("{{date.today}}", todayIso())));
    setStatus($("saveStatus"), dt("snippetInserted"), "ok");
  }

  async function renderTemplateGallery() {
    const host = $("templateGallery");
    if (!host) return;
    const builtIn = templateMetaList();
    const custom = loadCustomTemplates().map((t) => ({
      id: t.id,
      topic: "custom",
      title: t.title,
      blurb: t.blurb || dt("customTemplateBlurb"),
      previewHtml: t.contentHtml || "",
      custom: true,
    }));
    let team = [];
    try {
      if (activeCompanyId()) {
        const data = await api(`/api/v2/docs/templates${companyQuery()}`);
        team = (data.items || []).map((t) => ({
          id: t.id,
          topic: "team",
          title: t.title,
          blurb: t.blurb || dt("teamTemplateBlurb"),
          previewHtml: t.content_html || t.contentHtml || "",
          team: true,
          canDelete: t.canDelete !== false,
          isMine: !!t.isMine,
          createdBy: t.created_by_user_id || "",
        }));
      }
    } catch {
      team = [];
    }
    const list = [...team, ...custom, ...builtIn];
    const q = String(tplSearchQuery || "")
      .trim()
      .toLowerCase();
    const searched = q
      ? list.filter(
          (t) =>
            String(t.title || "")
              .toLowerCase()
              .includes(q) ||
            String(t.blurb || "")
              .toLowerCase()
              .includes(q),
        )
      : list;
    const topics = TOPIC_ORDER.filter((t) => searched.some((x) => x.topic === t));
    const chips = [
      `<button type="button" class="tpl-topic${activeTopicFilter === "all" ? " active" : ""}" data-topic="all">${escapeHtml(dt("topicAll"))}</button>`,
      ...topics.map(
        (t) =>
          `<button type="button" class="tpl-topic${activeTopicFilter === t ? " active" : ""}" data-topic="${escapeHtml(t)}">${escapeHtml(dt(TOPIC_LABEL_KEYS[t] || t))}</button>`,
      ),
    ].join("");

    const filtered =
      activeTopicFilter === "all" ? searched : searched.filter((t) => t.topic === activeTopicFilter);

    const byId = new Map(list.map((t) => [String(t.id), t]));
    const recentIds = loadRecentTemplates().filter((id) => byId.has(id));
    const recentHtml =
      !q && activeTopicFilter === "all" && recentIds.length
        ? `<div class="tpl-topic-group">
            <p class="tpl-topic-label">${escapeHtml(dt("tplRecent"))}</p>
            <div class="tpl-card-list">${recentIds.map((id) => cardHtml(byId.get(id))).join("")}</div>
          </div>`
        : "";

    function cardHtml(t) {
      if (!t) return "";
      const preview = escapeHtml(templatePreviewSnippet(t));
      const attr = t.team
        ? `data-team-template="${escapeHtml(t.id)}"`
        : t.custom
          ? `data-custom-template="${escapeHtml(t.id)}"`
          : `data-template="${escapeHtml(t.id)}"`;
      const sideBtn = t.team
        ? t.canDelete
          ? `<button type="button" class="cmd quiet tpl-card-del" data-team-del="${escapeHtml(t.id)}" title="${escapeHtml(dt("delete"))}">×</button>`
          : ""
        : t.custom
          ? `<button type="button" class="cmd quiet tpl-card-del" data-custom-del="${escapeHtml(t.id)}" title="${escapeHtml(dt("delete"))}">×</button>`
          : `<button type="button" class="cmd quiet tpl-card-edit" data-template-edit="${escapeHtml(t.id)}" title="${escapeHtml(dt("tplEdit"))}">✎</button>`;
      const badge = t.team
        ? `<em class="tpl-card-badge">${escapeHtml(t.isMine ? dt("topicTeam") + " · ✓" : dt("topicTeam"))}</em>`
        : t.custom
          ? `<em class="tpl-card-badge is-local">${escapeHtml(dt("topicCustom"))}</em>`
          : "";
      return `<div class="tpl-card-wrap${t.team ? " is-team" : ""}">
          <button type="button" class="tpl-card${t.team ? " is-team" : ""}" ${attr}>
            <div class="tpl-card-preview" aria-hidden="true">
              <strong class="tpl-card-preview-title">${escapeHtml(t.title)}</strong>
              <span class="tpl-card-preview-body">${preview}</span>
            </div>
            <span class="tpl-card-title-row"><strong>${escapeHtml(t.title)}</strong>${badge}</span>
            <span>${escapeHtml(t.blurb)}</span>
          </button>
          ${sideBtn}
        </div>`;
    }

    const teamItems = searched.filter((t) => t.team);
    const teamHtml =
      !q && (activeTopicFilter === "all" || activeTopicFilter === "team") && teamItems.length
        ? `<div class="tpl-topic-group tpl-team-group">
            <p class="tpl-topic-label">${escapeHtml(dt("topicTeam"))}</p>
            <div class="tpl-card-list">${teamItems.map(cardHtml).join("")}</div>
          </div>`
        : "";

    let cardsHtml = "";
    if (activeTopicFilter === "all" && !q) {
      cardsHtml = TOPIC_ORDER.filter((topic) => topic !== "team")
        .map((topic) => {
          const items = filtered.filter((t) => t.topic === topic);
          if (!items.length) return "";
          return `<div class="tpl-topic-group">
          <p class="tpl-topic-label">${escapeHtml(dt(TOPIC_LABEL_KEYS[topic] || topic))}</p>
          <div class="tpl-card-list">${items.map(cardHtml).join("")}</div>
        </div>`;
        })
        .join("");
    } else if (activeTopicFilter === "team") {
      cardsHtml = "";
    } else {
      cardsHtml = `<div class="tpl-card-list">${filtered.map(cardHtml).join("")}</div>`;
    }

    const saveBar = `<div class="tpl-save-bar">
      <button type="button" class="cmd quiet block" id="saveAsTemplateSideBtn" data-di18n="saveAsTemplate">${escapeHtml(dt("saveAsTemplate"))}</button>
    </div>`;
    const searchBar = `<label class="field tpl-search-field">
      <span class="sr-only">${escapeHtml(dt("tplSearch"))}</span>
      <input type="search" id="tplSearchInput" value="${escapeHtml(tplSearchQuery)}" placeholder="${escapeHtml(dt("tplSearch"))}" />
    </label>`;

    host.innerHTML = `
      ${saveBar}
      ${searchBar}
      <div class="tpl-topic-row" role="toolbar" aria-label="${escapeHtml(dt("topicSuggest"))}">${chips}</div>
      <div class="tpl-groups">${teamHtml}${recentHtml}${cardsHtml || (!teamHtml ? `<p class="side-hint">${escapeHtml(dt("emptyDocs"))}</p>` : "")}</div>
    `;
    const searchInput = $("tplSearchInput");
    if (searchInput) {
      let t = 0;
      searchInput.addEventListener("input", () => {
        tplSearchQuery = searchInput.value || "";
        window.clearTimeout(t);
        t = window.setTimeout(() => renderTemplateGallery(), 120);
      });
    }
    host.querySelectorAll("[data-topic]").forEach((btn) => {
      btn.addEventListener("click", () => {
        activeTopicFilter = btn.getAttribute("data-topic") || "all";
        renderTemplateGallery();
      });
    });
    host.querySelectorAll("[data-template]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-template");
        pushRecentTemplate(id);
        if ($("templateSelect")) $("templateSelect").value = id;
        applyTemplate(id).catch((e) => setStatus($("saveStatus"), e.message || dt("error"), "err"));
      });
    });
    host.querySelectorAll("[data-template-edit]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const id = btn.getAttribute("data-template-edit");
        pushRecentTemplate(id);
        if ($("templateSelect")) $("templateSelect").value = id;
        applyTemplate(id, { edit: true })
          .then(() => setStatus($("saveStatus"), dt("tplEditReady"), "ok"))
          .catch((err) => setStatus($("saveStatus"), err.message || dt("error"), "err"));
      });
    });
    host.querySelectorAll("[data-custom-template]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-custom-template");
        pushRecentTemplate(id);
        applyCustomTemplate(id).catch((e) => setStatus($("saveStatus"), e.message || dt("error"), "err"));
      });
    });
    host.querySelectorAll("[data-custom-del]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteCustomTemplate(btn.getAttribute("data-custom-del"));
      });
    });
    host.querySelectorAll("[data-team-template]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-team-template");
        pushRecentTemplate(id);
        applyTeamTemplate(id).catch(() => {});
      });
    });
    host.querySelectorAll("[data-team-del]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteTeamTemplate(btn.getAttribute("data-team-del")).catch(() => {});
      });
    });
    $("saveAsTemplateSideBtn")?.addEventListener("click", () => saveCurrentAsTemplate());
  }

  async function applyTeamTemplate(id) {
    if (!id) return;
    if (getText() && !confirm(dt("confirmTemplate"))) return;
    try {
      const data = await api(`/api/v2/docs/templates/${encodeURIComponent(id)}${companyQuery()}`);
      const tpl = data.template || {};
      let lay = {};
      try {
        lay = tpl.layout_json ? JSON.parse(tpl.layout_json) : {};
      } catch {
        lay = {};
      }
      if (lay && typeof lay === "object") Object.assign(layout, lay);
      applyLayoutToDom();
      const html = tpl.content_html || "<p><br></p>";
      const title = tpl.title || dt("tplBlank");
      if (!currentDoc?.id && activeCompanyId()) {
        await createBlank({ title, contentHtml: html, mode: "general" });
        setHtml(html);
      } else {
        setHtml(html);
      }
      if ($("docTitle")) $("docTitle").value = title;
      lastTemplateKey = `team:${id}`;
      markDirty();
      syncEmptyState();
      schedulePaperSync({ force: true, fit: true });
      setStatus($("saveStatus"), dt("templateReady", { name: title }), "ok");
    } catch (e) {
      setStatus($("saveStatus"), e.message || dt("templateSaveFail"), "err");
    }
  }

  async function deleteTeamTemplate(id) {
    if (!id || !confirm(dt("confirmDeleteTemplate"))) return;
    await api(`/api/v2/docs/templates/${encodeURIComponent(id)}${companyQuery()}`, { method: "DELETE" });
    renderTemplateGallery();
  }

  function setSideTab(tab) {
    const name = tab === "docs" ? "docs" : "templates";
    document.querySelectorAll("[data-side-tab]").forEach((btn) => {
      const on = btn.getAttribute("data-side-tab") === name;
      btn.classList.toggle("active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    document.querySelectorAll("[data-side-panel]").forEach((panel) => {
      const on = panel.getAttribute("data-side-panel") === name;
      panel.classList.toggle("active", on);
      panel.hidden = !on;
    });
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename || "dokument.pdf";
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 4000);
  }

  async function exportPdfBlob() {
    if (dirty || !currentDoc?.id) {
      try {
        await saveDoc();
      } catch {
        /* continue */
      }
    }
    if (!currentDoc?.id) throw new Error(dt("needSave"));
    const res = await fetch(
      `/api/v2/docs/${encodeURIComponent(currentDoc.id)}/export${companyQuery({ format: "pdf" })}`,
      { headers: authHeaders() },
    );
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error || `http_${res.status}`);
    }
    const blob = await res.blob();
    const cd = res.headers.get("Content-Disposition") || "";
    const match = /filename="([^"]+)"/i.exec(cd);
    const title = ($("docTitle")?.value || "dokument").trim().replace(/[\\/:*?"<>|]+/g, "_").slice(0, 80);
    const filename = match?.[1] || `${title || "dokument"}.pdf`;
    return { blob, filename };
  }

  function openEmailModal() {
    const modal = $("emailModal");
    if (!modal) {
      shareByEmailLocal().catch(() => {});
      return;
    }
    const title = ($("docTitle")?.value || dt("untitled")).trim();
    const company = companyBranding?.companyName || "";
    if ($("emailSubjectInput") && !$("emailSubjectInput").value) {
      $("emailSubjectInput").value = company ? `${title} (${company})` : title;
    }
    if ($("emailMessageInput") && !$("emailMessageInput").value) {
      $("emailMessageInput").value = [
        company || "",
        "",
        `Anbei das Dokument «${title}» als PDF.`,
        "",
        "— SUPPIX Docs",
      ]
        .filter((line, i, arr) => !(line === "" && arr[i - 1] === ""))
        .join("\n")
        .trim();
    }
    populateEmailWorkers();
    setStatus($("emailModalStatus"), "");
    modal.hidden = false;
    $("emailToInput")?.focus();
  }

  function closeEmailModal() {
    const modal = $("emailModal");
    if (modal) modal.hidden = true;
  }

  async function sendDocEmail() {
    const to = String($("emailToInput")?.value || "").trim();
    if (!to || !to.includes("@")) {
      setStatus($("emailModalStatus"), dt("emailNeedTo"), "err");
      return;
    }
    const openPh = collectOpenPlaceholders();
    if (openPh.length && !confirm(dt("emailOpenPhConfirm", { n: openPh.length }))) {
      renderPlaceholderCheck();
      return;
    }
    if (dirty || !currentDoc?.id) {
      try {
        await saveDoc();
      } catch (e) {
        setStatus($("emailModalStatus"), e.message || dt("emailPdfFail"), "err");
        return;
      }
    }
    if (!currentDoc?.id) {
      setStatus($("emailModalStatus"), dt("needSave"), "err");
      return;
    }
    setStatus($("emailModalStatus"), dt("emailSending"));
    setStatus($("saveStatus"), dt("emailSending"));
    try {
      await api(`/api/v2/docs/${encodeURIComponent(currentDoc.id)}/email${companyQuery()}`, {
        method: "POST",
        body: JSON.stringify({
          company_id: activeCompanyId(),
          to,
          subject: String($("emailSubjectInput")?.value || "").trim(),
          message: String($("emailMessageInput")?.value || "").trim(),
        }),
      });
      setStatus($("emailModalStatus"), dt("emailSentOk", { to }), "ok");
      setStatus($("saveStatus"), dt("emailSentOk", { to }), "ok");
      window.setTimeout(() => closeEmailModal(), 900);
    } catch (e) {
      const base = e.body?.message || e.message || dt("emailPdfFail");
      const hint = e.body?.hint || dt("emailSmtpHint");
      const msg = hint && !String(base).includes(hint) ? `${base} — ${hint}` : base;
      setStatus($("emailModalStatus"), msg, "err");
      setStatus($("saveStatus"), msg, "err");
    }
  }

  async function shareByEmail() {
    openEmailModal();
  }

  async function shareByEmailLocal() {
    const title = ($("docTitle")?.value || dt("untitled")).trim();
    const company = companyBranding?.companyName || "";
    const openPh = collectOpenPlaceholders();
    if (openPh.length && !confirm(dt("emailOpenPhConfirm", { n: openPh.length }))) {
      renderPlaceholderCheck();
      return;
    }
    setStatus($("saveStatus"), dt("emailPreparingPdf"));
    setStatus($("emailModalStatus"), dt("emailPreparingPdf"));
    try {
      const { blob, filename } = await exportPdfBlob();
      const file = new File([blob], filename, { type: "application/pdf" });
      const shareText = [
        company ? `${company}` : "",
        title,
        "",
        dt("emailPdfAttachedHint", { file: filename }),
      ]
        .filter(Boolean)
        .join("\n");

      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        await navigator.share({
          files: [file],
          title: company ? `${title} (${company})` : title,
          text: shareText,
        });
        setStatus($("saveStatus"), dt("emailSharedWithPdf"), "ok");
        setStatus($("emailModalStatus"), dt("emailSharedWithPdf"), "ok");
        return;
      }

      downloadBlob(blob, filename);
      const body = [
        company ? `${company}` : "",
        "",
        dt("emailPdfBody", { file: filename, title }),
        "",
        "—",
        getText().slice(0, 1200),
      ]
        .filter((line, i, arr) => !(line === "" && arr[i - 1] === ""))
        .join("\n");
      const mailto = `mailto:?subject=${encodeURIComponent(company ? `${title} (${company})` : title)}&body=${encodeURIComponent(body)}`;
      window.location.href = mailto;
      setStatus($("saveStatus"), dt("emailPdfDownloaded", { file: filename }), "ok");
      setStatus($("emailModalStatus"), dt("emailPdfDownloaded", { file: filename }), "ok");
    } catch (e) {
      setStatus($("saveStatus"), e.message || dt("emailPdfFail"), "err");
      setStatus($("emailModalStatus"), e.message || dt("emailPdfFail"), "err");
    }
  }

  async function copyTextToClipboard(text) {
    const value = String(text || "");
    if (!value) return false;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
        return true;
      }
    } catch {
      /* fallback */
    }
    try {
      const ta = document.createElement("textarea");
      ta.value = value;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      ta.remove();
      return !!ok;
    } catch {
      return false;
    }
  }

  function editorDeepLink() {
    const url = new URL(location.href);
    const cid = activeCompanyId();
    if (cid) url.searchParams.set("company_id", cid);
    if (currentDoc?.id) url.searchParams.set("id", currentDoc.id);
    else url.searchParams.delete("id");
    url.searchParams.delete("doc");
    return url.toString();
  }

  async function copyEditorLink() {
    if (!currentDoc?.id && dirty) {
      try {
        await saveDoc();
      } catch {
        /* ignore */
      }
    }
    if (!currentDoc?.id) {
      setStatus($("saveStatus"), dt("needSave"), "err");
      return;
    }
    const ok = await copyTextToClipboard(editorDeepLink());
    setStatus($("saveStatus"), ok ? dt("editorLinkCopied") : dt("clipboardFail"), ok ? "ok" : "err");
  }

  async function createShareLink() {
    openShareModal();
  }

  function openShareModal() {
    const modal = $("shareModal");
    if (!modal) {
      createShareLinkDirect().catch(() => {});
      return;
    }
    modal.hidden = false;
    if ($("shareUrlOutput")) {
      $("shareUrlOutput").hidden = true;
      $("shareUrlOutput").value = "";
    }
    setStatus($("shareModalStatus"), "");
    window.DocsIcons?.mountAll(modal, true);
  }

  function closeShareModal() {
    const modal = $("shareModal");
    if (modal) modal.hidden = true;
  }

  async function createShareLinkDirect() {
    if (dirty) {
      try {
        await saveDoc();
      } catch {
        /* continue if saved id exists */
      }
    }
    if (!currentDoc?.id) {
      setStatus($("saveStatus"), dt("needSave"), "err");
      return;
    }
    const hours = Number($("shareTtlSelect")?.value || 72);
    const password = String($("sharePasswordInput")?.value || "").trim();
    const requireApproved = !!$("shareApprovedOnly")?.checked;
    setStatus($("shareModalStatus") || $("saveStatus"), dt("shareCreating"));
    try {
      const data = await api(`/api/v2/docs/${encodeURIComponent(currentDoc.id)}/share${companyQuery()}`, {
        method: "POST",
        body: JSON.stringify({
          company_id: activeCompanyId(),
          ttlHours: hours,
          password,
          requireApproved,
        }),
      });
      let url = data.url || `${location.origin}/admin-v2/docs-share.html?t=${encodeURIComponent(data.token || "")}`;
      try {
        const parsed = new URL(url, location.origin);
        parsed.protocol = location.protocol;
        parsed.host = location.host;
        url = parsed.toString();
      } catch {
        /* keep */
      }
      if ($("shareUrlOutput")) {
        $("shareUrlOutput").hidden = false;
        $("shareUrlOutput").value = url;
      }
      const ok = await copyTextToClipboard(url);
      setStatus(
        $("shareModalStatus") || $("saveStatus"),
        ok ? dt("shareLinkCopied", { h: data.ttlHours || hours }) : url,
        ok ? "ok" : "",
      );
      setStatus($("saveStatus"), ok ? dt("shareLinkCopied", { h: data.ttlHours || hours }) : url, ok ? "ok" : "");
      if (ok && confirm(dt("shareOpenConfirm"))) window.open(url, "_blank", "noopener");
    } catch (e) {
      setStatus($("shareModalStatus") || $("saveStatus"), e.message || dt("shareFail"), "err");
    }
  }

  async function revokeAllShares() {
    if (!currentDoc?.id) return;
    if (!confirm(dt("shareRevokeConfirm"))) return;
    try {
      const data = await api(`/api/v2/docs/${encodeURIComponent(currentDoc.id)}/share/revoke${companyQuery()}`, {
        method: "POST",
        body: JSON.stringify({ company_id: activeCompanyId() }),
      });
      setStatus($("shareModalStatus") || $("saveStatus"), dt("shareRevoked", { n: data.revoked || 0 }), "ok");
    } catch (e) {
      setStatus($("shareModalStatus") || $("saveStatus"), e.message || dt("shareFail"), "err");
    }
  }

  async function importDocxFile(file) {
    if (!file) return;
    const cid = activeCompanyId();
    if (!cid) {
      setStatus($("saveStatus"), dt("needCompany"), "err");
      return;
    }
    const asNew = confirm(dt("confirmImportDocxNew"));
    if (!asNew && getText() && !confirm(dt("confirmImportDocx"))) return;
    setStatus($("saveStatus"), dt("importingDocx"));
    try {
      const fd = new FormData();
      fd.append("file", file, file.name || "import.docx");
      fd.append("create", asNew ? "1" : "0");
      const data = await apiUpload(`/api/v2/docs/import-docx${companyQuery()}`, fd);
      if (asNew && data.document) {
        await openDoc(data.document.id);
        setStatus($("saveStatus"), dt("importDocxDone"), "ok");
        return;
      }
      setHtml(data.contentHtml || "<p><br></p>");
      if ($("docTitle") && data.title && (!$("docTitle").value || $("docTitle").value === dt("untitled") || $("docTitle").value === dt("tplBlank"))) {
        $("docTitle").value = data.title;
      }
      markDirty();
      schedulePaperSync({ force: true, fit: true });
      setStatus($("saveStatus"), dt("importDocxDone"), "ok");
    } catch (e) {
      setStatus($("saveStatus"), e.message || dt("importDocxFail"), "err");
    }
  }

  function pickImportDocx() {
    const input = $("importDocxInput");
    if (!input) return;
    input.value = "";
    input.click();
  }

  function insertTableOfContents() {
    if (!quill?.root) return;
    const heads = [...quill.root.querySelectorAll("h1, h2, h3")].filter((h) => (h.textContent || "").trim());
    if (!heads.length) {
      setStatus($("saveStatus"), dt("tocEmpty"), "err");
      return;
    }
    heads.forEach((h, i) => {
      if (!h.id) h.id = `sec-${i + 1}-${Date.now().toString(36)}`;
    });
    const items = heads
      .map((h) => {
        const level = h.tagName === "H1" ? 1 : h.tagName === "H2" ? 2 : 3;
        return `<li class="toc-l${level}"><a href="#${escapeHtml(h.id)}">${escapeHtml((h.textContent || "").trim())}</a></li>`;
      })
      .join("");
    insertHtmlAtCursor(
      `<div class="wp-toc" contenteditable="false"><p><strong>${escapeHtml(dt("tocTitle"))}</strong></p><ul>${items}</ul></div><p><br></p>`,
    );
    setStatus($("saveStatus"), dt("tocInserted"), "ok");
  }

  function syncMergeWorkerSelect() {
    const src = $("workerSelect");
    const dst = $("mergeWorkerSelect");
    if (!src || !dst) return;
    dst.innerHTML = src.innerHTML;
    dst.value = selectedWorkerId || src.value || "";
  }

  function mergeValueLooksFilled(val) {
    const s = String(val ?? "").trim();
    return !!s && s !== "—" && s !== "-";
  }

  async function refreshMergePreview() {
    const will = $("mergeWillList");
    const open = $("mergeOpenList");
    if (!will || !open) return;
    const cid = activeCompanyId();
    if (!cid) {
      will.innerHTML = "";
      open.innerHTML = `<li>${escapeHtml(dt("needCompanyShort"))}</li>`;
      return;
    }
    const workerId = $("mergeWorkerSelect")?.value || selectedWorkerId || $("workerSelect")?.value || "";
    try {
      const data = await api(
        `/api/v2/docs/merge-context${companyQuery({ worker_id: workerId || undefined })}`,
      );
      const fields = data.fields || {};
      const placeholders = collectOpenPlaceholders();
      const willItems = [];
      const openItems = [];
      placeholders.forEach((it) => {
        const key = String(it.token || "")
          .replace(/^\{\{\s*/, "")
          .replace(/\s*\}\}$/, "");
        const val = fields[key];
        if (mergeValueLooksFilled(val)) willItems.push({ token: it.token, value: val });
        else openItems.push({ token: it.token });
      });
      will.innerHTML = willItems.length
        ? willItems
            .map(
              (it) =>
                `<li><code>${escapeHtml(it.token)}</code><span>${escapeHtml(String(it.value).slice(0, 48))}</span></li>`,
            )
            .join("")
        : `<li class="is-muted">${escapeHtml(dt("mergeNoneFill"))}</li>`;
      open.innerHTML = openItems.length
        ? openItems.map((it) => `<li><code>${escapeHtml(it.token)}</code></li>`).join("")
        : `<li class="is-ok">${escapeHtml(dt("placeholdersClear"))}</li>`;
      setStatus(
        $("mergeModalStatus"),
        dt("mergePreviewStats", { n: willItems.length, open: openItems.length }),
        openItems.length ? "" : "ok",
      );
    } catch (e) {
      will.innerHTML = "";
      open.innerHTML = `<li>${escapeHtml(e.message || dt("fillFail"))}</li>`;
    }
  }

  function openMergeFillModal() {
    const modal = $("mergeModal");
    if (!modal) {
      applyMergeFill().catch(() => {});
      return;
    }
    syncMergeWorkerSelect();
    setStatus($("mergeModalStatus"), "");
    modal.hidden = false;
    refreshMergePreview().catch(() => {});
  }

  function closeMergeFillModal() {
    const modal = $("mergeModal");
    if (modal) modal.hidden = true;
  }

  async function applyMergeFill() {
    const cid = activeCompanyId();
    if (!cid) {
      setStatus($("saveStatus"), dt("needCompanyShort"), "err");
      setStatus($("mergeModalStatus"), dt("needCompanyShort"), "err");
      return;
    }
    const workerId =
      $("mergeWorkerSelect")?.value || selectedWorkerId || $("workerSelect")?.value || "";
    if (workerId) {
      selectedWorkerId = workerId;
      if ($("workerSelect")) $("workerSelect").value = workerId;
    }
    setStatus($("saveStatus"), dt("filling"));
    setStatus($("mergeModalStatus"), dt("filling"));
    try {
      const data = await api(`/api/v2/docs/fill-merge${companyQuery()}`, {
        method: "POST",
        body: JSON.stringify({
          company_id: cid,
          workerId,
          contentHtml: getHtml(),
          headerHtml: getHeaderHtml(),
          footerHtml: getFooterHtml(),
        }),
      });
      setHtml(data.contentHtml || getHtml());
      if ($("docHeader") && typeof data.headerHtml === "string") {
        $("docHeader").innerHTML = wrapMergePlaceholders(data.headerHtml);
      }
      if ($("docFooter") && typeof data.footerHtml === "string") {
        $("docFooter").innerHTML = wrapMergePlaceholders(data.footerHtml);
      }
      applyLayoutToDom();
      markDirty();
      const unresolved = data.unresolved || [];
      const msg = unresolved.length
        ? dt("placeholderOpen", { list: unresolved.join(", ") })
        : dt("placeholderFilled");
      setStatus($("saveStatus"), msg, unresolved.length ? "" : "ok");
      setStatus($("mergeModalStatus"), msg, unresolved.length ? "" : "ok");
      renderPlaceholderCheck(unresolved);
      if (!unresolved.length) window.setTimeout(() => closeMergeFillModal(), 700);
      else refreshMergePreview().catch(() => {});
    } catch (e) {
      setStatus($("saveStatus"), e.message || dt("fillFail"), "err");
      setStatus($("mergeModalStatus"), e.message || dt("fillFail"), "err");
    }
  }

  async function fillMergeFields() {
    openMergeFillModal();
  }

  function collectOpenPlaceholders() {
    const hay = [
      getHeaderHtml(),
      getHtml(),
      getFooterHtml(),
      String($("docTitle")?.value || ""),
    ].join("\n");
    const found = new Map();
    const re = /\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}/g;
    let m;
    while ((m = re.exec(hay))) {
      const token = `{{${m[1]}}}`;
      found.set(token, (found.get(token) || 0) + 1);
    }
    return [...found.entries()].map(([token, count]) => ({ token, count }));
  }

  function renderPlaceholderCheck(forcedList) {
    const list = $("placeholderCheckList");
    const status = $("placeholderCheckStatus");
    if (!list) return;
    const items = Array.isArray(forcedList)
      ? forcedList.map((token) => ({ token: String(token), count: 1 }))
      : collectOpenPlaceholders();
    if (!items.length) {
      list.hidden = true;
      list.innerHTML = "";
      if (status) {
        status.hidden = false;
        status.textContent = dt("placeholdersClear");
        status.classList.add("is-ok");
        status.classList.remove("is-err");
      }
      return;
    }
    list.hidden = false;
    list.innerHTML = items
      .map(
        (it, i) =>
          `<li><button type="button" class="placeholder-check-item" data-ph="${i}" title="${escapeHtml(it.token)}">` +
          `<code>${escapeHtml(it.token)}</code>` +
          `<span>×${it.count || 1}</span></button></li>`,
      )
      .join("");
    list._phItems = items;
    if (status) {
      status.hidden = false;
      status.textContent = dt("placeholdersOpen", { n: items.length });
      status.classList.add("is-err");
      status.classList.remove("is-ok");
    }
  }

  function jumpToPlaceholder(token) {
    if (!token) return;
    openFindBar();
    if ($("findInput")) {
      $("findInput").value = token;
      runFind(token);
    }
  }

  function hideAiOperatorForPrint(hide) {
    document.body.classList.toggle("docs-printing", !!hide);
    document.querySelectorAll(".aio-root, #aioOperatorRoot, .aio-backdrop").forEach((el) => {
      if (hide) {
        if (!el.dataset.wpPrintDisplay) el.dataset.wpPrintDisplay = el.style.display || "";
        el.style.setProperty("display", "none", "important");
        el.setAttribute("aria-hidden", "true");
      } else {
        const prev = el.dataset.wpPrintDisplay;
        el.style.removeProperty("display");
        if (prev) el.style.display = prev;
        delete el.dataset.wpPrintDisplay;
        el.removeAttribute("aria-hidden");
      }
    });
  }

  let listCache = [];
  let listFilter = "";
  let statusFilter = "";

  function statusLabel(status) {
    const s = String(status || "draft");
    if (s === "in_review") return dt("statusReview");
    if (s === "approved") return dt("statusApproved");
    if (s === "archived") return dt("statusArchived");
    return dt("statusDraft");
  }

  function modeLabel(mode) {
    const m = String(mode || "general");
    if (m === "contract") return dt("modeContract");
    if (m === "workforce") return dt("modeWorkforce");
    return dt("modeGeneral");
  }

  function renderStatusFilters() {
    const host = $("docsStatusFilters");
    if (!host) return;
    const opts = [
      { id: "", label: dt("docs") },
      { id: "draft", label: dt("statusDraft") },
      { id: "in_review", label: dt("statusReview") },
      { id: "approved", label: dt("statusApproved") },
      { id: "archived", label: dt("statusArchived") },
    ];
    host.innerHTML = opts
      .map(
        (o) =>
          `<button type="button" class="chip${statusFilter === o.id ? " active" : ""}" data-status-filter="${escapeHtml(o.id)}">${escapeHtml(o.label)}</button>`,
      )
      .join("");
    host.querySelectorAll("[data-status-filter]").forEach((btn) => {
      btn.addEventListener("click", () => {
        statusFilter = btn.getAttribute("data-status-filter") || "";
        renderStatusFilters();
        renderDocsList(currentDoc?.id);
      });
    });
  }

  function renderDocsList(selectId) {
    const list = $("docsList");
    if (!list) return;
    const q = String(listFilter || "").trim().toLowerCase();
    const items = listCache.filter((d) => {
      if (statusFilter && String(d.status || "draft") !== statusFilter) return false;
      if (!q) return true;
      const hay = `${d.title || ""} ${d.status || ""} ${d.mode || ""}`.toLowerCase();
      return hay.includes(q);
    });
    if (!listCache.length) {
      list.innerHTML = `<li><p class="empty-list">${escapeHtml(dt("emptyDocs"))}</p></li>`;
      return;
    }
    if (!items.length) {
      list.innerHTML = `<li><p class="empty-list">${escapeHtml(dt("listEmpty"))}</p></li>`;
      return;
    }
    list.innerHTML = items
      .map((d) => {
        const active = selectId && d.id === selectId ? " active" : "";
        const mode = String(d.mode || "general");
        const st = String(d.status || "draft");
        return `<li><button type="button" data-id="${escapeHtml(d.id)}" class="${active}">
          <span class="doc-title">${escapeHtml(d.title || "—")}</span>
          <span class="doc-badges">
            <span class="doc-badge mode-${escapeHtml(mode)}">${escapeHtml(modeLabel(mode))}</span>
            <span class="doc-badge status-${escapeHtml(st)}">${escapeHtml(statusLabel(st))}</span>
          </span>
          <span class="doc-sub">${escapeHtml(formatWhen(d.updated_at))}</span>
        </button></li>`;
      })
      .join("");
    list.querySelectorAll("button[data-id]").forEach((btn) => {
      btn.addEventListener("click", () => openDoc(btn.getAttribute("data-id")));
    });
  }

  async function refreshVersions() {
    const list = $("versionsList");
    const status = $("versionsStatus");
    if (!list || !status) return;
    if (!currentDoc?.id) {
      list.innerHTML = `<li><p class="empty-list">${escapeHtml(dt("versionsNoneOpen"))}</p></li>`;
      setStatus(status, "—");
      return;
    }
    setStatus(status, dt("listLoading"));
    try {
      const data = await api(`/api/v2/docs/${encodeURIComponent(currentDoc.id)}/versions${companyQuery()}`);
      const items = data.items || [];
      setStatus(status, items.length ? dt("versionsCount", { n: items.length }) : "—");
      if (!items.length) {
        list.innerHTML = `<li><p class="empty-list">${escapeHtml(dt("versionsEmpty"))}</p></li>`;
        return;
      }
      list.innerHTML = items
        .map(
          (v) => `<li class="version-row">
          <button type="button" class="version-open" data-version="${escapeHtml(v.id)}">
            <span class="doc-title">${escapeHtml(v.note || dt("versionNote"))}</span>
            <span class="doc-badge ver">v${escapeHtml(String(v.version_no ?? "?"))}</span>
            <span class="doc-sub">${escapeHtml(formatWhen(v.created_at))}</span>
          </button>
          <div class="version-actions">
            <button type="button" class="cmd quiet" data-diff="${escapeHtml(v.id)}" data-di18n="diffBtn">Diff</button>
            <button type="button" class="cmd quiet" data-restore="${escapeHtml(v.id)}" data-di18n="diffRestore">Wiederherstellen</button>
          </div>
        </li>`,
        )
        .join("");
      list.querySelectorAll("button[data-diff]").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          openVersionDiff(btn.getAttribute("data-diff")).catch((err) =>
            setStatus($("saveStatus"), err.message, "err"),
          );
        });
      });
      list.querySelectorAll("button[data-restore]").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          restoreVersion(btn.getAttribute("data-restore")).catch((err) =>
            setStatus($("saveStatus"), err.message, "err"),
          );
        });
      });
      // Keep row click as restore for power users who expect old behavior? Better: open diff.
      list.querySelectorAll("button[data-version]").forEach((btn) => {
        btn.addEventListener("click", () =>
          openVersionDiff(btn.getAttribute("data-version")).catch((e) =>
            setStatus($("saveStatus"), e.message, "err"),
          ),
        );
      });
      if (typeof window.applyDocsPageI18n === "function") {
        // Re-apply only version buttons labels without full page refresh
        list.querySelectorAll("[data-di18n]").forEach((el) => {
          const key = el.getAttribute("data-di18n");
          if (key) el.textContent = dt(key);
        });
      }
    } catch (e) {
      setStatus(status, e.message || dt("listFail"), "err");
    }
  }

  async function restoreVersion(versionId) {
    if (!currentDoc?.id || !versionId) return;
    if (!confirm(dt("confirmVersion"))) return;
    setStatus($("saveStatus"), dt("restoring"));
    const data = await api(
      `/api/v2/docs/${encodeURIComponent(currentDoc.id)}/versions/${encodeURIComponent(versionId)}/restore${companyQuery()}`,
      {
        method: "POST",
        body: JSON.stringify({ company_id: activeCompanyId() }),
      },
    );
    loadIntoEditor(data.document);
    await refreshVersions();
    setStatus($("saveStatus"), dt("versionRestored"), "ok");
  }

  async function runAiSuggest(action) {
    const cid = activeCompanyId();
    if (!cid) {
      setStatus($("saveStatus"), dt("needCompanyShort"), "err");
      return;
    }
    if (!getText()) {
      setStatus($("saveStatus"), dt("noAiText"), "err");
      return;
    }
    setStatus($("saveStatus"), dt("aiWorking"));
    try {
      const data = await api(`/api/v2/docs/suggest${companyQuery()}`, {
        method: "POST",
        body: JSON.stringify({
          company_id: cid,
          contentHtml: getHtml(),
          action,
          lang: typeof window.getDocsPageLang === "function" ? window.getDocsPageLang() : "de",
        }),
      });
      if (!data.ok) {
        setStatus($("saveStatus"), data.error || dt("error"), "err");
        return;
      }
      if (data.contentHtml && data.contentHtml !== getHtml()) {
        if (!confirm(dt("confirmAi"))) {
          setStatus($("saveStatus"), dt("aiDiscarded"), "");
          return;
        }
        setHtml(data.contentHtml);
        markDirty();
      }
      const hint = data.hint ? ` · ${data.hint}` : "";
      setStatus($("saveStatus"), `${dt("aiOk", { provider: data.provider || "local" })}${hint}`, "ok");
    } catch (e) {
      setStatus($("saveStatus"), e.message || dt("error"), "err");
    }
  }

  async function exportDoc(fmt) {
    if (!currentDoc?.id) {
      await saveDoc();
    }
    if (!currentDoc?.id) {
      setStatus($("saveStatus"), dt("needSave"), "err");
      return;
    }
    if (dirty) await saveDoc();
    if (refreshTocBlocks()) {
      markDirty();
      try {
        await saveDoc();
      } catch {
        /* continue export */
      }
    }
    setStatus($("saveStatus"), "…");
    try {
      const res = await fetch(
        `/api/v2/docs/${encodeURIComponent(currentDoc.id)}/export${companyQuery({ format: fmt })}`,
        { headers: authHeaders() },
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || `http_${res.status}`);
      }
      const blob = await res.blob();
      const cd = res.headers.get("Content-Disposition") || "";
      const match = /filename="([^"]+)"/i.exec(cd);
      const ext = fmt === "pdf" ? "pdf" : fmt === "doc" || fmt === "docx" ? "docx" : "html";
      const filename = match?.[1] || `dokument.${ext}`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setStatus($("saveStatus"), dt("exportOk", { fmt: String(fmt).toUpperCase() }), "ok");
    } catch (e) {
      setStatus($("saveStatus"), e.message || dt("exportFail"), "err");
    }
  }

  let ooEditor = null;

  function loadScriptOnce(src) {
    return new Promise((resolve, reject) => {
      const existing = document.querySelector(`script[data-oo-src="${src}"]`);
      if (existing) {
        if (window.DocsAPI) resolve();
        else existing.addEventListener("load", () => resolve());
        return;
      }
      const s = document.createElement("script");
      s.src = src;
      s.async = true;
      s.dataset.ooSrc = src;
      s.onload = () => resolve();
      s.onerror = () => reject(new Error("OnlyOffice api.js nicht erreichbar"));
      document.head.appendChild(s);
    });
  }

  async function openWordPro() {
    if (dirty) await saveDoc();
    if (!currentDoc?.id) {
      await saveDoc();
    }
    if (!currentDoc?.id) {
      setStatus($("saveStatus"), dt("needSave"), "err");
      return;
    }
    setStatus($("ooStatus"), dt("ooLoading"));
    setStatus($("saveStatus"), dt("wordPro"));
    try {
      const status = await api(`/api/v2/docs/onlyoffice/status${companyQuery()}`);
      if (!status.enabled) {
        const msg = status.hint || dt("ooNeed");
        setStatus($("saveStatus"), msg, "err");
        window.alert(msg);
        return;
      }
      const data = await api(
        `/api/v2/docs/${encodeURIComponent(currentDoc.id)}/onlyoffice/config${companyQuery({ mode: "edit" })}`,
      );
      if (!data.ok || !data.config) throw new Error(data.error || "config_failed");
      await loadScriptOnce(data.scriptUrl);
      if (!window.DocsAPI?.DocEditor) throw new Error(dt("ooFail"));

      $("ooOverlay")?.classList.add("open");
      $("ooOverlay")?.setAttribute("aria-hidden", "false");
      const host = $("onlyofficeEditor");
      if (host) host.innerHTML = "";
      if (ooEditor?.destroyEditor) {
        try {
          ooEditor.destroyEditor();
        } catch {
          /* ignore */
        }
      }
      ooEditor = new window.DocsAPI.DocEditor("onlyofficeEditor", data.config);
      setStatus($("ooStatus"), dt("ooActive"));
      setStatus($("saveStatus"), dt("ooOpened"), "ok");
    } catch (e) {
      const msg = e.message || dt("ooFail");
      setStatus($("ooStatus"), msg, "err");
      setStatus($("saveStatus"), msg, "err");
      $("ooOverlay")?.classList.remove("open");
      window.alert(dt("ooUnavailable", { msg }));
    }
  }

  async function closeWordPro() {
    if (ooEditor?.destroyEditor) {
      try {
        ooEditor.destroyEditor();
      } catch {
        /* ignore */
      }
    }
    ooEditor = null;
    $("ooOverlay")?.classList.remove("open");
    $("ooOverlay")?.setAttribute("aria-hidden", "true");
    const host = $("onlyofficeEditor");
    if (host) host.innerHTML = "";
    if (currentDoc?.id) {
      try {
        await openDoc(currentDoc.id);
        setStatus($("saveStatus"), dt("ooUpdated"), "ok");
      } catch (e) {
        setStatus($("saveStatus"), e.message || dt("error"), "err");
      }
    }
  }

  function renderDocMeta(doc) {
    const bits = [
      doc?.id ? dt("metaId", { id: String(doc.id).slice(0, 8) }) : dt("newDoc"),
      doc?.updated_at ? dt("metaUpdated", { when: formatWhen(doc.updated_at) }) : "",
      doc?.contract_id ? dt("metaContract", { id: String(doc.contract_id).slice(0, 8) }) : "",
      doc?.worker_id ? dt("metaWorker", { id: String(doc.worker_id).slice(0, 8) }) : "",
      doc?.status ? dt("metaStatus", { status: statusLabel(doc.status) }) : "",
    ].filter(Boolean);
    $("docMeta").textContent = bits.join(" · ") || "—";
    if ($("docStatus") && doc?.status) {
      $("docStatus").value = doc.status;
    }
    syncWorkflowUi(doc?.status || $("docStatus")?.value || "draft");
  }

  const WORKFLOW_ORDER = ["draft", "in_review", "approved"];

  function syncWorkflowUi(status) {
    const st = String(status || "draft").toLowerCase();
    const badge = $("workflowBadge");
    const badgeLabel = $("workflowBadgeLabel");
    if (badge) badge.setAttribute("data-status", st === "archived" ? "archived" : st);
    if (badgeLabel) badgeLabel.textContent = statusLabel(st);
    $("workflowSteps")?.querySelectorAll("[data-wf]").forEach((li) => {
      const step = li.getAttribute("data-wf");
      const idx = WORKFLOW_ORDER.indexOf(step);
      const cur = WORKFLOW_ORDER.indexOf(st === "archived" ? "approved" : st);
      li.classList.toggle("is-current", step === st || (st === "archived" && step === "approved"));
      li.classList.toggle("is-done", idx >= 0 && cur > idx);
    });
    const nextBtn = $("workflowNextBtn");
    const approveBtn = $("workflowApproveBtn");
    const unlockBtn = $("workflowUnlockBtn");
    const hint = $("workflowHint");
    if (nextBtn) {
      nextBtn.hidden = st !== "draft";
      nextBtn.textContent = dt("workflowNext");
    }
    if (approveBtn) {
      approveBtn.hidden = st !== "in_review";
    }
    if (unlockBtn) {
      unlockBtn.hidden = !(st === "approved" || st === "archived");
    }
    if (hint) {
      if (st === "draft") hint.textContent = dt("workflowHintDraft");
      else if (st === "in_review") hint.textContent = dt("workflowHintReview");
      else if (st === "approved") hint.textContent = dt("workflowHintApproved");
      else if (st === "archived") hint.textContent = dt("workflowHintArchived");
    }
    const locked = st === "approved" || st === "archived";
    document.body.classList.toggle("docs-workflow-locked", locked);
    if (quill) {
      try {
        quill.enable(!locked);
      } catch {
        /* ignore */
      }
    }
    $("docHeader")?.setAttribute("contenteditable", locked ? "false" : "true");
    $("docFooter")?.setAttribute("contenteditable", locked ? "false" : "true");
  }

  async function setDocStatus(status) {
    if (!currentDoc?.id) {
      setStatus($("saveStatus"), dt("needSave"), "err");
      return;
    }
    if (dirty) {
      try {
        await saveDoc();
      } catch {
        /* continue */
      }
    }
    setStatus($("saveStatus"), dt("statusUpdating"));
    try {
      const data = await api(`/api/v2/docs/${encodeURIComponent(currentDoc.id)}/status${companyQuery()}`, {
        method: "POST",
        body: JSON.stringify({ company_id: activeCompanyId(), status }),
      });
      currentDoc = data.document;
      renderDocMeta(currentDoc);
      maybeAutoWatermark(status);
      setStatus($("saveStatus"), dt("statusSet", { status: statusLabel(status) }), "ok");
      await refreshList(currentDoc?.id);
    } catch (e) {
      setStatus($("saveStatus"), e.message || dt("statusFail"), "err");
    }
  }

  async function publishToWorker(opts = {}) {
    if (!opts.skipPreflight) {
      openPreflight("publish");
      return;
    }
    if (dirty) await saveDoc();
    if (!currentDoc?.id) {
      setStatus($("saveStatus"), dt("needSave"), "err");
      return;
    }
    const workerId =
      selectedWorkerId ||
      ($("workerSelect")?.value || "").trim() ||
      currentDoc?.worker_id ||
      qs().get("worker_id") ||
      "";
    if (!workerId) {
      setStatus($("saveStatus"), dt("needWorker"), "err");
      return;
    }
    if (!confirm(dt("confirmPublish"))) {
      return;
    }
    setStatus($("saveStatus"), dt("publishing"));
    try {
      const data = await api(`/api/v2/docs/${encodeURIComponent(currentDoc.id)}/publish${companyQuery()}`, {
        method: "POST",
        body: JSON.stringify({
          company_id: activeCompanyId(),
          workerId,
          notify: true,
          docType: "sonstiges",
        }),
      });
      currentDoc = data.document;
      syncWorkerSelect(workerId);
      renderDocMeta(currentDoc);
      if ($("docStatus")) $("docStatus").value = currentDoc?.status || "archived";
      setStatus(
        $("saveStatus"),
        dt("published", { id: String(data.workerDocumentId || "").slice(0, 10) }),
        "ok",
      );
      await refreshList(currentDoc?.id);
      await refreshVersions();
    } catch (e) {
      setStatus($("saveStatus"), e.message || dt("publishFail"), "err");
    }
  }

  function clearPaperBands() {
    if ($("docHeader")) $("docHeader").innerHTML = "";
    if ($("docFooter")) $("docFooter").innerHTML = "";
  }

  function loadIntoEditor(doc) {
    currentDoc = doc;
    $("docTitle").value = doc?.title || "Unbenannt";
    $("docMode").value = doc?.mode || "general";
    syncWorkerSelect(doc?.worker_id || qs().get("worker_id") || "");
    renderDocMeta(doc);
    syncContractChrome(doc);

    // Always reset bands first — otherwise the previous doc's letterhead leaks.
    clearPaperBands();

    let loaded = false;
    if (doc?.content_json) {
      try {
        const parsed = typeof doc.content_json === "string" ? JSON.parse(doc.content_json) : doc.content_json;
        if (parsed && parsed.schema === "workpass-doc-v2") {
          if (parsed.layout) layout = { ...layout, ...parsed.layout };
          if (!PAPER_SIZES[layout.pageSize]) layout.pageSize = "a4";
          applyLayoutToDom();
          if ($("docHeader")) $("docHeader").innerHTML = parsed.headerHtml || "";
          if ($("docFooter")) $("docFooter").innerHTML = parsed.footerHtml || "";
          // Prefer HTML so Word-like classes (subtitle, caption, tables) round-trip.
          if (doc.content_html) {
            setHtml(doc.content_html);
            loaded = true;
          } else if (parsed.bodyDelta && parsed.bodyDelta.ops) {
            quill.setContents(parsed.bodyDelta);
            loaded = true;
          }
        } else if (parsed && parsed.ops) {
          quill.setContents(parsed);
          loaded = true;
        }
      } catch {
        /* fall through */
      }
    }
    if (!loaded) {
      applyLayoutToDom();
      if (doc?.content_html) setHtml(doc.content_html);
      else if (doc?.content_text) setHtml(plainToHtml(doc.content_text));
      else setHtml("<p><br></p>");
    }
    dirty = false;
    lastKnownUpdatedAt = String(doc?.updated_at || "");
    lastKnownContentHash = "";
    hideCollabConflict();
    setStatus($("saveStatus"), dt("loaded"), "ok");
    updatePageLabel();
    refreshVersions().catch(() => {});
    maybeOfferOfflineDraft(doc);
    startPresenceLoop();
    syncEmptyState();
    maybeAutoWatermark(doc?.status);
    // Company letterhead on every paper; strip leftover platform dual-brand headers.
    if ($("useLetterhead")) $("useLetterhead").checked = true;
    ensureCompanyLetterhead({ silent: true });
  }

  async function refreshList(selectId) {
    const cid = activeCompanyId();
    if (!cid) {
      setStatus($("listStatus"), dt("needCompany"), "err");
      listCache = [];
      $("docsList").innerHTML = `<li><p class="empty-list">${escapeHtml(dt("emptyCompany"))}</p></li>`;
      return;
    }
    setStatus($("listStatus"), dt("listLoading"));
    try {
      const data = await api(`/api/v2/docs${companyQuery()}`);
      listCache = data.items || [];
      setStatus(
        $("listStatus"),
        listCache.length ? dt("listCount", { n: listCache.length }) : dt("listEmpty"),
      );
      renderDocsList(selectId || currentDoc?.id);
    } catch (e) {
      setStatus($("listStatus"), e.message || dt("listFail"), "err");
    }
  }

  async function openDoc(id) {
    if (!id) return;
    if (dirty && currentDoc?.id && currentDoc.id !== id) {
      if (!confirm(dt("confirmSwitch"))) return;
    }
    const data = await api(`/api/v2/docs/${encodeURIComponent(id)}${companyQuery()}`);
    loadIntoEditor(data.document);
    syncDocUrl(id);
    maybeAutoWatermark(data.document?.status);
    await refreshList(id);
    setSideTab("docs");
  }

  async function createBlank(opts = {}) {
    const cid = activeCompanyId();
    if (!cid) {
      setStatus($("saveStatus"), dt("needCompany"), "err");
      return null;
    }
    const body = {
      company_id: cid,
      title: opts.title || dt("tplBlank"),
      mode: opts.mode || "general",
      contentHtml: opts.contentHtml || "<p><br></p>",
      contentText: opts.contentText || "",
      contentJson: opts.contentJson || "",
      contractId: opts.contractId || "",
      workerId: opts.workerId || "",
    };
    const data = await api(`/api/v2/docs${companyQuery()}`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    loadIntoEditor(data.document);
    ensureCompanyLetterhead({ force: true, silent: true });
    await refreshList(data.document?.id);
    syncEmptyState();
    startPresenceLoop();
    return data.document;
  }

  async function saveDoc() {
    const cid = activeCompanyId();
    if (!cid) {
      setStatus($("saveStatus"), dt("needCompany"), "err");
      return;
    }
    const payload = payloadFromEditor();
    setStatus($("saveStatus"), dt("saving"));
    try {
      let data;
      if (currentDoc?.id) {
        data = await api(`/api/v2/docs/${encodeURIComponent(currentDoc.id)}${companyQuery()}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
      } else {
        data = await api(`/api/v2/docs${companyQuery()}`, {
          method: "POST",
          body: JSON.stringify(payload),
        });
      }
      currentDoc = data.document;
      dirty = false;
      lastSavedAt = Date.now();
      lastKnownUpdatedAt = String(currentDoc?.updated_at || lastKnownUpdatedAt || "");
      lastKnownContentHash = "";
      hideCollabConflict();
      clearOfflineDraft(currentDoc?.id || "new");
      hideOfflineBanner();
      renderDocMeta(currentDoc);
      syncWorkerSelect(currentDoc?.worker_id || selectedWorkerId);
      syncContractChrome(currentDoc);
      syncDocUrl(currentDoc?.id);
      refreshTocBlocks();
      maybeAutoWatermark(currentDoc?.status);
      setStatus(
        $("saveStatus"),
        autosavePass
          ? dt("autosaved", { when: formatRelativeWhen(new Date().toISOString()) })
          : dt("saved"),
        "ok",
      );
      await refreshList(currentDoc?.id);
      await refreshVersions();
    } catch (e) {
      persistOfflineDraft();
      setStatus($("saveStatus"), `${e.message || dt("saveFail")} · ${dt("offlineKept")}`, "err");
    }
  }

  let autosavePass = false;
  let lastSavedAt = 0;

  function scheduleAutosave() {
    if (saveTimer) clearTimeout(saveTimer);
    const delay = peerCount > 0 ? 2000 : 4000;
    saveTimer = setTimeout(() => {
      if (!dirty) return;
      autosavePass = true;
      saveDoc()
        .catch(() => {})
        .finally(() => {
          autosavePass = false;
        });
    }, delay);
  }

  async function deleteDoc() {
    if (!currentDoc?.id) return;
    if (!confirm(dt("confirmDelete"))) return;
    await api(`/api/v2/docs/${encodeURIComponent(currentDoc.id)}${companyQuery()}`, { method: "DELETE" });
    currentDoc = null;
    lastTemplateKey = "";
    appliedLiveRev = 0;
    liveRev = 0;
    clearPaperBands();
    setHtml("<p><br></p>");
    if ($("docTitle")) $("docTitle").value = "";
    dirty = false;
    setStatus($("saveStatus"), dt("deleted"), "ok");
    stopPresenceLoop();
    hideTplEditBanner();
    syncEmptyState();
    await refreshList();
  }

  function contractReturnUrl() {
    const stored = sessionStorage.getItem("workpass-docs-return") || "";
    if (stored) return stored;
    const cid = activeCompanyId();
    const contractId = currentDoc?.contract_id || qs().get("contract_id") || "";
    if (!contractId) return "";
    const u = new URL("/admin-v2/contracts.html", location.origin);
    if (cid) u.searchParams.set("company_id", cid);
    u.searchParams.set("id", contractId);
    return `${u.pathname}${u.search}`;
  }

  function syncContractChrome(doc) {
    const hasContract = !!(doc?.contract_id || qs().get("contract_id"));
    $("applyContractBtn")?.classList.toggle("hidden", !hasContract);
    $("returnContractBtn")?.classList.toggle("hidden", !hasContract);
    $("contractBanner")?.classList.toggle("hidden", !hasContract);
    if (hasContract && $("docMode")) $("docMode").value = "contract";
    const back = $("backLink");
    if (back && hasContract) {
      const ret = contractReturnUrl();
      if (ret) {
        back.href = ret;
        back.textContent = dt("backContracts");
        back.setAttribute("data-di18n", "backContracts");
      }
    }
    if (hasContract) {
      getOwnerUnlock()?.bind();
      $("docsLockNowBtn")?.classList.remove("hidden");
    } else {
      $("docsLockNowBtn")?.classList.add("hidden");
      $("docsLockOverlay")?.classList.add("hidden");
    }
  }

  async function duplicateDoc() {
    const cid = activeCompanyId();
    if (!cid) {
      setStatus($("saveStatus"), dt("needCompany"), "err");
      return;
    }
    if (!confirm(dt("confirmDuplicate"))) return;
    if (dirty) {
      try {
        await saveDoc();
      } catch {
        /* continue */
      }
    }
    const copy = await createBlank({
      title: `${($("docTitle")?.value || dt("untitled")).trim()} (copy)`,
      mode: $("docMode")?.value || "general",
      workerId: selectedWorkerId || currentDoc?.worker_id || "",
      contractId: "",
      contentHtml: getHtml(),
      contentText: getText(),
      contentJson: JSON.stringify(buildEnvelope()),
    });
    if (copy) setStatus($("saveStatus"), dt("duplicated"), "ok");
  }

  async function applyToContract({ andReturn = false } = {}) {
    const contractId = currentDoc?.contract_id || qs().get("contract_id");
    if (!contractId) return;
    if (dirty) await saveDoc();
    await api(`/api/contracts/${encodeURIComponent(contractId)}`, {
      method: "PUT",
      body: JSON.stringify({
        company_id: activeCompanyId(),
        final_text: getText(),
        draft_text: getText(),
      }),
    });
    setStatus($("saveStatus"), dt("appliedContract"), "ok");
    if (andReturn) {
      const ret = contractReturnUrl();
      if (ret) {
        sessionStorage.removeItem("workpass-docs-return");
        location.href = ret;
      }
    }
  }

  function showTplEditBanner(key) {
    const banner = $("tplEditBanner");
    if (!banner) return;
    if (!key || key === "blank") {
      banner.hidden = true;
      banner.classList.remove("is-on");
      return;
    }
    const name = templateMetaList().find((t) => t.id === key)?.title || key;
    if ($("tplEditBannerText")) {
      $("tplEditBannerText").textContent = dt("tplEditHintNamed", { name });
    }
    banner.hidden = false;
    banner.classList.add("is-on");
  }

  function hideTplEditBanner() {
    const banner = $("tplEditBanner");
    if (!banner) return;
    banner.hidden = true;
    banner.classList.remove("is-on");
  }

  async function applyTemplate(forcedKey, opts = {}) {
    const key = forcedKey || $("templateSelect")?.value || "";
    const pack = contentPack();
    if (!key || (key !== "blank" && !pack[key])) return;
    const silent = !!opts.silent;
    if (!silent && !skipTemplateConfirmOnce && getText() && !confirm(dt("confirmTemplate"))) return;
    skipTemplateConfirmOnce = false;
    const titles = Object.fromEntries(templateMetaList().map((t) => [t.id, t.title]));
    const knownTitles = new Set(Object.values(titles).filter(Boolean));
    const prevTitle = ($("docTitle")?.value || "").trim();
    let html = compactHtml(getTemplateHtml(key));
    html = html.replaceAll("{{date.today}}", todayIso());
    const nextTitle = titles[key] || dt("tplBlank");
    // Ensure we leave the empty-start overlay: create a real doc when none is open.
    if (!currentDoc?.id && activeCompanyId() && key !== "blank") {
      try {
        await createBlank({
          title: nextTitle,
          mode: key === "letter" ? "letter" : "general",
          contentHtml: html,
        });
        // Re-apply local HTML so Quill chips/classes survive server round-trip.
        setHtml(html);
        if ($("docTitle")) $("docTitle").value = nextTitle;
      } catch (e) {
        setStatus($("saveStatus"), e.message || dt("saveFail"), "err");
        setHtml(html);
      }
    } else {
      setHtml(html);
    }
    // Company branding on every paper (logo + name); never SUPPIX platform mark.
    if ($("useLetterhead")) $("useLetterhead").checked = true;
    ensureCompanyLetterhead({ force: true, silent: true });
    lastTemplateKey = key;
    markDirty();
    if (!silent) showTplEditBanner(key);
    else hideTplEditBanner();
    syncEditorWritingDirection({ focusStart: true });
    if (quill) {
      try {
        quill.focus();
        quill.setSelection(0, 0, "silent");
      } catch {
        /* ignore */
      }
    }
    const untitledish = new Set(["Unbenannt", "Neues Dokument", dt("untitled"), dt("tplBlank"), "Untitled", "Blank", ""]);
    // Sync title when empty, default, or still named after another built-in template.
    if ($("docTitle") && (untitledish.has(prevTitle) || knownTitles.has(prevTitle) || opts.edit || opts.forceTitle || !prevTitle)) {
      $("docTitle").value = nextTitle;
    }
    if ($("templateSelect")) $("templateSelect").value = key;
    setStatus($("saveStatus"), dt("templateReady", { name: nextTitle || key }), "ok");
    syncEmptyState();
    schedulePaperSync({ force: true, fit: true });
  }

  function setZoom(next) {
    autoFit = false;
    zoom = Math.min(1.5, Math.max(0.6, next));
    applyFitScale();
  }

  function resetAutoFit() {
    autoFit = true;
    zoom = 1;
    applyFitScale();
  }

  async function bootstrapFromQuery() {
    const orphan = scanOfflineDrafts();
    if (orphan) showOfflineBanner(orphan);
    syncEmptyState();

    const contractId = (qs().get("contract_id") || "").trim();
    const docId = (qs().get("id") || "").trim();
    const seedText = sessionStorage.getItem("workpass-docs-seed-text") || "";
    if (seedText) sessionStorage.removeItem("workpass-docs-seed-text");

    if (!activeCompanyId()) {
      setStatus($("listStatus"), dt("needCompany"), "err");
      setStatus($("saveStatus"), dt("needCompanyShort"), "err");
      setHtml(`<p>${escapeHtml(dt("pickCompanyBody"))}</p>`);
      return;
    }

    if (docId) {
      await openDoc(docId);
      return;
    }
    const workerId = (qs().get("worker_id") || "").trim();
    if (workerId) {
      selectedWorkerId = workerId;
      await refreshList();
      const title = qs().get("title") || "Schreiben";
      await createBlank({
        title,
        mode: "workforce",
        workerId,
        contentHtml: getTemplateHtml("letter").replaceAll("{{date.today}}", todayIso()),
      });
      syncWorkerSelect(workerId);
      return;
    }
    if (contractId) {
      const data = await api(`/api/v2/docs/from-contract${companyQuery()}`, {
        method: "POST",
        body: JSON.stringify({
          company_id: activeCompanyId(),
          contractId,
          title: qs().get("title") || "Vertrag",
          text: seedText || "",
        }),
      });
      loadIntoEditor(data.document);
      syncContractChrome(data.document);
      await refreshList(data.document?.id);
      return;
    }
    await refreshList();
    if (seedText) {
      await createBlank({ contentHtml: plainToHtml(seedText), contentText: seedText });
    } else {
      const list = await api(`/api/v2/docs${companyQuery({ limit: 1 })}`);
      if ((list.items || []).length) await openDoc(list.items[0].id);
      else await createBlank();
    }
  }

  function main() {
    if (!window.Quill) {
      setStatus($("saveStatus"), dt("quillFail"), "err");
      return;
    }
    const userRaw = wpGet(USER_KEY);
    if (!userRaw || !wpGet(TOKEN_KEY)) {
      location.href = "/admin-v2/index.html";
      return;
    }

    const cid = activeCompanyId();
    const back = $("backLink");
    if (back) back.href = cid ? `/admin-v2/index.html?company_id=${encodeURIComponent(cid)}` : "/admin-v2/index.html";
    if (window.DocsIcons) window.DocsIcons.mountAll(document);

    const Size = window.Quill.import("attributors/style/size");
    Size.whitelist = ["12px", "14px", "16px", "18px", "24px", "32px"];
    window.Quill.register(Size, true);
    const Font = window.Quill.import("formats/font");
    Font.whitelist = ["sans-serif", "serif", "monospace"];
    window.Quill.register(Font, true);
    try {
      const AlignStyle = window.Quill.import("attributors/style/align");
      window.Quill.register(AlignStyle, true);
      const DirectionStyle = window.Quill.import("attributors/style/direction");
      window.Quill.register(DirectionStyle, true);
    } catch {
      /* Quill build without style attributors — CSS/dir still applied */
    }
    try {
      const ColorStyle = window.Quill.import("attributors/style/color");
      window.Quill.register(ColorStyle, true);
      const BackgroundStyle = window.Quill.import("attributors/style/background");
      window.Quill.register(BackgroundStyle, true);
    } catch {
      /* optional color attributors */
    }

    // Install custom toolbar icons BEFORE constructing Quill (required).
    if (window.DocsIcons?.installQuillIcons) {
      window.DocsIcons.installQuillIcons(window.Quill);
    }

    // Keep HTML tables (Quill strips them by default)
    const BlockEmbed = window.Quill.import("blots/block/embed");
    class WpTableBlot extends BlockEmbed {
      static create(value) {
        const node = super.create();
        node.setAttribute("contenteditable", "false");
        const wrap = document.createElement("div");
        wrap.className = "wp-table-wrap";
        wrap.setAttribute("contenteditable", "true");
        wrap.innerHTML = typeof value === "string" ? value : "";
        wrap.addEventListener("mousedown", (e) => e.stopPropagation());
        node.appendChild(wrap);
        return node;
      }
      static value(node) {
        const wrap = node.querySelector(".wp-table-wrap");
        return wrap ? wrap.innerHTML : "";
      }
    }
    WpTableBlot.blotName = "wpTable";
    WpTableBlot.tagName = "div";
    WpTableBlot.className = "ql-wp-table";
    window.Quill.register(WpTableBlot, true);

    class WpPageEdgeBlot extends BlockEmbed {
      static create() {
        const node = super.create();
        node.setAttribute("contenteditable", "false");
        node.setAttribute("data-wp-page-edge", "1");
        return node;
      }
      static value() {
        return true;
      }
    }
    WpPageEdgeBlot.blotName = "wpPageEdge";
    WpPageEdgeBlot.tagName = "div";
    WpPageEdgeBlot.className = "wp-page-edge";
    window.Quill.register(WpPageEdgeBlot, true);

    const Inline = window.Quill.import("blots/inline");
    class WpCommentBlot extends Inline {
      static create(value) {
        const node = super.create();
        const note = typeof value === "string" ? value : value?.note || "";
        node.setAttribute("data-note", note);
        node.setAttribute("title", note);
        return node;
      }
      static formats(node) {
        return node.getAttribute("data-note") || true;
      }
      format(name, value) {
        if (name === WpCommentBlot.blotName) {
          if (!value) {
            this.unwrap();
            return;
          }
          const note = typeof value === "string" ? value : value?.note || "";
          this.domNode.setAttribute("data-note", note);
          this.domNode.setAttribute("title", note);
          return;
        }
        super.format(name, value);
      }
    }
    WpCommentBlot.blotName = "wpComment";
    WpCommentBlot.tagName = "mark";
    WpCommentBlot.className = "wp-comment";
    window.Quill.register(WpCommentBlot, true);

    quill = new window.Quill("#quillEditor", {
      theme: "snow",
      modules: {
        toolbar: "#quillToolbar",
        history: { delay: 400, maxStack: 200 },
        clipboard: {
          matchers: [
            [
              "table",
              (node) => {
                const Delta = window.Quill.import("delta");
                return new Delta().insert({ wpTable: node.outerHTML });
              },
            ],
          ],
        },
      },
      placeholder: dt("editorPh"),
    });
    quill.on("text-change", (delta, _old, source) => {
      if (source === "silent" || suppressTextSideEffects) return;
      markDirty();
      scheduleAutosave();
      scheduleStats();
      scheduleOutline();
      detectSlashFromTextChange(delta, source);
      // Ultra-fast path: skip page layout work unless sheet count may change.
      const ed = quill.root;
      if (!ed) return;
      const h = ed.scrollHeight | 0;
      const paperH = getPaper().h;
      const chrome = cachedChromeH || getChromeHeight();
      const bodyBudget = Math.max(120, paperH - chrome);
      const nextPages = pagesForContentHeight(h, bodyBudget);
      const crossed = nextPages !== pageCount;
      const bigJump = Math.abs(h - lastTypedContentH) >= bodyBudget * 0.45;
      lastTypedContentH = h;
      if (crossed || bigJump) schedulePaperSync();
    });
    quill.on("selection-change", (range) => {
      if (selectionSyncRaf) return;
      selectionSyncRaf = requestAnimationFrame(() => {
        selectionSyncRaf = 0;
        if (range) {
          highlightActiveTable();
          syncStyleSelectFromSelection();
        }
        scheduleSelBubble();
      });
    });
    syncEditorWritingDirection({ focusStart: false });
    polishToolbarPickers();
    applyPremiumIcons();
    bindEditorPageObservers();
    bindCleanPaste();
    applySpellcheck();
    schedulePaperSync({ force: true, fit: true });

    function applyPremiumIcons() {
      const Icons = window.DocsIcons;
      if (!Icons) return;
      Icons.mountAll(document, true);
      Icons.decorateQuillToolbar($("quillToolbar"));
      // Quill sometimes finishes picker DOM one frame later.
      requestAnimationFrame(() => {
        Icons.decorateQuillToolbar($("quillToolbar"));
        Icons.mountAll(document, true);
      });
    }

    function polishToolbarPickers() {
      const fontMap = {
        "": "Sans",
        "sans-serif": "Sans",
        serif: "Serif",
        monospace: "Mono",
      };
      const sizeMap = {
        "": "16",
        "12px": "12",
        "14px": "14",
        "16px": "16",
        "18px": "18",
        "24px": "24",
        "32px": "32",
      };
      const root = $("quillToolbar");
      if (!root) return;
      root.querySelectorAll(".ql-font .ql-picker-item, .ql-font .ql-picker-label").forEach((el) => {
        const key = el.getAttribute("data-value") || "";
        el.setAttribute("data-label", fontMap[key] || "Sans");
      });
      root.querySelectorAll(".ql-size .ql-picker-item, .ql-size .ql-picker-label").forEach((el) => {
        const key = el.getAttribute("data-value") || "";
        el.setAttribute("data-label", sizeMap[key] || (key ? key.replace("px", "") : "16"));
      });
      root.querySelectorAll(".ql-picker").forEach((picker) => {
        if (picker.dataset.wpPickerBound) return;
        picker.dataset.wpPickerBound = "1";
        picker.addEventListener("mousedown", () => {
          root.querySelectorAll(".ql-picker").forEach((p) => p.classList.remove("wp-picker-front"));
          picker.classList.add("wp-picker-front");
          polishToolbarPickers();
        });
      });
      root.querySelectorAll(".ql-picker-label").forEach((label) => {
        if (label.dataset.wpLabelObs) return;
        label.dataset.wpLabelObs = "1";
        const mo = new MutationObserver(() => polishToolbarPickers());
        mo.observe(label, { attributes: true, attributeFilter: ["data-value", "class"] });
      });
    }

    function closeMoreMenu() {
      $("moreMenu")?.classList.remove("open");
      $("moreBtn")?.setAttribute("aria-expanded", "false");
    }
    $("moreBtn")?.addEventListener("click", (e) => {
      e.stopPropagation();
      const menu = $("moreMenu");
      const open = !menu?.classList.contains("open");
      menu?.classList.toggle("open", open);
      $("moreBtn")?.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest?.(".more-wrap")) closeMoreMenu();
    });
    $("moreMenu")?.addEventListener("click", () => {
      setTimeout(closeMoreMenu, 0);
    });

    $("newDocBtn")?.addEventListener("click", () => createBlank().catch((e) => setStatus($("saveStatus"), e.message, "err")));
    document.querySelectorAll("[data-side-tab]").forEach((btn) => {
      btn.addEventListener("click", () => setSideTab(btn.getAttribute("data-side-tab") || "templates"));
    });
    setSideTab("templates");
    $("saveBtn")?.addEventListener("click", () => saveDoc().catch((e) => setStatus($("saveStatus"), e.message, "err")));
    $("deleteBtn")?.addEventListener("click", () => deleteDoc().catch((e) => setStatus($("saveStatus"), e.message, "err")));
    $("duplicateBtn")?.addEventListener("click", () => duplicateDoc().catch((e) => setStatus($("saveStatus"), e.message, "err")));
    $("applyContractBtn")?.addEventListener("click", () =>
      applyToContract().catch((e) => setStatus($("saveStatus"), e.message, "err")),
    );
    $("applyReturnContractBtn")?.addEventListener("click", () =>
      applyToContract({ andReturn: true }).catch((e) => setStatus($("saveStatus"), e.message, "err")),
    );
    $("returnContractBtn")?.addEventListener("click", () => {
      const ret = contractReturnUrl();
      if (ret) {
        sessionStorage.removeItem("workpass-docs-return");
        location.href = ret;
      }
    });
    $("printBtn")?.addEventListener("click", () => exportDoc("pdf").catch(() => {}));
    $("printBrowserBtn")?.addEventListener("click", () => openPrintPreviewPdf().catch(() => {}));
    $("fullscreenBtn")?.addEventListener("click", () => toggleFocusMode());
    $("exitFocusBtn")?.addEventListener("click", () => toggleFocusMode(false));
    $("applyTemplateBtn")?.addEventListener("click", () => {
      applyTemplate().catch((e) => setStatus($("saveStatus"), e.message || dt("error"), "err"));
    });
    $("zoomInBtn")?.addEventListener("click", () => setZoom(zoom + 0.08));
    $("zoomOutBtn")?.addEventListener("click", () => setZoom(zoom - 0.08));
    $("fitResetBtn")?.addEventListener("click", resetAutoFit);
    $("fillMergeBtn")?.addEventListener("click", () => fillMergeFields().catch(() => {}));
    $("mergeModalClose")?.addEventListener("click", () => closeMergeFillModal());
    $("mergeBackdrop")?.addEventListener("click", () => closeMergeFillModal());
    $("mergePreviewBtn")?.addEventListener("click", () => refreshMergePreview().catch(() => {}));
    $("mergeApplyBtn")?.addEventListener("click", () => applyMergeFill().catch(() => {}));
    $("mergeWorkerSelect")?.addEventListener("change", () => {
      selectedWorkerId = $("mergeWorkerSelect")?.value || "";
      if ($("workerSelect")) $("workerSelect").value = selectedWorkerId;
      refreshMergePreview().catch(() => {});
    });
    $("signModalClose")?.addEventListener("click", () => closeSignModal());
    $("signBackdrop")?.addEventListener("click", () => closeSignModal());
    $("signClearBtn")?.addEventListener("click", () => clearSignCanvas());
    $("signLineOnlyBtn")?.addEventListener("click", () => insertSignatureBlockLineOnly());
    $("signInsertBtn")?.addEventListener("click", () => {
      insertSignatureFromModal().catch(() => {});
    });
    $("collabReloadBtn")?.addEventListener("click", () => {
      dirty = false;
      conflictIgnoredHash = "";
      pendingRemoteHash = "";
      hideCollabConflict();
      reloadFromServerQuiet().catch(() => {});
    });
    $("collabKeepBtn")?.addEventListener("click", () => {
      if (pendingRemoteHash) conflictIgnoredHash = pendingRemoteHash;
      hideCollabConflict();
    });
    $("liveFollowBtn")?.addEventListener("click", () => {
      liveFollow = !liveFollow;
      if (liveFollow && latestPeerLive) applyPeerLive(latestPeerLive);
      renderLiveTyping(latestPeerLive ? [latestPeerLive] : []);
    });
    $("signQesBtn")?.addEventListener("click", () => {
      startQesSignature().catch(() => {});
    });
    $("diffOnlyChanges")?.addEventListener("change", () => renderDiffBody());
    $("diffUnifiedView")?.addEventListener("change", () => renderDiffBody());
    $("checkPlaceholdersBtn")?.addEventListener("click", () => {
      renderPlaceholderCheck();
      const items = collectOpenPlaceholders();
      setStatus(
        $("saveStatus"),
        items.length ? dt("placeholdersOpen", { n: items.length }) : dt("placeholdersClear"),
        items.length ? "err" : "ok",
      );
    });
    $("placeholderCheckList")?.addEventListener("click", (e) => {
      const btn = e.target?.closest?.("[data-ph]");
      if (!btn) return;
      const items = $("placeholderCheckList")?._phItems || collectOpenPlaceholders();
      const item = items[Number(btn.getAttribute("data-ph"))];
      if (item?.token) jumpToPlaceholder(item.token);
    });
    $("applyLetterheadBtn")?.addEventListener("click", () => applyCompanyLetterhead());
    $("clearLetterheadBtn")?.addEventListener("click", () => clearCompanyLetterhead());
    $("useLetterhead")?.addEventListener("change", () => syncLetterheadFromToggle());
    document.querySelectorAll("[data-snippet]").forEach((btn) => {
      btn.addEventListener("click", () => insertSnippet(btn.getAttribute("data-snippet") || ""));
    });
    $("sharePdfBtn")?.addEventListener("click", () => exportDoc("pdf").catch(() => {}));
    $("sharePrintBtn")?.addEventListener("click", () => openPrintPreviewPdf().catch(() => {}));
    $("shareEmailBtn")?.addEventListener("click", () => shareByEmail().catch(() => {}));

    $("emptyTplBtn")?.addEventListener("click", () => {
      setSideTab("templates");
      document.body.classList.add("side-open");
    });
    $("emptyBlankBtn")?.addEventListener("click", () => createBlank().catch((e) => setStatus($("saveStatus"), e.message, "err")));
    $("emptyImportBtn")?.addEventListener("click", () => pickImportDocx());
    $("printPreviewPdfBtn")?.addEventListener("click", () => openPrintPreviewPdf().catch(() => {}));
    $("signSaveMineBtn")?.addEventListener("click", () => saveMySignatureFromModal());
    $("signLoadMineBtn")?.addEventListener("click", () => loadMySignatureIntoModal());
    $("emailWorkerSelect")?.addEventListener("change", () => {
      const opt = $("emailWorkerSelect")?.selectedOptions?.[0];
      const mail = opt?.dataset?.email || "";
      const m = /([\w.+-]+@[\w.-]+\.[A-Za-z]{2,})/.exec(opt?.textContent || "");
      if ($("emailToInput")) $("emailToInput").value = mail || (m ? m[1] : $("emailToInput").value);
    });
    quill?.root?.addEventListener("click", (e) => {
      const chip = e.target?.closest?.(".wp-ph-chip");
      if (!chip) return;
      const key = chip.getAttribute("data-wp-ph");
      const token = key ? `{{${key}}}` : chip.textContent;
      if (token) jumpToPlaceholder(token);
      openMergeFillModal();
    });
    window.setInterval(() => tickSaveStatus(), 15000);
    window.addEventListener("online", () => {
      if (dirty) scheduleAutosave();
      const draft = scanOfflineDrafts();
      if (draft && !pendingOfflineDraft) showOfflineBanner(draft);
    });
    window.addEventListener("beforeunload", () => {
      if (dirty) persistOfflineDraft();
    });

    $("emailModalClose")?.addEventListener("click", () => closeEmailModal());
    $("emailBackdrop")?.addEventListener("click", () => closeEmailModal());
    $("emailSendBtn")?.addEventListener("click", () => sendDocEmail().catch(() => {}));
    $("emailFallbackBtn")?.addEventListener("click", () => shareByEmailLocal().catch(() => {}));
    $("shareLinkBtn")?.addEventListener("click", () => createShareLink().catch(() => {}));
    $("shareLinkRailBtn")?.addEventListener("click", () => createShareLink().catch(() => {}));
    $("shareModalClose")?.addEventListener("click", () => closeShareModal());
    $("shareBackdrop")?.addEventListener("click", () => closeShareModal());
    $("shareCreateBtn")?.addEventListener("click", () => createShareLinkDirect().catch(() => {}));
    $("shareRevokeAllBtn")?.addEventListener("click", () => revokeAllShares().catch(() => {}));
    $("copyEditorLinkBtn")?.addEventListener("click", () => copyEditorLink().catch(() => {}));
    $("importDocxBtn")?.addEventListener("click", () => pickImportDocx());
    $("insertTocBtn")?.addEventListener("click", () => insertTableOfContents());
    $("importDocxInput")?.addEventListener("change", () => {
      const file = $("importDocxInput")?.files?.[0];
      if (file) importDocxFile(file).catch(() => {});
    });
    $("exportPdfBtn")?.addEventListener("click", () => exportDoc("pdf").catch(() => {}));
    $("exportHtmlBtn")?.addEventListener("click", () => exportDoc("html").catch(() => {}));
    $("exportDocBtn")?.addEventListener("click", () => exportDoc("doc").catch(() => {}));
    $("wordProBtn")?.addEventListener("click", () => openWordPro().catch(() => {}));
    $("ooCloseBtn")?.addEventListener("click", () => closeWordPro().catch(() => {}));
    $("publishBtn")?.addEventListener("click", () => publishToWorker().catch(() => {}));
    $("docStatus")?.addEventListener("change", () => {
      const status = $("docStatus")?.value || "draft";
      setDocStatus(status).catch(() => {});
    });
    $("workflowPanel")?.addEventListener("click", (e) => {
      const btn = e.target?.closest?.("[data-status-set]");
      if (!btn) return;
      const status = btn.getAttribute("data-status-set");
      if (status) setDocStatus(status).catch(() => {});
    });
    $("workflowNextBtn")?.addEventListener("click", () => openPreflight("review"));
    $("workflowApproveBtn")?.addEventListener("click", () => openPreflight("approve"));
    $("workflowUnlockBtn")?.addEventListener("click", () => setDocStatus("draft").catch(() => {}));
    $("saveAsTemplateBtn")?.addEventListener("click", () => saveCurrentAsTemplate());
    $("watermarkSelect")?.addEventListener("change", () => {
      layout.watermark = String($("watermarkSelect")?.value || "");
      refreshWatermarkFrames();
      markDirty();
    });
    $("preflightClose")?.addEventListener("click", () => closePreflight());
    $("preflightCancel")?.addEventListener("click", () => closePreflight());
    $("preflightBackdrop")?.addEventListener("click", () => closePreflight());
    $("preflightContinue")?.addEventListener("click", () => {
      const act = preflightAction;
      closePreflight();
      runPreflightAction(act);
    });
    $("insertTableBtn")?.addEventListener("click", (e) => {
      e.stopPropagation();
      const panel = $("tablePicker");
      if (panel && !panel.hidden) closeTablePicker();
      else openTablePicker();
    });
    document.addEventListener("click", (e) => {
      const wrap = $("tablePickerWrap");
      if (wrap && !wrap.contains(e.target)) closeTablePicker();
    });
    $("insertTablePreset33")?.addEventListener("click", () => insertTable(3, 3));
    $("undoBtn")?.addEventListener("click", () => quill?.history?.undo());
    $("redoBtn")?.addEventListener("click", () => quill?.history?.redo());
    $("findOpenBtn")?.addEventListener("click", () => openFindBar());
    $("replaceOpenBtn")?.addEventListener("click", () => openFindBar({ replace: true }));
    $("cmdPaletteBtn")?.addEventListener("click", () => openCmdPalette());
    $("outlineToggleBtn")?.addEventListener("click", () => {
      const panel = $("docOutline");
      if (!panel) return;
      const open = panel.hidden;
      panel.hidden = !open;
      $("outlineToggleBtn")?.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) renderOutline();
      scheduleFit();
    });
    $("commentsToggleBtn")?.addEventListener("click", () => {
      const panel = $("docComments");
      if (!panel) return;
      const open = panel.hidden;
      panel.hidden = !open;
      $("commentsToggleBtn")?.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) renderCommentsPanel();
      scheduleFit();
    });
    $("docOutlineList")?.addEventListener("click", (e) => {
      const btn = e.target?.closest?.("[data-outline]");
      if (!btn) return;
      jumpToOutline(Number(btn.getAttribute("data-outline")));
    });
    $("docCommentsList")?.addEventListener("click", (e) => {
      const jump = e.target?.closest?.("[data-cmt]");
      if (jump) {
        jumpToComment(Number(jump.getAttribute("data-cmt")));
        return;
      }
      const assign = e.target?.closest?.("[data-cmt-assign]");
      if (assign) {
        assignCommentAt(Number(assign.getAttribute("data-cmt-assign")));
        return;
      }
      const edit = e.target?.closest?.("[data-cmt-edit]");
      if (edit) {
        editCommentAt(Number(edit.getAttribute("data-cmt-edit")));
        return;
      }
      const resolve = e.target?.closest?.("[data-cmt-resolve]");
      if (resolve) resolveCommentAt(Number(resolve.getAttribute("data-cmt-resolve")));
    });
    document.querySelectorAll("[data-cmt-filter]").forEach((btn) => {
      btn.addEventListener("click", () => {
        commentsFilter = btn.getAttribute("data-cmt-filter") || "open";
        renderCommentsPanel();
      });
    });
    $("printPreviewBtn")?.addEventListener("click", () => openPrintPreviewPdf().catch(() => {}));
    $("printPreviewClose")?.addEventListener("click", () => closePrintPreview());
    $("printPreviewDismiss")?.addEventListener("click", () => closePrintPreview());
    $("printPreviewBackdrop")?.addEventListener("click", () => closePrintPreview());
    $("printPreviewCheck")?.addEventListener("click", () => openPrintPreview({ showMarks: true }));
    $("printPreviewPrint")?.addEventListener("click", () => runCleanBrowserPrint());
    $("tplEditSaveBtn")?.addEventListener("click", () => {
      hideTplEditBanner();
      saveCurrentAsTemplate();
    });
    $("tplEditDismissBtn")?.addEventListener("click", () => hideTplEditBanner());
    window.addEventListener("afterprint", () => {
      document.body.classList.remove("docs-printing-locked", "docs-print-clean");
      hideAiOperatorForPrint(false);
    });
    $("slashMenu")?.addEventListener("mousedown", (e) => e.preventDefault());
    $("slashMenu")?.addEventListener("click", (e) => {
      const row = e.target?.closest?.("[data-idx]");
      if (!row) return;
      runSlashItem(Number(row.getAttribute("data-idx")));
    });
    $("insertImageInput")?.addEventListener("change", () => {
      const file = $("insertImageInput")?.files?.[0];
      if (file) insertImageFromFile(file);
      if ($("insertImageInput")) $("insertImageInput").value = "";
    });
    quill.root.addEventListener("keydown", (e) => {
      const mergeEl = $("mergeMenu");
      if (mergeEl && !mergeEl.hidden) {
        if (e.key === "ArrowDown") {
          e.preventDefault();
          mergeIndex = Math.min(mergeItems.length - 1, mergeIndex + 1);
          renderMergeMenu(
            mergeStart >= 0
              ? String(quill.getText(mergeStart + 2, Math.max(0, (quill.getSelection()?.index || 0) - mergeStart - 2)))
              : "",
          );
          return;
        }
        if (e.key === "ArrowUp") {
          e.preventDefault();
          mergeIndex = Math.max(0, mergeIndex - 1);
          renderMergeMenu(
            mergeStart >= 0
              ? String(quill.getText(mergeStart + 2, Math.max(0, (quill.getSelection()?.index || 0) - mergeStart - 2)))
              : "",
          );
          return;
        }
        if (e.key === "Enter" || e.key === "Tab") {
          if (mergeItems.length) {
            e.preventDefault();
            runMergeItem(mergeIndex);
          }
          return;
        }
        if (e.key === "Escape") {
          e.preventDefault();
          hideMergeMenu();
          return;
        }
      }
      const menu = $("slashMenu");
      if (!menu || menu.hidden) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        slashIndex = Math.min(slashItems.length - 1, slashIndex + 1);
        renderSlashMenu(
          slashStart >= 0
            ? String(quill.getText(slashStart + 1, Math.max(0, (quill.getSelection()?.index || 0) - slashStart - 1)))
            : "",
        );
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        slashIndex = Math.max(0, slashIndex - 1);
        renderSlashMenu(
          slashStart >= 0
            ? String(quill.getText(slashStart + 1, Math.max(0, (quill.getSelection()?.index || 0) - slashStart - 1)))
            : "",
        );
      } else if (e.key === "Enter" || e.key === "Tab") {
        if (slashItems.length) {
          e.preventDefault();
          runSlashItem(slashIndex);
        }
      } else if (e.key === "Escape") {
        e.preventDefault();
        hideSlashMenu();
      }
    });
    $("mergeMenu")?.addEventListener("mousedown", (e) => e.preventDefault());
    $("mergeMenu")?.addEventListener("click", (e) => {
      const row = e.target?.closest?.("[data-merge-idx]");
      if (!row) return;
      runMergeItem(Number(row.getAttribute("data-merge-idx")));
    });
    $("shortcutsBtn")?.addEventListener("click", () => openShortcutsModal());
    $("shortcutsClose")?.addEventListener("click", () => closeShortcutsModal());
    $("shortcutsBackdrop")?.addEventListener("click", () => closeShortcutsModal());
    $("offlineRestoreBtn")?.addEventListener("click", () => applyOfflineDraft(pendingOfflineDraft));
    $("offlineDiscardBtn")?.addEventListener("click", () => {
      clearOfflineDraft(pendingOfflineDraft?.docId || currentDoc?.id || "new");
      hideOfflineBanner();
    });
    // Drag & drop images onto the paper
    quill.root.addEventListener("dragover", (e) => {
      if ([...e.dataTransfer?.types || []].includes("Files")) e.preventDefault();
    });
    quill.root.addEventListener("drop", (e) => {
      const file = [...(e.dataTransfer?.files || [])].find((f) => String(f.type || "").startsWith("image/"));
      if (!file) return;
      e.preventDefault();
      insertImageFromFile(file);
    });
    $("cmdPaletteBackdrop")?.addEventListener("click", () => closeCmdPalette());
    $("cmdPaletteInput")?.addEventListener("input", () => {
      cmdPaletteIndex = 0;
      renderCmdPaletteList($("cmdPaletteInput")?.value || "");
    });
    $("cmdPaletteInput")?.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        cmdPaletteIndex = Math.min(cmdPaletteItems.length - 1, cmdPaletteIndex + 1);
        renderCmdPaletteList($("cmdPaletteInput")?.value || "");
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        cmdPaletteIndex = Math.max(0, cmdPaletteIndex - 1);
        renderCmdPaletteList($("cmdPaletteInput")?.value || "");
      } else if (e.key === "Enter") {
        e.preventDefault();
        runCmdPaletteItem(cmdPaletteIndex);
      } else if (e.key === "Escape") {
        e.preventDefault();
        closeCmdPalette();
      }
    });
    $("cmdPaletteList")?.addEventListener("click", (e) => {
      const row = e.target?.closest?.("[data-idx]");
      if (!row) return;
      runCmdPaletteItem(Number(row.getAttribute("data-idx")));
    });
    $("selBubble")?.addEventListener("mousedown", (e) => {
      // Keep Quill selection while clicking bubble controls.
      e.preventDefault();
    });
    $("selBubble")?.addEventListener("click", (e) => {
      const btn = e.target?.closest?.(".sel-bubble-btn");
      if (!btn) return;
      const action = btn.getAttribute("data-action");
      if (action === "comment") {
        addCommentOnSelection();
        return;
      }
      const fmt = btn.getAttribute("data-fmt");
      const align = btn.getAttribute("data-align");
      if (fmt) applyBubbleFormat(fmt);
      if (align) applyBubbleAlign(align);
    });
    $("imgSizeBar")?.addEventListener("mousedown", (e) => e.preventDefault());
    $("imgSizeBar")?.addEventListener("click", (e) => {
      const btn = e.target?.closest?.("[data-img-size]");
      if (!btn) return;
      setImageSize(btn.getAttribute("data-img-size"));
    });
    quill.root.addEventListener("click", (e) => {
      const img = e.target?.closest?.("img");
      if (img && quill.root.contains(img)) {
        hideSelBubble();
        showImgSizeBar(img);
        return;
      }
      hideImgSizeBar();
    });
    $("diffModalBackdrop")?.addEventListener("click", () => closeDiffModal());
    $("diffModalClose")?.addEventListener("click", () => closeDiffModal());
    $("diffCloseBtn")?.addEventListener("click", () => closeDiffModal());
    $("diffRestoreBtn")?.addEventListener("click", () => {
      if (!diffVersionId) return;
      restoreVersion(diffVersionId)
        .then(() => closeDiffModal())
        .catch((err) => setStatus($("saveStatus"), err.message, "err"));
    });
    $("diffCopyBtn")?.addEventListener("click", () => saveDiffAsCopy().catch((err) => setStatus($("saveStatus"), err.message, "err")));
    document.addEventListener("click", (e) => {
      if ($("imgSizeBar") && !$("imgSizeBar").hidden) {
        if (!e.target?.closest?.("#imgSizeBar") && !e.target?.closest?.("img")) hideImgSizeBar();
      }
    });
    $("findCloseBtn")?.addEventListener("click", () => closeFindBar());
    $("findNextBtn")?.addEventListener("click", () => focusFindMatch(findIndex + 1));
    $("findPrevBtn")?.addEventListener("click", () => focusFindMatch(findIndex - 1));
    $("replaceOneBtn")?.addEventListener("click", () => replaceOne());
    $("replaceAllBtn")?.addEventListener("click", () => replaceAll());
    let findDebounce = 0;
    $("findInput")?.addEventListener("input", () => {
      window.clearTimeout(findDebounce);
      findDebounce = window.setTimeout(() => runFind($("findInput")?.value || ""), 140);
    });
    $("findInput")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        if (findReplaceMode && (e.ctrlKey || e.metaKey)) replaceOne();
        else if (e.shiftKey) focusFindMatch(findIndex - 1);
        else focusFindMatch(findIndex + 1);
      } else if (e.key === "Escape") {
        e.preventDefault();
        closeFindBar();
      }
    });
    $("replaceInput")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        if (e.ctrlKey || e.metaKey || e.altKey) replaceAll();
        else replaceOne();
      } else if (e.key === "Escape") {
        e.preventDefault();
        closeFindBar();
      }
    });
    $("zoom100Btn")?.addEventListener("click", () => {
      autoFit = false;
      fitScale = 1;
      zoom = 1;
      applyFitScale();
    });
    $("docsStage")?.addEventListener(
      "scroll",
      () => {
        updateCurrentPageFromScroll();
        scheduleSelBubble();
      },
      { passive: true },
    );
    $("insertPageBreakBtn")?.addEventListener("click", () => {
      const label = dt("pageBreak");
      insertHtmlAtCursor(
        `<p class="wp-page-break" data-label="${escapeHtml(label)}"><br></p><p><br></p>`,
      );
    });
    $("insertHrBtn")?.addEventListener("click", () => insertHtmlAtCursor("<hr /><p><br></p>"));
    $("insertSignBtn")?.addEventListener("click", () => insertSignatureBlock());
    $("insertImageBtn")?.addEventListener("click", () => openImagePicker());
    $("spellLangSelect")?.addEventListener("change", () => applySpellcheck());
    $("styleSelect")?.addEventListener("change", () => applyParagraphStyle($("styleSelect").value));
    $("lineSpacingSelect")?.addEventListener("change", () => {
      layout.lineSpacing = Number($("lineSpacingSelect")?.value || 1.15);
      applyLayoutToDom();
      markDirty();
    });
    $("tableAddRowBtn")?.addEventListener("click", tableAddRow);
    $("tableDelRowBtn")?.addEventListener("click", tableDelRow);
    $("tableAddColBtn")?.addEventListener("click", tableAddCol);
    $("tableDelColBtn")?.addEventListener("click", tableDelCol);
    $("tableHeaderRowBtn")?.addEventListener("click", tableToggleHeaderRow);
    $("tableBorderSelect")?.addEventListener("change", () => tableSetBorders($("tableBorderSelect").value));
    $("headerPreset")?.addEventListener("change", () => {
      const v = $("headerPreset")?.value;
      if (v) applyHeaderPreset(v);
      if ($("headerPreset")) $("headerPreset").value = "";
    });
    $("footerPreset")?.addEventListener("change", () => {
      const v = $("footerPreset")?.value;
      if (v) applyFooterPreset(v);
      if ($("footerPreset")) $("footerPreset").value = "";
    });
    ["marginTop", "marginBottom", "marginLeft", "marginRight"].forEach((id) => {
      $(id)?.addEventListener("change", readLayoutFromInputs);
    });
    $("pageSizeSelect")?.addEventListener("change", () => {
      const next = String($("pageSizeSelect").value || "a4").toLowerCase();
      layout.pageSize = PAPER_SIZES[next] ? next : "a4";
      applyLayoutToDom();
      markDirty();
    });
    $("marginResetBtn")?.addEventListener("click", () => {
      layout = {
        ...layout,
        pageSize: layout.pageSize || "a4",
        marginTopMm: 22,
        marginRightMm: 20,
        marginBottomMm: 22,
        marginLeftMm: 25,
        lineSpacing: 1.15,
      };
      applyLayoutToDom();
      markDirty();
    });
    $("toggleHeaderBtn")?.addEventListener("click", () => {
      layout.showHeader = !layout.showHeader;
      applyLayoutToDom();
      markDirty();
    });
    $("toggleFooterBtn")?.addEventListener("click", () => {
      layout.showFooter = !layout.showFooter;
      applyLayoutToDom();
      markDirty();
    });
    $("toggleSideBtn")?.addEventListener("click", () => {
      document.body.classList.toggle("side-open");
      document.body.classList.remove("rail-open");
      $("railBackdrop")?.setAttribute("hidden", "");
      scheduleFit();
    });
    function setRailOpen(open) {
      document.body.classList.toggle("rail-open", open);
      document.body.classList.remove("side-open");
      const bd = $("railBackdrop");
      if (bd) {
        if (open) bd.removeAttribute("hidden");
        else bd.setAttribute("hidden", "");
      }
      scheduleFit();
    }
    $("toggleRailBtn")?.addEventListener("click", () => {
      setRailOpen(!document.body.classList.contains("rail-open"));
    });
    $("railCloseBtn")?.addEventListener("click", () => setRailOpen(false));
    $("railBackdrop")?.addEventListener("click", () => setRailOpen(false));
    $("docsStage")?.addEventListener("click", () => {
      document.body.classList.remove("side-open");
      if (window.matchMedia("(max-width: 1200px)").matches) setRailOpen(false);
    });
    $("docHeader")?.addEventListener("input", () => {
      markDirty();
      chromeCacheTs = 0;
      schedulePaperSync({ force: true });
    });
    $("docFooter")?.addEventListener("input", () => {
      markDirty();
      chromeCacheTs = 0;
      schedulePaperSync({ force: true });
    });
    $("docHeader")?.addEventListener("focus", () => {
      layout.showHeader = true;
      applyLayoutToDom();
    });
    $("docFooter")?.addEventListener("focus", () => {
      layout.showFooter = true;
      applyLayoutToDom();
    });
    quill.root.addEventListener("mouseup", highlightActiveTable);
    quill.root.addEventListener("keyup", highlightActiveTable);
    $("workerSelect")?.addEventListener("change", () => {
      selectedWorkerId = ($("workerSelect")?.value || "").trim();
      markDirty();
      loadMergeContext().catch(() => {});
    });
    $("docsSearch")?.addEventListener("input", () => {
      listFilter = ($("docsSearch")?.value || "").trim();
      renderDocsList(currentDoc?.id);
    });
    document.addEventListener("keydown", (e) => {
      const key = String(e.key || "").toLowerCase();
      if (key === "escape") {
        if ($("signModal") && !$("signModal").hidden) {
          e.preventDefault();
          closeSignModal();
          return;
        }
        if ($("mergeModal") && !$("mergeModal").hidden) {
          e.preventDefault();
          closeMergeFillModal();
          return;
        }
        if ($("emailModal") && !$("emailModal").hidden) {
          e.preventDefault();
          closeEmailModal();
          return;
        }
        if ($("diffModal") && !$("diffModal").hidden) {
          e.preventDefault();
          closeDiffModal();
          return;
        }
        if ($("preflightModal") && !$("preflightModal").hidden) {
          e.preventDefault();
          closePreflight();
          return;
        }
        if ($("shortcutsModal") && !$("shortcutsModal").hidden) {
          e.preventDefault();
          closeShortcutsModal();
          return;
        }
        if ($("mergeMenu") && !$("mergeMenu").hidden) {
          e.preventDefault();
          hideMergeMenu();
          return;
        }
        if ($("slashMenu") && !$("slashMenu").hidden) {
          e.preventDefault();
          hideSlashMenu();
          return;
        }
        if ($("cmdPalette") && !$("cmdPalette").hidden) {
          e.preventDefault();
          closeCmdPalette();
          return;
        }
        if ($("printPreviewModal") && !$("printPreviewModal").hidden) {
          e.preventDefault();
          closePrintPreview();
          return;
        }
        if ($("docsFind") && !$("docsFind").hidden) {
          e.preventDefault();
          closeFindBar();
          return;
        }
        if (document.body.classList.contains("docs-fullscreen")) {
          e.preventDefault();
          toggleFocusMode(false);
          return;
        }
      }
      if (!(e.ctrlKey || e.metaKey)) return;
      if (key === "s") {
        e.preventDefault();
        saveDoc().catch((err) => setStatus($("saveStatus"), err.message, "err"));
      } else if (key === "p") {
        e.preventDefault();
        openPrintPreviewPdf().catch(() => {});
      } else if (key === "d") {
        e.preventDefault();
        duplicateDoc().catch((err) => setStatus($("saveStatus"), err.message, "err"));
      } else if (key === "f") {
        e.preventDefault();
        openFindBar();
      } else if (key === "h") {
        e.preventDefault();
        openFindBar({ replace: true });
      } else if (key === "k") {
        e.preventDefault();
        openCmdPalette();
      } else if (key === "/" || (key === "7" && e.shiftKey)) {
        // Ctrl+/ (US) or Ctrl+Shift+7 (DE layouts often)
        e.preventDefault();
        openShortcutsModal();
      }
    });
    document.querySelectorAll("[data-ai]").forEach((btn) => {
      btn.addEventListener("click", () =>
        runAiSuggest(btn.getAttribute("data-ai") || "improve").catch(() => {}),
      );
    });
    $("docTitle")?.addEventListener("input", markDirty);
    $("docMode")?.addEventListener("change", markDirty);
    document.querySelectorAll("[data-merge]").forEach((btn) => {
      btn.addEventListener("click", () => insertMergeToken(btn.getAttribute("data-merge") || ""));
    });

    window.addEventListener("beforeprint", () => {
      document.body.classList.add("docs-printing-locked");
      hideAiOperatorForPrint(true);
    });
    window.addEventListener("afterprint", () => {
      document.body.classList.remove("docs-printing-locked");
      hideAiOperatorForPrint(false);
    });
    window.addEventListener("beforeunload", (e) => {
      if (dirty) persistOfflineDraft();
      if (!dirty) return;
      e.preventDefault();
      e.returnValue = "";
    });

    window.addEventListener("resize", scheduleFit);
    if (window.ResizeObserver && $("docsStage")) {
      new ResizeObserver(scheduleFit).observe($("docsStage"));
    }

    window.refreshDocsPageDynamicUi = (opts = {}) => {
      renderTemplateGallery();
      renderStatusFilters();
      renderDocsList(currentDoc?.id);
      renderBrandPreview();
      updatePageLabel();
      updateWordCountLabel();
      updateReadTimeLabel();
      scheduleOutline();
      highlightActiveTable();
      syncStyleSelectFromSelection();
      if (window.DocsIcons) {
        window.DocsIcons.mountAll(document, true);
        window.DocsIcons.decorateQuillToolbar($("quillToolbar"));
      }
      syncEditorWritingDirection({ focusStart: false });
      applySpellcheck();
      if (quill?.root) {
        quill.root.dataset.placeholder = dt("editorPh");
      }
      const noneOpt = $("workerSelect")?.querySelector('option[value=""]');
      if (noneOpt) noneOpt.textContent = dt("workerNone");
      const applyBtn = $("applyTemplateBtn");
      if (applyBtn) applyBtn.textContent = dt("applyTemplateBtn");
      $("zoomOutBtn")?.setAttribute("aria-label", dt("zoomOut"));
      $("zoomInBtn")?.setAttribute("aria-label", dt("zoomIn"));
      // Re-apply active template body so paper text follows language switch literally.
      if (opts.reason === "lang" && lastTemplateKey) {
        skipTemplateConfirmOnce = true;
        applyTemplate(lastTemplateKey, { silent: true }).catch(() => {});
      }
    };

    const unlock = getOwnerUnlock();
    // Owner-OTP-UI nur bei Vertrags-Kontext binden — normaler Editor ist frei.
    if (!isContractContext()) {
      $("docsLockOverlay")?.classList.add("hidden");
      $("docsLockNowBtn")?.classList.add("hidden");
    } else {
      unlock?.bind();
    }
    $("docsLockNowBtn")?.addEventListener("click", async () => {
      if (!isContractContext()) return;
      try {
        await api("/api/contracts/lock", {
          method: "POST",
          body: JSON.stringify({ company_id: activeCompanyId() }),
        });
        unlock?.markUnlocked(false);
        $("docsLockNowBtn")?.classList.add("hidden");
        unlock?.show({ setup: false, enforced: true });
        setStatus($("saveStatus"), dt("lockNowToast") || "Vertragsbereich gesperrt.", "ok");
      } catch (e) {
        setStatus($("saveStatus"), e.body?.message || e.message || dt("error"), "err");
      }
    });

    if (currentUserRole() === "turnstile" && isContractContext()) {
      setStatus($("saveStatus"), dt("lockTurnstileBlocked") || "Arbeitsverträge sind für die Pförtner-Rolle gesperrt.", "err");
      unlock?.bind();
      unlock?.show({ setup: false });
      unlock?.setMsg(dt("lockRoleBlocked") || "Nur mit Freigabe des Firmeninhabers — Inhaber wurde informiert.", "warn");
      $("docsLockSendBtn")?.classList.add("hidden");
      $("docsLockVerifyBtn")?.classList.add("hidden");
      $("docsLockSkipBtn")?.classList.remove("hidden");
      if ($("docsLockSkipBtn")) $("docsLockSkipBtn").textContent = dt("lockBackOps") || "Zurück zum Betrieb";
      $("docsLockSkipBtn")?.addEventListener(
        "click",
        () => {
          location.href = "/admin-v2/docs.html";
        },
        { once: true },
      );
      return;
    }

    applyLayoutToDom();
    resetAutoFit();
    scheduleStats();
    scheduleOutline();
    window.initDocsPageLangSync?.();
    renderTemplateGallery();
    selectedWorkerId = (qs().get("worker_id") || "").trim();
    loadMergeContext()
      .then(() => bootstrapFromQuery())
      .then(async () => {
        try {
          const cid = activeCompanyId();
          if (cid && isContractContext()) {
            const st = await api(`/api/contracts/lock-status?company_id=${encodeURIComponent(cid)}`);
            if (st.lockRequired && st.unlocked) {
              unlock?.markUnlocked(true);
              $("docsLockNowBtn")?.classList.remove("hidden");
            } else if (st.lockRequired && !st.unlocked) {
              unlock?.bind();
              unlock?.show({ setup: !!st.ownerSetupRequired, enforced: true });
            }
          } else {
            $("docsLockNowBtn")?.classList.add("hidden");
            $("docsLockOverlay")?.classList.add("hidden");
          }
        } catch {
          /* ignore lock-status probe */
        }
        scheduleFit();
      })
      .catch((e) => {
        setStatus($("saveStatus"), e.message || dt("startFail"), "err");
        setStatus($("listStatus"), e.message || dt("error"), "err");
      });
  }


  function syncEmptyState() {
    const empty = $("docsEmptyState");
    const paper = $("paperFit");
    if (!empty) return;
    const text = (getText() || "").replace(/\s+/g, " ").trim();
    const hasWork = !!currentDoc?.id || !!lastTemplateKey || text.length > 8;
    const show = !hasWork;
    empty.hidden = !show;
    empty.classList.toggle("is-on", show);
    if (paper) paper.classList.toggle("is-dimmed", show);
  }

  function tickSaveStatus() {
    if (!lastSavedAt || dirty) return;
    const el = $("saveStatus");
    if (!el || el.classList.contains("is-err")) return;
    setStatus(el, dt("autosaved", { when: formatRelativeWhen(new Date(lastSavedAt).toISOString()) }), "ok");
  }

  const MY_SIGN_KEY = "baupass-docs-my-signature";
  function readMySignature() {
    try {
      const raw = JSON.parse(localStorage.getItem(MY_SIGN_KEY) || "null");
      if (!raw?.dataUrl) return null;
      return raw;
    } catch {
      return null;
    }
  }
  function writeMySignature(dataUrl, name) {
    try {
      localStorage.setItem(MY_SIGN_KEY, JSON.stringify({ dataUrl, name: name || "", ts: Date.now() }));
      return true;
    } catch {
      return false;
    }
  }
  function saveMySignatureFromModal() {
    const canvas = $("signCanvas");
    if (!canvas || !signHasInk) {
      setStatus($("signModalStatus"), dt("signNeedInk"), "err");
      return;
    }
    const ok = writeMySignature(canvas.toDataURL("image/png"), String($("signNameInput")?.value || "").trim());
    setStatus($("signModalStatus"), ok ? dt("signSavedMine") : dt("signSaveFail"), ok ? "ok" : "err");
  }
  function loadMySignatureIntoModal() {
    const mine = readMySignature();
    if (!mine) {
      setStatus($("signModalStatus"), dt("signNoneMine"), "err");
      return;
    }
    bindSignCanvas();
    clearSignCanvas();
    const canvas = $("signCanvas");
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const img = new Image();
    img.onload = () => {
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      signHasInk = true;
      if ($("signNameInput") && mine.name) $("signNameInput").value = mine.name;
      setStatus($("signModalStatus"), dt("signLoadedMine"), "ok");
    };
    img.src = mine.dataUrl;
  }

  let presenceTimer = 0;
  let lastKnownUpdatedAt = "";
  let lastKnownContentHash = "";
  let peerCount = 0;
  let conflictIgnoredHash = "";
  let pendingRemoteHash = "";
  let collabReloading = false;

  function myActorId() {
    try {
      const u = JSON.parse(String(wpGet(USER_KEY) || "null"));
      return String(u?.id || u?.username || "");
    } catch {
      return "";
    }
  }

  function hideCollabConflict() {
    const el = $("collabConflictBanner");
    if (el) el.hidden = true;
  }

  function showCollabConflict() {
    const el = $("collabConflictBanner");
    if (el) el.hidden = false;
  }

  async function reloadFromServerQuiet() {
    if (!currentDoc?.id || collabReloading) return;
    collabReloading = true;
    try {
      const id = currentDoc.id;
      const data = await api(`/api/v2/docs/${encodeURIComponent(id)}${companyQuery()}`);
      loadIntoEditor(data.document);
      setStatus($("saveStatus"), dt("presenceReloaded"), "ok");
    } catch (e) {
      setStatus($("saveStatus"), e.message || dt("presenceUpdated"), "err");
    } finally {
      collabReloading = false;
    }
  }

  function renderPresence(peers) {
    const chip = $("presenceChip");
    const label = $("presenceLabel");
    if (!chip || !label) return;
    const meId = myActorId();
    const others = (peers || []).filter((p) => String(p.user_id || "") !== meId);
    peerCount = others.length;
    if (!others.length) {
      chip.hidden = true;
      return;
    }
    chip.hidden = false;
    const names = others.map((p) => p.display_name || p.user_id || "?").slice(0, 3);
    label.textContent =
      names.length === 1
        ? dt("presenceOne", { name: names[0] })
        : dt("presenceMany", { n: others.length, names: names.join(", ") });
    chip.title = others.map((p) => p.display_name || p.user_id).join(", ");
  }

  function applyPeerLive(peer) {
    if (!peer) return;
    const html = String(peer.live_html || peer.liveHtml || "");
    if (!html) return;
    const rev = Number(peer.live_rev || peer.liveRev || 0);
    if (rev && rev <= appliedLiveRev) return;
    setHtml(html);
    if (peer.live_title || peer.liveTitle) {
      const title = String(peer.live_title || peer.liveTitle || "").trim();
      if (title && $("docTitle")) $("docTitle").value = title;
    }
    dirty = false;
    appliedLiveRev = rev;
    liveRev = Math.max(liveRev, rev);
    setStatus($("saveStatus"), dt("liveApplied"), "ok");
    schedulePaperSync({ force: true });
  }

  function renderLiveTyping(peers) {
    const chip = $("liveTypingChip");
    const label = $("liveTypingLabel");
    if (!chip || !label) return;
    const meId = myActorId();
    const typing = (peers || []).filter((p) => {
      if (String(p.user_id || "") === meId) return false;
      return Number(p.live_rev || 0) > 0 && String(p.live_html || "").trim();
    });
    if (!typing.length) {
      chip.hidden = true;
      latestPeerLive = null;
      return;
    }
    typing.sort((a, b) => Number(b.live_rev || 0) - Number(a.live_rev || 0));
    latestPeerLive = typing[0];
    chip.hidden = false;
    chip.classList.toggle("is-following", liveFollow);
    label.textContent =
      typing.length === 1
        ? dt("liveTypingOne", { name: typing[0].display_name || typing[0].user_id || "?" })
        : dt("liveTypingMany", { n: typing.length });
    if ($("liveFollowBtn")) {
      $("liveFollowBtn").textContent = liveFollow ? dt("liveFollowing") : dt("liveFollow");
    }
  }

  function handlePeerLivePayload(peerLike) {
    if (!peerLike) return;
    const peer = {
      user_id: peerLike.userId || peerLike.user_id,
      display_name: peerLike.displayName || peerLike.display_name,
      live_html: peerLike.liveHtml || peerLike.live_html,
      live_title: peerLike.liveTitle || peerLike.live_title,
      live_rev: peerLike.liveRev || peerLike.live_rev,
    };
    latestPeerLive = peer;
    renderLiveTyping([peer]);
    // Never auto-overwrite the editor — only when user chose Live folgen.
    if (liveFollow) applyPeerLive(peer);
  }

  function ensureDocsSocket() {
    if (docsSocket || typeof window.io !== "function") return;
    try {
      docsSocket = window.io({
        path: "/socket.io",
        transports: ["websocket", "polling"],
        withCredentials: true,
      });
      docsSocket.on("docs_live", (payload) => {
        if (!currentDoc?.id) return;
        if (String(payload?.documentId || "") !== String(currentDoc.id)) return;
        if (String(payload?.userId || "") === myActorId()) return;
        handlePeerLivePayload(payload);
      });
    } catch {
      docsSocket = null;
    }
  }

  function subscribeDocsSocket() {
    ensureDocsSocket();
    if (!docsSocket || !currentDoc?.id) return;
    const token = wpGet(TOKEN_KEY) || "";
    docsSocket.emit("subscribe", { company_id: activeCompanyId(), session_token: token });
    docsSocket.emit("docs_subscribe", {
      company_id: activeCompanyId(),
      document_id: currentDoc.id,
      session_token: token,
    });
  }

  async function heartbeatPresence() {
    if (!currentDoc?.id || !activeCompanyId()) return;
    try {
      const payload = { company_id: activeCompanyId() };
      if (dirty) {
        payload.liveRev = liveRev;
        payload.liveTitle = String($("docTitle")?.value || "");
        payload.liveHtml = getHtml();
      }
      const data = await api(`/api/v2/docs/${encodeURIComponent(currentDoc.id)}/presence${companyQuery()}`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      renderPresence(data.peers || []);
      renderLiveTyping(data.peers || []);
      const meId = myActorId();
      const others = (data.peers || []).filter((p) => String(p.user_id || "") !== meId);
      const bestLive = others
        .filter((p) => Number(p.live_rev || 0) > appliedLiveRev && String(p.live_html || "").trim())
        .sort((a, b) => Number(b.live_rev || 0) - Number(a.live_rev || 0))[0];
      if (bestLive && liveFollow) {
        applyPeerLive(bestLive);
      }
      const remote = String(data.updatedAt || "");
      const remoteHash = String(data.contentHash || "");
      if (remoteHash && lastKnownContentHash && remoteHash !== lastKnownContentHash) {
        if (!dirty && !liveFollow) {
          lastKnownContentHash = remoteHash;
          if (remote) lastKnownUpdatedAt = remote;
          await reloadFromServerQuiet();
          return;
        }
        if (remoteHash !== conflictIgnoredHash) {
          pendingRemoteHash = remoteHash;
          showCollabConflict();
        }
      } else if (remoteHash && !lastKnownContentHash) {
        lastKnownContentHash = remoteHash;
      }
      if (remote) lastKnownUpdatedAt = remote;
      if (docsSocket && dirty && peerCount > 0) {
        docsSocket.emit("docs_live", {
          company_id: activeCompanyId(),
          document_id: currentDoc.id,
          session_token: wpGet(TOKEN_KEY) || "",
          user_id: meId,
          display_name: myActorId(),
          liveRev,
          liveTitle: payload.liveTitle,
          liveHtml: payload.liveHtml,
        });
      }
    } catch {
      /* ignore */
    }
  }

  function startPresenceLoop() {
    subscribeDocsSocket();
    if (presenceTimer) {
      heartbeatPresence().catch(() => {});
      return;
    }
    heartbeatPresence().catch(() => {});
    presenceTimer = window.setInterval(() => heartbeatPresence().catch(() => {}), peerCount > 0 ? 2500 : 8000);
  }

  function stopPresenceLoop() {
    if (presenceTimer) window.clearInterval(presenceTimer);
    presenceTimer = 0;
    peerCount = 0;
    liveFollow = false;
    latestPeerLive = null;
    renderPresence([]);
    renderLiveTyping([]);
    hideCollabConflict();
  }

  async function refreshSignatures() {
    const list = $("signaturesList");
    const status = $("signaturesStatus");
    if (!list || !status) return;
    if (!currentDoc?.id) {
      list.innerHTML = `<li><p class="empty-list">${escapeHtml(dt("signAuditNone"))}</p></li>`;
      setStatus(status, "—");
      return;
    }
    try {
      const data = await api(`/api/v2/docs/${encodeURIComponent(currentDoc.id)}/signatures${companyQuery()}`);
      const items = data.items || [];
      setStatus(status, items.length ? dt("signAuditCount", { n: items.length }) : "—");
      list.innerHTML = items.length
        ? items
            .map(
              (s) => `<li class="version-row">
              <span class="doc-title">${escapeHtml(s.signer_name || "—")}</span>
              <span class="doc-badge ${Number(s.stamped) ? "status-approved" : ""}">${escapeHtml(Number(s.stamped) ? dt("signStamp") : dt("snSign"))}</span>
              <span class="doc-sub">${escapeHtml(formatWhen(s.created_at))} · ${escapeHtml(String(s.content_hash || "").slice(0, 10))}</span>
            </li>`,
            )
            .join("")
        : `<li><p class="empty-list">${escapeHtml(dt("signAuditEmpty"))}</p></li>`;
    } catch (e) {
      setStatus(status, e.message || "—", "err");
    }
  }

  async function recordSignatureAudit({ signerName, stamped, signatureData, pin, lockAfter }) {
    if (!currentDoc?.id) {
      try {
        await saveDoc();
      } catch {
        /* ignore */
      }
    }
    if (!currentDoc?.id) throw new Error(dt("needSave"));
    const data = await api(`/api/v2/docs/${encodeURIComponent(currentDoc.id)}/signatures${companyQuery()}`, {
      method: "POST",
      body: JSON.stringify({
        company_id: activeCompanyId(),
        signerName: signerName || "",
        stamped: !!stamped,
        signatureData: signatureData || "",
        pin: pin || "",
        lockAfter: !!lockAfter,
      }),
    });
    if (data.document) {
      currentDoc = data.document;
      renderDocMeta(currentDoc);
      maybeAutoWatermark(currentDoc?.status);
      lastKnownUpdatedAt = String(currentDoc?.updated_at || "");
      lastKnownContentHash = "";
    }
    refreshSignatures().catch(() => {});
    return data;
  }

  function populateEmailWorkers() {
    const sel = $("emailWorkerSelect");
    const src = $("workerSelect");
    if (!sel || !src) return;
    const keep = sel.value;
    sel.innerHTML = `<option value="">${escapeHtml(dt("emailToManual"))}</option>`;
    [...src.options].forEach((o) => {
      if (!o.value) return;
      const opt = document.createElement("option");
      opt.value = o.value;
      opt.textContent = o.textContent;
      opt.dataset.email = o.dataset.email || "";
      const m = /([\w.+-]+@[\w.-]+\.[A-Za-z]{2,})/.exec(o.textContent || "");
      if (m) opt.dataset.email = opt.dataset.email || m[1];
      sel.appendChild(opt);
    });
    if (keep) sel.value = keep;
  }

  async function openPrintPreviewPdf() {
    const modal = $("printPreviewModal");
    const body = $("printPreviewBody");
    if (!modal || !body) return;
    hideAiOperatorForPrint(true);
    if (body._pdfUrl) {
      try {
        URL.revokeObjectURL(body._pdfUrl);
      } catch {
        /* ignore */
      }
      body._pdfUrl = null;
    }
    body.innerHTML = `<p class="rail-note">${escapeHtml(dt("emailPreparingPdf"))}</p>`;
    modal.hidden = false;
    try {
      const { blob, filename } = await exportPdfBlob();
      const url = URL.createObjectURL(blob);
      body.innerHTML = `<iframe class="print-pdf-frame" title="${escapeHtml(filename)}" src="${url}"></iframe>`;
      if ($("printPreviewMeta")) $("printPreviewMeta").textContent = filename;
      body._pdfUrl = url;
    } catch (e) {
      body.innerHTML = `<p class="status is-err">${escapeHtml(e.message || dt("emailPdfFail"))}</p>`;
    }
  }

  function scanOfflineDrafts() {
    const cid = activeCompanyId() || "none";
    const prefix = `${OFFLINE_PREFIX}${cid}:`;
    let best = null;
    try {
      for (let i = 0; i < localStorage.length; i += 1) {
        const key = localStorage.key(i);
        if (!key || !key.startsWith(prefix)) continue;
        const draft = JSON.parse(localStorage.getItem(key) || "null");
        if (!draft?.html || !draft?.ts) continue;
        if (!best || draft.ts > best.ts) best = draft;
      }
    } catch {
      /* ignore */
    }
    return best;
  }


  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", main);
  else main();
})();
