/**
 * Paste near the top of WorkPass Lohn auth-gate.js (inside the IIFE, before init()).
 * Enables one-click SSO from SUPPIX: URL hash #suppix-sso={urlencoded JSON}
 * Payload: { token, expiresAt, user, via }  — token is data.session from /v1/auth/login
 */
(function consumeSuppixSsoHash() {
  try {
    const hash = String(location.hash || "");
    const m = hash.match(/#suppix-sso=([^&]+)/);
    if (!m) return;
    const data = JSON.parse(decodeURIComponent(m[1]));
    if (!data || !data.token) return;
    localStorage.setItem(
      "workpassPlatformSessionV2",
      JSON.stringify({
        token: data.token,
        expiresAt: data.expiresAt,
        user: data.user || null,
        via: data.via || "suppix",
      }),
    );
    if (data.user && data.user.companyId) {
      const prev = JSON.parse(localStorage.getItem("workpass.lohn.apiConfig.v1") || "{}");
      localStorage.setItem(
        "workpass.lohn.apiConfig.v1",
        JSON.stringify({ ...prev, companyId: data.user.companyId }),
      );
    }
    history.replaceState(null, "", location.pathname + location.search);
    location.reload();
  } catch (e) {
    /* ignore malformed handoff */
  }
})();
