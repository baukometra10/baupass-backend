// Smoke scaffold for admin/worker voice-call UI.
// Requires mocked WebRTC; skipped until staging fixtures are wired.
const { test, expect } = require("@playwright/test");

test.describe("chat voice calls (mocked webrtc)", () => {
  test.skip(true, "Enable after seeding admin+worker sessions and WebRTC mocks");

  test("admin dial button opens call overlay", async ({ page }) => {
    await page.addInitScript(() => {
      class FakeRTCPeerConnection {
        createDataChannel() { return { close() {} }; }
        close() {}
        addEventListener() {}
        removeEventListener() {}
        setLocalDescription() { return Promise.resolve(); }
        setRemoteDescription() { return Promise.resolve(); }
        createOffer() { return Promise.resolve({ type: "offer", sdp: "v=0" }); }
        createAnswer() { return Promise.resolve({ type: "answer", sdp: "v=0" }); }
        addIceCandidate() { return Promise.resolve(); }
      }
      window.RTCPeerConnection = FakeRTCPeerConnection;
      navigator.mediaDevices = {
        getUserMedia: async () => ({
          getTracks: () => [{ stop() {}, kind: "audio", enabled: true }],
          getAudioTracks: () => [{ stop() {}, kind: "audio", enabled: true }],
        }),
      };
    });

    await page.goto("/admin-v2/chat.html");
    // Seeded login + open thread, then:
    // await page.click("#chatVoiceCallBtn");
    // await expect(page.locator("#voiceCallOverlay")).not.toHaveClass(/hidden/);
    await expect(page.locator("body")).toBeVisible();
  });
});
