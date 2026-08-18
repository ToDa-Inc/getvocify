# Vocify Companion

A tiny desktop window that **emulates the Vocify listen flow** the way Granola does: it hears **system audio** (Zoom / Meet / Teams / the call playing on your machine) as the prospect, and your **microphone** as You. When you stop, it uploads the transcript into the same SaaS review pipeline.

This does **not** join the meeting as a bot. It captures loopback audio on the machine.

## Why this exists

The Chrome extension can capture a **tab**. Desktop meeting apps have no tab. Companion uses Chromium `audio: 'loopback'` (Electron `setDisplayMediaRequestHandler`) so the meeting’s speakers become the prospect channel.

## Run

```bash
cd desktop
npm install
npm start
```

On Linux cloud VMs / containers (no GPU, no D-Bus) `npm start` now disables the GPU and Chromium sandbox so the window can open. D-Bus `Unknown address type` lines are harmless.

If Electron still cannot open a window (no display), use the same UI in a browser:

```bash
cd desktop
npm run web
# open http://127.0.0.1:3847/renderer/index.html
```

Browser mode uses the Chrome share-picker for tab/window audio instead of silent loopback.

Log in with your Vocify email/password. Default API is `https://api.getvocify.com/api/v1`. For local backend, set API base to `http://localhost:8888/api/v1`.

1. Start the meeting and make sure you can hear the other person.
2. Click **Listen**. macOS will ask for Screen Recording (required for system audio).
3. Speak on your mic. You/Them labels appear live.
4. **Stop & send** creates a memo (`meeting_transcript`) — review it in the dashboard with the same speaker labels and field mapping.

## Permissions

| Platform | Needed |
|----------|--------|
| macOS | Microphone + Screen Recording (System Settings → Privacy) |
| Windows | Microphone; loopback via Chromium |
| Linux | Microphone; PipeWire/Pulse. Loopback may require sharing a window that has audio |

If system audio has no track, Companion tells you instead of uploading silence.

## Linux troubleshooting

| Log line | Meaning |
|----------|---------|
| `Failed to connect to the bus: Could not parse server address` | No D-Bus session. Harmless; ignored. |
| `Exiting GPU process due to errors during initialization` | No usable GPU. `npm start` now passes `--disable-gpu` so this should not kill the app. |
| Window never appears | No `DISPLAY` / Wayland. Run `npm run web` instead. |

## Tests (no Electron UI)

```bash
cd desktop
npm test
```
