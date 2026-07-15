// Admin voice-call UI smoke with mocked WebRTC + chat APIs.
const { test, expect } = require("@playwright/test");

const COMPANY_ID = "co-e2e-calls";
const WORKER_ID = "wrk-e2e-calls";
const THREAD_ID = "thr-e2e-calls";
const CALL_ID = "call-e2e-1";

async function installWebRtcMocks(page) {
  await page.addInitScript(() => {
    class FakeTrack {
      constructor(kind = "audio") {
        this.kind = kind;
        this.enabled = true;
        this.id = `track-${kind}-${Math.random().toString(16).slice(2)}`;
      }
      stop() {}
    }
    class FakeStream {
      constructor() {
        this._tracks = [new FakeTrack("audio")];
      }
      getTracks() {
        return this._tracks.slice();
      }
      getAudioTracks() {
        return this._tracks.filter((t) => t.kind === "audio");
      }
    }
    class FakeRTCPeerConnection {
      constructor() {
        this.onicecandidate = null;
        this.ontrack = null;
        this.localDescription = null;
        this.remoteDescription = null;
        this.signalingState = "stable";
        this.iceConnectionState = "new";
        this.connectionState = "new";
      }
      addTrack() {
        return { stop() {} };
      }
      addTransceiver() {
        return {};
      }
      createDataChannel() {
        return { close() {}, readyState: "open" };
      }
      close() {}
      addEventListener() {}
      removeEventListener() {}
      setLocalDescription(desc) {
        this.localDescription = desc;
        return Promise.resolve();
      }
      setRemoteDescription(desc) {
        this.remoteDescription = desc;
        return Promise.resolve();
      }
      createOffer() {
        return Promise.resolve({ type: "offer", sdp: "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\n" });
      }
      createAnswer() {
        return Promise.resolve({ type: "answer", sdp: "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\n" });
      }
      addIceCandidate() {
        return Promise.resolve();
      }
      getStats() {
        return Promise.resolve(new Map());
      }
    }
    window.RTCPeerConnection = FakeRTCPeerConnection;
    navigator.mediaDevices = {
      getUserMedia: async () => new FakeStream(),
      enumerateDevices: async () => [],
    };
    try {
      localStorage.setItem("workpass-admin-token", "e2e-admin-token");
      localStorage.setItem(
        "workpass-admin-user",
        JSON.stringify({
          id: "usr-e2e-admin",
          role: "company-admin",
          company_id: "co-e2e-calls",
          name: "E2E Admin",
        }),
      );
      localStorage.setItem("workpass-admin-company", "co-e2e-calls");
    } catch (_) {
      /* ignore */
    }
  });
}

async function mockChatApis(page) {
  await page.route("**/api/**", async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname;
    const method = req.method().toUpperCase();

    const json = (body, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
      });

    if (path === "/api/session/bootstrap") {
      return json({
        ok: true,
        token: "e2e-admin-token",
        user: {
          id: "usr-e2e-admin",
          role: "company-admin",
          company_id: COMPANY_ID,
          name: "E2E Admin",
        },
      });
    }
    if (path === "/api/chat/threads" && method === "GET") {
      return json({
        threads: [
          {
            id: THREAD_ID,
            worker_id: WORKER_ID,
            first_name: "Ali",
            last_name: "Test",
            subject: "Baustelle",
            unread_count: 0,
            last_message_at: new Date().toISOString(),
          },
        ],
      });
    }
    if (path.includes(`/api/chat/threads/${THREAD_ID}`) && method === "GET") {
      return json({ messages: [], ok: true });
    }
    if (path === "/api/chat/calls" && method === "POST") {
      return json({
        ok: true,
        call: {
          id: CALL_ID,
          status: "ringing",
          workerId: WORKER_ID,
          iceServers: [],
        },
      });
    }
    if (path.includes(`/api/chat/calls/${CALL_ID}/signal`) && method === "POST") {
      return json({ ok: true });
    }
    if (path.includes(`/api/chat/calls/${CALL_ID}/signals`) && method === "GET") {
      return json({ ok: true, call: { id: CALL_ID, status: "ringing" }, signals: [] });
    }
    if (path === "/api/chat/calls/incoming") {
      return json({ ok: true, call: null });
    }
    if (path.includes("/api/chat/thread-prefs") || path.includes("/api/chat/message-prefs")) {
      return json({ ok: true, prefs: {} });
    }
    if (path.includes("/api/chat/push")) {
      return json({ ok: true, enabled: false });
    }
    if (path.includes("/typing")) {
      return json({ ok: true, typing: false });
    }
    if (path.includes("/e2e") || path.includes("/crypto")) {
      return json({ ok: true });
    }
    return json({ ok: true });
  });
}

test.describe("chat voice calls (mocked webrtc)", () => {
  test("admin dial opens call overlay and shows ringing", async ({ page }) => {
    await installWebRtcMocks(page);
    await mockChatApis(page);

    await page.goto(`/admin-v2/chat.html?company_id=${COMPANY_ID}`);
    await expect(page.locator(".thread-item[data-worker]").first()).toBeVisible({ timeout: 15000 });
    await page.locator(".thread-item[data-worker]").first().click();
    await expect(page.locator("#chatVoiceCallBtn")).toBeVisible();

    await page.locator("#chatVoiceCallBtn").click();
    const overlay = page.locator("#voiceCallOverlay");
    await expect(overlay).not.toHaveClass(/hidden/, { timeout: 10000 });
    await expect(page.locator("#voiceCallStatus")).toContainText(/Wählt|Klingelt|Ring|Dial|Connecting|Verbind/i);
    await expect(page.locator("#voiceCallHangupBtn")).toBeVisible();
  });
});
