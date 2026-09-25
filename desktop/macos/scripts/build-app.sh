#!/bin/bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
desktop="$(cd "$root/.." && pwd)"
cd "$root"

swift build -c release

mkdir -p "$root/build"
master="$root/build/app-icon-1024.png"
swift "$root/scripts/draw-app-icon.swift" "$desktop/brand/icon-512.png" "$master"

iconset="$root/build/AppIcon.iconset"
rm -rf "$iconset"
mkdir -p "$iconset"
for size in 16 32 128 256 512; do
  sips -z "$size" "$size" "$master" --out "$iconset/icon_${size}x${size}.png" >/dev/null
done
sips -z 32 32 "$master" --out "$iconset/icon_16x16@2x.png" >/dev/null
sips -z 64 64 "$master" --out "$iconset/icon_32x32@2x.png" >/dev/null
sips -z 256 256 "$master" --out "$iconset/icon_128x128@2x.png" >/dev/null
sips -z 512 512 "$master" --out "$iconset/icon_256x256@2x.png" >/dev/null
sips -z 512 512 "$master" --out "$iconset/icon_512x512.png" >/dev/null
cp "$master" "$iconset/icon_512x512@2x.png"
iconutil -c icns "$iconset" -o "$root/build/AppIcon.icns"

app="$root/Vocify.app"
rm -rf "$app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
cp "$root/.build/release/VocifyHost" "$app/Contents/MacOS/VocifyHost"
cp "$root/Sources/VocifyHost/bridge.js" "$app/Contents/Resources/bridge.js"
cp "$root/Info.plist" "$app/Contents/Info.plist"
cp "$root/build/AppIcon.icns" "$app/Contents/Resources/AppIcon.icns"
rsync -a --delete "$desktop/renderer/" "$app/Contents/Resources/renderer/"
rsync -a --delete --exclude '*.test.js' "$desktop/lib/" "$app/Contents/Resources/lib/"
# desktop/lib imports ../../shared/ui, which the page resolves as /shared/ui.
rsync -a --delete --exclude '*.test.js' "$desktop/../shared/ui/" "$app/Contents/Resources/shared/ui/"

codesign --force --deep --sign - --entitlements "$root/VocifyHost.entitlements" "$app"
echo "$app"
