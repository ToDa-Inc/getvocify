#!/usr/bin/env bash
# Vendor the Telnyx WebRTC SDK browser bundle into the Chrome extension.
#
# The extension has no build step: manifest.json loads plain ES modules and
# package-chrome-extension.sh ships raw source. MV3 also forbids remote code.
# So we commit Telnyx's own prebuilt UMD bundle, which exposes
# globalThis.TelnyxWebRTC.TelnyxRTC.
set -euo pipefail
VER="${1:-2.27.10}"
DEST="chrome-extension/vendor/telnyx-webrtc-${VER}.bundle.js"
mkdir -p "$(dirname "$DEST")"
curl -fsSL "https://unpkg.com/@telnyx/webrtc@${VER}/lib/bundle.js" -o "$DEST"
echo "vendored $DEST ($(wc -c <"$DEST") bytes)"
