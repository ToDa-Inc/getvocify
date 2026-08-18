# Vocify Companion

Desktop companion for Vocify. Same cream / beige dashboard language, **You / Them** labels, and CRM handoff — with Granola-style **system-audio loopback**, a **menu-bar tray**, and an **always-on-top live overlay**.

It does **not** join Zoom as a bot. Mic = You. Speakers = Them.

## On your Mac (this is how you actually see the app)

Cloud agents cannot put a window on your laptop. Build and open it locally:

```bash
git checkout cursor/field-extraction-speakers-desktop-a838
cd desktop
npm install
npm start
```

A Vocify-styled window appears, plus a tray icon. Close the window to keep listening from the overlay / tray.

### Mac installer (unsigned .dmg)

On a Mac:

```bash
cd desktop
npm install
npm run icons
npm run dist:mac
```

Open `dist/Vocify Companion-0.2.0.dmg`. Unsigned Gatekeeper: **Right-click → Open**. Grant **Microphone** and **Screen Recording**.

## What you get

| Piece | Behavior |
|-------|----------|
| Main window | Dashboard tokens, Instrument Serif, Listen / Stop & send |
| Overlay | Always-on-top pill while live; Stop; double-click to show main |
| Tray | Open Vocify, Listen, Stop & send, Open dashboard, Quit |
| Loopback | Chromium `audio: 'loopback'` on macOS/Windows; PipeWire/Pulse on Linux |
| Handoff | `POST /memos/upload-transcript` → review in the dashboard |

## Browser fallback

```bash
npm run web
# http://127.0.0.1:3847/renderer/index.html
```

No tray/overlay. Chrome’s share picker instead of silent loopback.

## Permissions

| Platform | Needed |
|----------|--------|
| macOS | Microphone + Screen Recording |
| Windows | Microphone; WASAPI loopback via Chromium |
| Linux | Microphone; `pw-record` / `parec` if Chromium loopback is empty |

## Tests

```bash
cd desktop
npm test
```
