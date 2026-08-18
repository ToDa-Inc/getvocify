# Vocify Companion

Standalone desktop app for Vocify (Granola-style): **system audio = Them**, **mic = You**, tray + always-on-top overlay, dashboard cream UI, CRM transcript upload.

This folder is the full app. The intended GitHub repo is **[ToDa-Inc/getvocify-desktop](https://github.com/ToDa-Inc/getvocify-desktop)** — create that empty repo, then from getvocify:

```bash
bash desktop/scripts/push-standalone-repo.sh
```

(This agent’s GitHub token cannot create org repos: `403 Resource not accessible by integration`.)

## Why nothing opened last time

The companion is **Electron on the machine that runs `npm start`**. Cursor cloud agents run Linux VMs; that window never appears on your Mac. A `.dmg` also cannot be built on Linux — GitHub Actions on `macos-latest` produces it.

On your Mac:

```bash
git checkout cursor/field-extraction-speakers-desktop-a838
cd desktop
npm install
npm start
```

You should see a Vocify window **and** a menu-bar icon. If the window is behind others, click **Vocify Companion** in the Dock.

## Mac installer (.dmg)

On a Mac, or via **Actions → Companion Mac DMG → Run workflow**:

```bash
cd desktop
npm install
npm run dist:mac
open dist/Vocify-Companion-0.2.0.dmg
```

Unsigned build: **Right-click the app → Open**. Grant **Microphone** and **Screen Recording**.

## Loopback

| Platform | System audio |
|----------|----------------|
| macOS / Windows | Chromium `audio: 'loopback'` |
| Linux | PipeWire / Pulse monitor (Anarlog-style), then Chromium |

Does not join the meeting as a bot.
