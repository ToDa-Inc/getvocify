#!/bin/bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
desktop="$(cd "$root/.." && pwd)"
app="$root/Vocify.app"
bg="$desktop/build/dmg-background.png"
logo="$desktop/brand/icon-512.png"

if [[ ! -d "$app" ]]; then
  echo "Missing $app — run scripts/build-app.sh first." >&2
  exit 1
fi

if [[ ! -f "$bg" ]]; then
  draw="$root/scripts/draw-dmg-background.swift"
  if [[ ! -f "$draw" ]]; then
    echo "Missing $bg — add desktop/build/dmg-background.png or commit $draw to generate it." >&2
    exit 1
  fi
  if [[ ! -f "$logo" ]]; then
    echo "Missing logo $logo — cannot generate DMG background." >&2
    exit 1
  fi
  mkdir -p "$(dirname "$bg")"
  swift "$draw" "$logo" "$bg"
fi

version="$(/usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "$root/Info.plist")"
volname="Vocify"
mkdir -p "$desktop/dist"
dmg="$desktop/dist/Vocify-${version}.dmg"
rm -f "$dmg"

stage="$(mktemp -d)"
rw="$(mktemp -t vocify-rw).dmg"
device=""
trap 'rm -rf "$stage"; rm -f "$rw"' EXIT

cp -R "$app" "$stage/Vocify.app"
ln -sf /Applications "$stage/Applications"
mkdir -p "$stage/.background"
cp "$bg" "$stage/.background/background.png"

emit_srcfolder_fallback() {
  local reason="$1"
  rm -f "$rw" "$dmg"
  if [[ -n "${device:-}" ]]; then
    hdiutil detach "$device" >/dev/null 2>&1 || hdiutil detach "$device" -force >/dev/null 2>&1 || true
    device=""
  fi
  hdiutil create -volname "$volname" -srcfolder "$stage" -ov -format UDZO "$dmg" >/dev/null
  echo "packaging_path=srcfolder-fallback" >&2
  echo "finder_layout_applied=no" >&2
  echo "$reason" >&2
  echo "$dmg"
}

hdiutil create -srcfolder "$stage" -volname "$volname" -fs HFS+ -format UDRW -ov "$rw" >/dev/null

attach_out=""
attach_ok=0
if attach_out="$(hdiutil attach -readwrite -noverify -noautoopen "$rw" 2>&1)"; then
  attach_ok=1
fi

if [[ "$attach_ok" -ne 1 ]]; then
  if echo "$attach_out" | grep -qi "Operation not permitted"; then
    emit_srcfolder_fallback "Finder layout skipped (hdiutil attach not permitted in this environment)."
    exit 0
  fi
  echo "$attach_out" >&2
  exit 1
fi

mount_point="$(echo "$attach_out" | awk '/\/Volumes\// {print $NF; exit}')"
device="$(echo "$attach_out" | awk '/\/Volumes\// {print $1; exit}')"

if [[ -z "${mount_point:-}" || -z "${device:-}" ]]; then
  echo "hdiutil attach succeeded but mount point was not parsed." >&2
  echo "$attach_out" >&2
  exit 1
fi

if osascript <<EOF
with timeout of 120 seconds
  tell application "Finder"
    tell disk "$volname"
      open
      set current view of container window to icon view
      set toolbar visible of container window to false
      set statusbar visible of container window to false
      set bounds of container window to {100, 100, 640, 480}
      tell icon view options of container window
        set arrangement to not arranged
        set icon size to 96
        set background picture to file ".background:background.png"
      end tell
      set position of item "Vocify.app" of container window to {140, 190}
      set position of item "Applications" of container window to {400, 190}
      close
      open
      update without registering applications
      delay 2
    end tell
  end tell
end timeout
EOF
then
  sync "$mount_point"
  hdiutil detach "$device" >/dev/null
  device=""
  hdiutil convert "$rw" -format UDZO -imagekey zlib-level=9 -o "$dmg" >/dev/null
  rm -f "$rw"
  echo "packaging_path=finder-branded" >&2
  echo "finder_layout_applied=yes" >&2
  echo "$dmg"
  exit 0
fi

emit_srcfolder_fallback "Finder layout AppleScript failed — produced unbranded DMG via srcfolder (run from Terminal.app with Automation access to Finder for a branded layout)."
exit 0
