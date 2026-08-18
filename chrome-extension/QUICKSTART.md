# Quick Start Guide

## Prerequisites

1. Backend API running at `http://localhost:8888`
2. Chrome browser (latest version)

## Setup Steps

### 1. Create Icons

The logo asset is already included in `icons/logo_transparent.png`. To generate the required extension icons:
- Open `create-icons.html` in your browser and save the three canvas images as:
- `icons/icon16.png`
- `icons/icon48.png`  
- `icons/icon128.png`

### 2. Load Extension

1. Open Chrome
2. Navigate to `chrome://extensions/`
3. Enable "Developer mode" (top right toggle)
4. Click "Load unpacked"
5. Select the `chrome-extension` folder

### 3. Authenticate

1. Click the Vocify extension icon in Chrome toolbar
2. Log in with your Vocify credentials
3. You should see "Ready to record" screen

### 4. Test Recording

1. Navigate to any webpage (or HubSpot deal page)
2. Press `Alt+Shift+V` to start recording
3. Speak your memo (e.g., "Met with Sarah Chen at Acme Corp. Deal value is 50k.")
4. Press `Alt+Shift+V` again to stop
5. Wait for notification: "Processing your voice memo..."
6. After processing, you'll get: "Ready for Review" or "CRM Updated"

## Troubleshooting

### "Login Required" notification
- Click extension icon and log in through popup

### "Failed to start recording"
- Check microphone permissions in Chrome settings
- Go to `chrome://settings/content/microphone`
- Ensure Vocify extension has microphone access

### "Upload Failed" or "Authentication Required"
- Token may have expired
- Click extension icon and log in again

### Extension not responding
- Check Chrome console: `chrome://extensions/` → Click "service worker" link
- Look for errors in the console

## Production Configuration

Load unpacked already uses localhost. A Chrome Web Store build already uses `https://api.getvocify.com`. Do not hardcode `API_BASE` before shipping.

If traffic still hits production while testing locally, reload the unpacked folder, or clear an override:

```js
chrome.storage.local.remove('api_base')
```
