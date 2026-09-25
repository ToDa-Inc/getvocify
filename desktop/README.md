# Vocify Companion

Desktop app for [Vocify](https://github.com/ToDa-Inc/getvocify): Granola-style **system audio + mic**, dashboard UI, tray, always-on-top overlay. Talks to the production API at **https://api.getvocify.com/api/v1**.

## macOS native app (`desktop/macos`)

The shipped **Vocify.app** loads the **same React dashboard** as [app.getvocify.com](https://app.getvocify.com) inside `WKWebView` (sidebar, memos, settings). Native code only handles permissions, ScreenCaptureKit, overlay, and `window.vocifyDesktop`.

```bash
cd desktop/macos && bash scripts/build-app.sh
open Vocify.app
```

**Dev against local Vite:** run `npm run dev` in the repo root, then:

```bash
VOCIFY_WEB_ORIGIN=http://localhost:8080 open Vocify.app/Contents/MacOS/VocifyHost
```

**Fallback** to the bundled vanilla renderer (Electron parity / offline UI work):

```bash
VOCIFY_USE_LOCAL_RENDERER=1 open Vocify.app/Contents/MacOS/VocifyHost
```

## Run on your Mac (Electron)

```bash
git clone https://github.com/ToDa-Inc/getvocify-desktop.git
cd getvocify-desktop
npm install
npm start
```

A window and a menu-bar icon should appear. Log in with the same Vocify account as [app.getvocify.com](https://app.getvocify.com). On Mac, grant **Microphone** and **Screen & System Audio Recording** (that last one is how macOS lets the app hear Zoom/Meet/Teams — it does not capture your screen).

## Logs (login / SaaS)

Requests go through Electron (`[saas]` in the terminal), not the window, so production CORS cannot block them.

- **Main process:** the terminal where you ran `npm start` — look for `[saas] → POST …/auth/login` then `[saas] ← 200`.
- **Renderer:** View → Toggle Developer Tools (or **⌥⌘I**). DevTools also open automatically in unpackaged `npm start`.
- **Network:** DevTools → Network. Login should be `saas:request` IPC, not a failing `auth/login` fetch.

Default API: `https://api.getvocify.com/api/v1` (Advanced on the login screen). Local backend: `http://localhost:8888/api/v1`.

## Installer (.dmg)

```bash
npm run dist:mac
open dist/Vocify-Companion-0.2.0.dmg
```

Or GitHub → Actions → **Mac DMG** → download the artifact. Unsigned: **Right-click → Open**. Grant Microphone + Screen & System Audio Recording (audio only; the screen is not captured).
