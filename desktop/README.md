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

## Tests (no Electron UI)

```bash
cd desktop
npm test
```
