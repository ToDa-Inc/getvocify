# Vocify Companion

A tiny desktop window that **emulates the Vocify listen flow** the way Granola does: it hears **system audio** (Zoom / Meet / Teams / the call playing on your machine) as the prospect, and your **microphone** as You. When you stop, it uploads the transcript into the same SaaS review pipeline.

This does **not** join the meeting as a bot. It captures loopback audio on the machine.

Capture follows the same split as [Anarlog](https://github.com/fastrepl/anarlog) (MIT, Granola-style): **microphone = You**, **system audio = Them**. Vocify keeps the Electron shell and existing SaaS STT/CRM pipeline; it does not vendor Anarlog’s Tauri/Rust app.

| Platform | System audio |
|----------|----------------|
| macOS / Windows | Chromium `audio: 'loopback'` (Screen Recording / WASAPI) |
| Linux | PipeWire `stream.capture.sink`, else PulseAudio `<default-sink>.monitor` via `pw-record` / `parec` / `ffmpeg`, then Chromium share-picker |

## Why this exists

The Chrome extension can capture a **tab**. Desktop meeting apps have no tab. Companion captures **system audio** the way Granola / [Anarlog](https://github.com/fastrepl/anarlog) do: native speaker loopback on Linux, Chromium `audio: 'loopback'` on macOS and Windows.

## Run

```bash
cd desktop
npm install
npm start
```

On Linux cloud VMs / containers (no GPU, no D-Bus) `npm start` disables the GPU and Chromium sandbox and starts a session bus so the window can open.

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
| `Failed to connect to the bus: Could not parse server address` | No D-Bus session. Harmless leftover Chromium noise; the app still runs. |
| `Exiting GPU process due to errors during initialization` | No usable GPU. `npm start` passes `--disable-gpu` so this should not kill the app. |
| Window never appears | No `DISPLAY` / Wayland. Run `npm run web` instead. |

## Tests (no Electron UI)

```bash
cd desktop
npm test
```
