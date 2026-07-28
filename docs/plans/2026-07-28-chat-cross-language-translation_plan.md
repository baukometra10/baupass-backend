# Chat Cross-Language Translation Plan

**Date:** 2026-07-28  
**Goal:** Employee ↔ employer chat understands each other across languages. Same language → leave messages unchanged.

## Problem

- Worker app language (`LocaleController` / `workpass-worker-lang`) and admin chat UI language (`baupass-admin-v2-lang`) are already separate.
- Chat `body` is stored as-is (often E2E-encrypted). There is **no** message translation today.
- Docs editor already has OpenAI translate prompts (`translate_de|en|ar|tr|fr|es|it|pl`) in `backend/app/domains/docs/service.py` — reusable pattern.

## Product rules

1. **Different languages** (e.g. employer EN, worker AR): each side sees the message in *their* UI language.
2. **Same language** (e.g. both DE): show original only — **no** API call, no rewrite.
3. **UX (decided):** bubble shows **translation only** by default. Original stays hidden until the user opens the existing message menu (long-press / tap actions: reply, pin, delete, forward, …) and chooses **“Show original”** / **“إظهار النص الأصلي”**. Tap again or **“Show translation”** to switch back.
4. Skip non-text payloads: voice, location markers (`@voice-call|`, `@location|`), empty body, E2E envelopes until decrypted client-side.
5. Supported langs = same 8 as the app: `de en tr ar pl fr es it`.
6. Optional subtle cue on translated bubbles (e.g. small “Translated” / icon) so users know a translation is active — without cluttering the thread.

## Recommended approach: translate on view (not on send)

Translate for the **viewer’s current UI language**, using the message’s stored `source_lang`.

```
send:   body + source_lang (sender UI lang)
store:  original body unchanged (+ source_lang column)
show:   if viewer_lang == source_lang (or missing) → original only (no menu item)
        else → show translation in bubble; menu action reveals original
```

Why not translate-on-send into all peer langs?

- Admin lang lives in `localStorage` today; multiple admins can differ.
- E2E: server cannot read ciphertext → cannot pre-translate.
- On-view matches “I speak Arabic / they speak English” without guessing the peer at send time.

## Architecture

```mermaid
sequenceDiagram
  participant W as Worker app
  participant A as Admin chat
  participant API as Backend
  participant AI as OpenAI translate

  W->>API: POST message { body, source_lang: ar }
  API->>API: store body + source_lang
  A->>API: GET messages
  API-->>A: body, source_lang: ar
  Note over A: decrypt if E2E; viewer_lang=en
  A->>API: POST /chat/translate { text, from: ar, to: en, message_id }
  API->>AI: translate prompt
  AI-->>API: English text
  API-->>A: { translation, cached }
  A->>A: show EN in bubble; menu → Show original (AR)
```

## Backend

### Schema (`ChatService._ensure_schema`)

Add nullable columns on `chat_messages`:

- `source_lang TEXT` — ISO code from sender UI (`de`…`it`)
- Optional later: `translations_json TEXT` — server cache `{ "en": "...", "de": "..." }` for **non-E2E** plaintext only

### Message create

Extend `create_message` / routes (admin + worker):

- Accept optional `source_lang` / `sourceLang` in JSON.
- Normalize to supported set; default `de` if missing.
- Persist with body; never mutate `body` for translation.

Files: `backend/app/domains/chat/service.py`, `backend/app/domains/chat/routes.py`.

### Translate endpoint (new)

`POST /api/chat/translate` (admin auth)  
`POST /api/worker-app/chat/translate` (worker session)

Body: `{ text, sourceLang?, targetLang, messageId? }`

Logic:

1. Reject if `targetLang` not supported / text empty / looks like e2e envelope or system marker.
2. If `sourceLang == targetLang` → `{ skipped: true, text }`.
3. Optional: if `sourceLang` empty, light heuristic or treat as unknown and still translate to target.
4. Call shared helper extracted from docs AI translate prompts (reuse `natural_language_query` or a thin `translate_text(text, target_lang)` in `backend/app/platform/ai/`).
5. Cache by `(message_id, target_lang)` in memory/DB for plaintext messages; for E2E, client may pass `messageId` only for rate-limit keying — **do not** store plaintext translation server-side when body is E2E (privacy). Client-side cache is enough for E2E.
6. Rate-limit per company/user; require `OPENAI_API_KEY` (or Azure) like docs AI; clear error if missing.

### Language preference sync (small)

So push previews / future features know langs:

- Worker: on login / language change → `PUT /api/worker-app/me/language` storing `workers.preferred_lang` (or prefs table).
- Admin: optional `users.preferred_lang` updated when admin changes `baupass-admin-v2-lang`.

Not required for MVP on-view translation (viewer lang is local), but useful for analytics and future push-body translation.

## Mobile (Flutter)

Files: `mobile/lib/services/chat_repository.dart`, `mobile/lib/features/chat/chat_screen.dart` (existing long-press bottom sheet ~reply/pin/star).

1. On send: include `sourceLang: LocaleController.instance.lang`.
2. After decrypt for display:
   - If `sourceLang == LocaleController.lang` → show `body` only; no “Show original” action.
   - Else → bubble text = translation; track per-message `showingOriginal` flag (default false).
3. Message action sheet: add **Show original** / **Show translation** toggle when a translation exists.
4. Local cache map `messageId → { lang, text }` to avoid re-calling API on scroll.
5. Listen to `LocaleController`: when language changes, clear `showingOriginal` and re-resolve.
6. i18n: `showOriginal`, `showTranslation`, `translated`, `translating`, `translationUnavailable`.

## Admin web (`admin-v2` + chat JS)

1. On send: pass `sourceLang` from `baupass-admin-v2-lang` / `baupass-ui-lang`.
2. Bubble: translation by default when langs differ.
3. Extend `chat-message-menu.js` / `SUPPIXChatMessageMenu` with `showOriginal` / `showTranslation` action (same place as forward/delete).
4. Cache in module Map / `sessionStorage`.
5. Strings in `admin-v2/chat-i18n.js`.

## Same-language path (explicit)

| Sender UI | Viewer UI | Behavior |
|-----------|-----------|----------|
| de | de | original only |
| ar | en | translate AR→EN + show original |
| en | ar | translate EN→AR + show original |
| tr | tr | original only |

No translation for attachments-only / voice / location system messages.

## E2E constraint

- Server never decrypts E2E bodies.
- Translation runs **after** client decrypt, then client POSTs plaintext to translate endpoint (or uses a dedicated ephemeral translate that does not persist).
- Document: company with E2E still gets translation; plaintext briefly hits translate API (same trust model as docs AI).

## Tests

- Unit: skip when langs equal; normalize lang codes; refuse e2e envelopes / `@location|`.
- API: create message with `source_lang`; list returns it.
- Integration (mocked OpenAI): AR→EN returns translation field.
- Flutter widget/unit: bubble shows single line when langs match.

## Out of scope (this iteration)

- Auto speech-to-text translation of voice notes.
- Translating push notification bodies (can follow once `preferred_lang` sync exists).
- DeepL / Google Translate as primary (OpenAI already wired; optional provider later).

## Implementation order

1. Schema + `source_lang` on create/list  
2. Shared `translate_text()` + chat translate routes  
3. Admin chat UI bubbles + send lang  
4. Flutter chat bubbles + send lang + locale rebuild  
5. Tests + feature flag `BAUPASS_CHAT_TRANSLATE=1` (default on when OpenAI configured)

## Acceptance

- DE worker ↔ DE admin: messages unchanged, no translate calls; no “Show original” menu item.  
- AR worker ↔ EN admin: bubble shows translation; long-press → **Show original** reveals source; toggle back works.  
- Existing menu actions (reply, pin, forward, delete, …) remain unchanged.  
- Language switch mid-thread refreshes translations for the new UI lang.  
- Missing OpenAI: chat still works with original text; soft “translation unavailable”.
