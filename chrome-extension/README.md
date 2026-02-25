# Vocify Chrome Extension

Chrome Extension for Vocify that enables voice-to-CRM updates via hotkey.

## Features

- **Hotkey Recording**: Press `Alt+Shift+V` to start/stop recording
- **Context Awareness**: Automatically associates memos with HubSpot deals when on HubSpot pages
- **Universal**: Works from any page, not just HubSpot
- **Visual Feedback**: "REC" badge appears during recording
- **Notifications**: Desktop notifications for processing status

## Development

### Setup

1. **Create Icons** (Required):
   - Open `create-icons.html` in a browser
   - Right-click each canvas and save as:
     - `icons/icon16.png`
     - `icons/icon48.png`
     - `icons/icon128.png`
   - Or create your own icons (16x16, 48x48, 128x128 PNG files)

2. **Load Extension**:
   - Open Chrome and navigate to `chrome://extensions/`
   - Enable "Developer mode" (toggle in top right)
   - Click "Load unpacked"
   - Select the `chrome-extension` folder

### Structure

```
chrome-extension/
├── manifest.json          # Extension configuration
├── background.js         # Service worker (hotkeys, API, polling)
├── offscreen.html        # Offscreen document for audio recording
├── offscreen.js          # MediaRecorder implementation
├── popup/                # Authentication UI
│   ├── index.html
│   ├── popup.js
│   └── styles.css
├── lib/                  # Shared utilities
│   ├── api.js           # API client with token management
│   └── hubspot-parser.js # URL parsing utilities
└── icons/               # Extension icons
```

### API Configuration

The extension uses `http://localhost:8888/api/v1` by default. To change this for production:

1. Set `api_base` in chrome.storage.local (e.g. `chrome.storage.local.set({ api_base: 'https://api.getvocify.com/api/v1' })`)
2. Or update `DEFAULT_API_BASE` in `lib/api.js`
2. Update `host_permissions` in `manifest.json`

### Testing

1. Load the extension in Chrome
2. Click the extension icon to log in
3. Navigate to a HubSpot deal page (optional)
4. Press `Alt+Shift+V` to start recording
5. Speak your memo
6. Press `Alt+Shift+V` again to stop
7. Wait for notification that processing is complete

## Production Build

For production deployment:

1. Set `api_base` in chrome.storage.local or update `DEFAULT_API_BASE` in `lib/api.js` to production URL
2. Update `host_permissions` in `manifest.json`
3. Create proper icons (16x16, 48x48, 128x128)
4. Package extension: `zip -r vocify-extension.zip chrome-extension/`
5. Submit to Chrome Web Store

## Architecture

- **Manifest V3**: Uses service worker and offscreen document
- **Token Management**: Automatic refresh on 401 errors
- **Error Handling**: Graceful fallbacks and user notifications
- **Scalable**: Modular structure for easy extension
