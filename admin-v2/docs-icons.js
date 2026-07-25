/**
 * SUPPIX Docs — premium SVG icon kit.
 * Quill toolbar icons are installed via ui/icons BEFORE editor init (official path).
 * Custom chrome buttons use data-wp-ico + mountAll().
 */
(function (global) {
  const PATHS = {
    undo: '<path d="M3 7v6h6"/><path d="M3 13a9 9 0 1 0 3-7.7L3 7"/>',
    redo: '<path d="M21 7v6h-6"/><path d="M21 13a9 9 0 1 1-3-7.7L21 7"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    searchPrev: '<path d="m18 15-6-6-6 6"/>',
    searchNext: '<path d="m6 9 6 6 6-6"/>',
    close: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    bold: '<path d="M7 4h6a3.5 3.5 0 0 1 0 7H7z"/><path d="M7 11h7a3.5 3.5 0 0 1 0 7H7z"/>',
    italic: '<path d="M14 4H8"/><path d="M16 20H10"/><path d="m12 4-3 16"/>',
    underline: '<path d="M7 4v8a5 5 0 0 0 10 0V4"/><path d="M5 20h14"/>',
    strike: '<path d="M5 12h14"/><path d="M16.2 6.5A4.2 4.2 0 0 0 8.4 8"/><path d="M7.8 15.6A4.2 4.2 0 0 0 16 17.2"/>',
    listOrdered:
      '<path d="M11 6h10"/><path d="M11 12h10"/><path d="M11 18h10"/><path d="M4 6h1v4"/><path d="M4 10h2"/><path d="M6 18H4c0-1 2-2 2-3s-1-1.5-2-1"/>',
    listBullet:
      '<path d="M11 6h10"/><path d="M11 12h10"/><path d="M11 18h10"/><circle cx="5" cy="6" r="1.35"/><circle cx="5" cy="12" r="1.35"/><circle cx="5" cy="18" r="1.35"/>',
    indentLess: '<path d="M3 6h18"/><path d="M9 12h12"/><path d="M3 18h18"/><path d="m7 9-3 3 3 3"/>',
    indentMore: '<path d="M3 6h18"/><path d="M9 12h12"/><path d="M3 18h18"/><path d="m5 9 3 3-3 3"/>',
    link: '<path d="M10 13a5 5 0 0 0 7.07 0l1.8-1.8a5 5 0 0 0-7.07-7.07L10.5 5.5"/><path d="M14 11a5 5 0 0 0-7.07 0L5.2 12.8a5 5 0 0 0 7.07 7.07L13.5 18.5"/>',
    quote: '<path d="M6 17h3l2-4V7H5v6h3z"/><path d="M14 17h3l2-4V7h-6v6h3z"/>',
    clean: '<path d="m5 7 1.5-2h11L19 7"/><path d="M9 7v11a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1V7"/><path d="M10 11v5"/><path d="M14 11v5"/>',
    color: '<path d="M4 20h16"/><path d="m7 14 5-10 5 10"/><path d="M8.5 11h7"/>',
    highlight: '<path d="m9 11-5 5v3h3l5-5"/><path d="M13.5 7.5 16 5l3 3-2.5 2.5z"/><path d="m11 13 3 3"/>',
    alignLeft: '<path d="M4 6h16"/><path d="M4 12h10"/><path d="M4 18h14"/>',
    alignCenter: '<path d="M4 6h16"/><path d="M7 12h10"/><path d="M5 18h14"/>',
    alignRight: '<path d="M4 6h16"/><path d="M10 12h10"/><path d="M6 18h14"/>',
    alignJustify: '<path d="M4 6h16"/><path d="M4 12h16"/><path d="M4 18h16"/>',
    table:
      '<rect x="3" y="4" width="18" height="16" rx="1.5"/><path d="M3 10h18"/><path d="M3 15h18"/><path d="M9 4v16"/><path d="M15 4v16"/>',
    pageBreak:
      '<path d="M4 8V5a1 1 0 0 1 1-1h5"/><path d="M14 4h5a1 1 0 0 1 1 1v3"/><path d="M4 16v3a1 1 0 0 0 1 1h5"/><path d="M14 20h5a1 1 0 0 0 1-1v-3"/><path d="M8 12h8"/>',
    hr: '<path d="M4 12h16"/><path d="M8 8v8"/><path d="M16 8v8"/>',
    zoomIn: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/><path d="M11 8v6"/><path d="M8 11h6"/>',
    zoomOut: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/><path d="M8 11h6"/>',
    zoomFit: '<path d="M8 3H4v4"/><path d="M16 3h4v4"/><path d="M8 21H4v-4"/><path d="M16 21h4v-4"/><rect x="8" y="8" width="8" height="8" rx="1"/>',
    save: '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><path d="M17 21v-8H7v8"/><path d="M7 3v5h8"/>',
    more: '<circle cx="6" cy="12" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="18" cy="12" r="1.4"/>',
    plus: '<path d="M12 5v14"/><path d="M5 12h14"/>',
    command:
      '<path d="M8 7V5a2 2 0 0 0-2-2H5"/><path d="M16 7V5a2 2 0 0 1 2-2h1"/><path d="M8 17v2a2 2 0 0 1-2 2H5"/><path d="M16 17v2a2 2 0 0 0 2 2h1"/><rect x="7" y="7" width="10" height="10" rx="1.5"/>',
    image:
      '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="m21 15-4.5-4.5L9 18"/>',
    comment:
      '<path d="M5 5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H9l-4 3v-3H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z"/>',
    print:
      '<path d="M6 9V3h12v6"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><path d="M6 14h12v7H6z"/>',
    signature:
      '<path d="M4 20h16"/><path d="m5 16 3.2-8.5a1.2 1.2 0 0 1 2.2 0L14 16"/><path d="M9 12h4"/><path d="m16 14 3-3 1.5 1.5-3 3H16z"/>',
  };

  const FILLED = new Set(["listBullet", "more"]);

  function tagBody(name, quillMode) {
    let body = PATHS[name];
    if (!body) return "";
    if (quillMode) {
      // Quill snow paints .ql-stroke / .ql-fill — required for visibility.
      body = body
        .replace(/<path\b/g, '<path class="ql-stroke"')
        .replace(/<rect\b/g, '<rect class="ql-stroke"')
        .replace(/<circle\b/g, FILLED.has(name) ? '<circle class="ql-fill"' : '<circle class="ql-stroke"');
    }
    return body;
  }

  function svg(name, opts = {}) {
    if (!PATHS[name]) return "";
    const quillMode = !!opts.quill;
    const body = tagBody(name, quillMode);
    if (quillMode) {
      return (
        `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">` +
        body +
        `</svg>`
      );
    }
    return (
      `<svg class="wp-ico-svg" viewBox="0 0 24 24" width="16" height="16" fill="none" ` +
      `stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">` +
      body +
      `</svg>`
    );
  }

  function mount(el, name, force) {
    if (!el || !name || !PATHS[name]) return;
    if (!force && el.dataset.wpIco === name && el.querySelector(".wp-ico-svg")) return;
    el.dataset.wpIco = name;
    const keepLabel = el.querySelector(".wp-ico-label");
    const labelHtml = keepLabel ? keepLabel.outerHTML : "";
    const textBits = [...el.childNodes]
      .filter((n) => n.nodeType === 3 && String(n.textContent || "").trim())
      .map((n) => String(n.textContent).trim());
    const fallbackLabel =
      !keepLabel && textBits.length
        ? `<span class="wp-ico-label">${textBits.join(" ")}</span>`
        : labelHtml;
    el.innerHTML = `<span class="wp-ico">${svg(name)}</span>${fallbackLabel}`;
  }

  function mountAll(root, force) {
    const scope = root || document;
    scope.querySelectorAll("[data-wp-ico]").forEach((el) => {
      mount(el, el.getAttribute("data-wp-ico"), force);
    });
  }

  /**
   * Official Quill path — must run BEFORE `new Quill(...)`.
   */
  function installQuillIcons(Quill) {
    if (!Quill || typeof Quill.import !== "function") return false;
    let icons;
    try {
      icons = Quill.import("ui/icons");
    } catch {
      return false;
    }
    if (!icons) return false;

    const q = (name) => svg(name, { quill: true });

    icons.bold = q("bold");
    icons.italic = q("italic");
    icons.underline = q("underline");
    icons.strike = q("strike");
    icons.link = q("link");
    icons.blockquote = q("quote");
    icons.clean = q("clean");
    icons.color = q("color");
    icons.background = q("highlight");

    if (typeof icons.list !== "object" || icons.list === null) icons.list = {};
    icons.list.ordered = q("listOrdered");
    icons.list.bullet = q("listBullet");

    if (typeof icons.indent !== "object" || icons.indent === null) icons.indent = {};
    icons.indent["-1"] = q("indentLess");
    icons.indent["+1"] = q("indentMore");

    if (typeof icons.align !== "object" || icons.align === null) icons.align = {};
    icons.align[""] = q("alignLeft");
    icons.align.left = q("alignLeft");
    icons.align.center = q("alignCenter");
    icons.align.right = q("alignRight");
    icons.align.justify = q("alignJustify");

    return true;
  }

  /** Safety net if Quill rebuilds a control without our icon. */
  function decorateQuillToolbar(toolbar) {
    if (!toolbar) return;
    const map = [
      [".ql-bold", "bold"],
      [".ql-italic", "italic"],
      [".ql-underline", "underline"],
      [".ql-strike", "strike"],
      ['.ql-list[value="ordered"]', "listOrdered"],
      ['.ql-list[value="bullet"]', "listBullet"],
      ['.ql-indent[value="-1"]', "indentLess"],
      ['.ql-indent[value="+1"]', "indentMore"],
      [".ql-link", "link"],
      [".ql-blockquote", "quote"],
      [".ql-clean", "clean"],
    ];
    map.forEach(([sel, name]) => {
      toolbar.querySelectorAll(sel).forEach((btn) => {
        if (btn.querySelector("svg")) {
          // Ensure ql-stroke classes exist (Quill may inject raw svg).
          if (!btn.querySelector(".ql-stroke, .ql-fill, .wp-ico-svg")) {
            btn.innerHTML = svg(name, { quill: true });
          }
          return;
        }
        btn.innerHTML = svg(name, { quill: true });
      });
    });

    const ensurePickerIcon = (pickerSel, name) => {
      const label = toolbar.querySelector(`${pickerSel} .ql-picker-label`);
      if (!label) return;
      if (!label.querySelector("svg")) {
        label.insertAdjacentHTML("afterbegin", svg(name, { quill: true }));
      }
    };
    ensurePickerIcon(".ql-color", "color");
    ensurePickerIcon(".ql-background", "highlight");

    const alignMap = {
      "": "alignLeft",
      left: "alignLeft",
      center: "alignCenter",
      right: "alignRight",
      justify: "alignJustify",
    };
    toolbar.querySelectorAll(".ql-align .ql-picker-label, .ql-align .ql-picker-item").forEach((el) => {
      const key = el.getAttribute("data-value") || "";
      const name = alignMap[key] || "alignLeft";
      if (!el.querySelector("svg")) {
        el.innerHTML = svg(name, { quill: true });
      } else if (el.classList.contains("ql-picker-label") && !el.querySelector(".ql-stroke, .ql-fill")) {
        el.innerHTML = svg(name, { quill: true });
      }
    });
  }

  global.DocsIcons = {
    svg,
    mount,
    mountAll,
    installQuillIcons,
    decorateQuillToolbar,
    names: Object.keys(PATHS),
  };
})(window);
