#!/usr/bin/env bash
# Vendor the Twilio Voice SDK browser bundle into the Chrome extension.
#
# The extension has no build step: manifest.json loads plain ES modules and
# package-chrome-extension.sh ships raw source. MV3 also forbids remote code.
# So we commit Twilio's own prebuilt UMD bundle, which exposes
# globalThis.Twilio.Device.
set -euo pipefail

VERSION="${1:-2.18.3}"
DEST="chrome-extension/vendor/twilio-voice-${VERSION}.min.js"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

( cd "$TMP" && npm pack "@twilio/voice-sdk@${VERSION}" --silent >/dev/null )
tar -xzf "$TMP/twilio-voice-sdk-${VERSION}.tgz" -C "$TMP"

mkdir -p "$(dirname "$DEST")"
cp "$TMP/package/dist/twilio.min.js" "$DEST"

grep -q "root.Twilio" "$DEST" || { echo "unexpected bundle shape" >&2; exit 1; }
echo "vendored $DEST ($(wc -c <"$DEST") bytes)"
