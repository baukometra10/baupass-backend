/**
 * SUPPIX chat attach sheet — WhatsApp-style + menu for file/photo/location.
 */
(function initSuppixChatAttachSheet(global) {
  function closeAllSheets(except) {
    global.document?.querySelectorAll(".chat-attach-sheet:not(.hidden)").forEach((node) => {
      if (except && node === except) return;
      node.classList.add("hidden");
    });
  }

  function mountChatAttachSheet({
    triggerEl,
    sheetEl,
    onSelect,
    onOpen,
    onClose,
  } = {}) {
    if (!triggerEl || !sheetEl || triggerEl.dataset.attachBound) {
      return () => {};
    }
    triggerEl.dataset.attachBound = "1";
    const toggle = (force) => {
      const open = typeof force === "boolean" ? force : sheetEl.classList.contains("hidden");
      if (open) {
        closeAllSheets(sheetEl);
        sheetEl.classList.remove("hidden");
        onOpen?.();
      } else {
        sheetEl.classList.add("hidden");
        onClose?.();
      }
    };
    triggerEl.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      toggle();
    });
    sheetEl.querySelectorAll("[data-attach-action]").forEach((btn) => {
      btn.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const action = btn.getAttribute("data-attach-action") || "";
        sheetEl.classList.add("hidden");
        onClose?.();
        onSelect?.(action, btn);
      });
    });
    const docHandler = (event) => {
      if (sheetEl.classList.contains("hidden")) return;
      const target = event.target;
      if (target instanceof Element && (sheetEl.contains(target) || triggerEl.contains(target))) {
        return;
      }
      sheetEl.classList.add("hidden");
      onClose?.();
    };
    global.document?.addEventListener("click", docHandler);
    global.document?.addEventListener("keydown", (event) => {
      if (event.key === "Escape") toggle(false);
    });
    return () => {
      global.document?.removeEventListener("click", docHandler);
      sheetEl.classList.add("hidden");
    };
  }

  global.SUPPIXChatAttachSheet = {
    mountChatAttachSheet,
    closeAllSheets,
  };
})(typeof window !== "undefined" ? window : globalThis);
