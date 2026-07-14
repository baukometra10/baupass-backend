/**
 * SUPPIX chat typing indicators — debounced POST + poll/realtime display.
 */
(function initSuppixChatTyping(global) {
  const TYPING_DEBOUNCE_MS = 1800;
  const TYPING_POLL_MS = 2200;
  const TYPING_HIDE_MS = 4200;

  function labelForActors(actors, labels) {
    const rows = Array.isArray(actors) ? actors : [];
    if (!rows.length) return "";
    const workerLabel = labels.workerTyping || "Mitarbeiter tippt…";
    const adminLabel = labels.adminTyping || "Arbeitgeber tippt…";
    const hasWorker = rows.some((row) => String(row?.actorType || "") === "worker");
    const hasAdmin = rows.some((row) => String(row?.actorType || "") !== "worker");
    if (hasWorker && hasAdmin) return labels.bothTyping || "Beide tippen…";
    if (hasWorker) return workerLabel;
    if (hasAdmin) return adminLabel;
    return "";
  }

  function createTypingController({
    threadId,
    actorType,
    actorId,
    actorLabel = "",
    workerId = "",
    companyId = "",
    postTyping,
    fetchTyping,
    onLabel,
    labels = {},
    onRealtimeTyping,
  } = {}) {
    let stopped = false;
    let debounceTimer = null;
    let pollTimer = null;
    let hideTimer = null;
    let lastSentAt = 0;

    const sendTyping = () => {
      if (stopped || !threadId) return;
      const now = Date.now();
      if (now - lastSentAt < 1200) return;
      lastSentAt = now;
      void postTyping?.({
        threadId,
        actorType,
        actorId,
        actorLabel,
        workerId,
        companyId,
      });
    };

    const scheduleTyping = () => {
      if (stopped) return;
      if (debounceTimer) global.clearTimeout(debounceTimer);
      debounceTimer = global.setTimeout(sendTyping, TYPING_DEBOUNCE_MS);
      sendTyping();
    };

    const showLabel = (text) => {
      const value = String(text || "").trim();
      onLabel?.(value);
      if (hideTimer) global.clearTimeout(hideTimer);
      if (value) {
        hideTimer = global.setTimeout(() => onLabel?.(""), TYPING_HIDE_MS);
      }
    };

    const poll = async () => {
      if (stopped || !threadId) return;
      try {
        const actors = await fetchTyping?.({ threadId, actorType, actorId, workerId, companyId });
        showLabel(labelForActors(actors, labels));
      } catch {
        /* retry */
      }
      if (!stopped) pollTimer = global.setTimeout(poll, TYPING_POLL_MS);
    };

    const handleRealtime = (evt) => {
      if (stopped) return;
      const type = String(evt?.type || "");
      if (type !== "chat.typing") return;
      const payload = evt?.payload || {};
      if (String(payload.threadId || "") !== String(threadId || "")) return;
      if (
        String(payload.actorType || "") === String(actorType || "")
        && String(payload.actorId || "") === String(actorId || "")
      ) {
        return;
      }
      onRealtimeTyping?.(payload);
      const actors = [{
        actorType: payload.actorType,
        actorId: payload.actorId,
        actorLabel: payload.actorLabel,
      }];
      showLabel(labelForActors(actors, labels));
    };

    const bindInput = (inputEl) => {
      if (!inputEl || inputEl.dataset.typingBound) return;
      inputEl.dataset.typingBound = "1";
      inputEl.addEventListener("input", scheduleTyping);
      inputEl.addEventListener("keydown", scheduleTyping);
      inputEl.addEventListener("blur", () => {
        if (debounceTimer) global.clearTimeout(debounceTimer);
      });
    };

    poll();

    return {
      bindInput,
      handleRealtime,
      refresh: poll,
      stop() {
        stopped = true;
        if (debounceTimer) global.clearTimeout(debounceTimer);
        if (pollTimer) global.clearTimeout(pollTimer);
        if (hideTimer) global.clearTimeout(hideTimer);
        onLabel?.("");
      },
    };
  }

  global.SUPPIXChatTyping = {
    labelForActors,
    createTypingController,
  };
})(typeof window !== "undefined" ? window : globalThis);
