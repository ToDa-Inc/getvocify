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
  mkdir -p "$(dirname "$bg")"
  draw="$root/scripts/draw-dmg-background.swift"
  if [[ ! -f "$draw" ]]; then
    echo "Missing $bg and $draw — cannot generate DMG background." >&2
    exit 1
  fi
  swift "$draw" "$logo" "$bg"
fi

version="$(/usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "$root/Info.plist")"
volname="Vocify"
mkdir -p "$desktop/dist"
dmg="$desktop/dist/Vocify-${version}.dmg"
rm -f "$dmg"

stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT

cp -R "$app" "$stage/Vocify.app"
ln -sf /Applications "$stage/Applications"
mkdir -p "$stage/.background"
cp "$bg" "$stage/.background/background.png"

packaging_path="finder-branded"
rw="$(mktemp -t vocify-rw).dmg"
trap 'rm -rf "$stage"; rm -f "$rw"' EXIT

hdiutil create -srcfolder "$stage" -volname "$volname" -fs HFS+ -format UDRW -ov "$rw" >/dev/null

attach_out=""
attach_ok=0
if attach_out="$(hdiutil attach -readwrite -noverify -noautoopen "$rw" 2>&1)"; then
  attach_ok=1
fi

if [[ "$attach_ok" -eq 1 ]]; then
  mount_point="$(echo "$attach_out" | awk '/\/Volumes\// {print $NF; exit}')"
  device="$(echo "$attach_out" | awk '/\/Volumes\// {print $1; exit}')"

  if [[ -n "${mount_point:-}" && -n "${device:-}" ]]; then
    layout_applied=no
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
      update without registering applications
    end tell
  end tell
end timeout
EOF
    then
      layout_applied=yes
    else
      echo "Finder layout AppleScript failed (run from Terminal.app with Automation access to Finder)." >&2
    fi
    hdiutil detach "$device" >/dev/null 2>&1 || hdiutil detach "$device" -force >/dev/null 2>&1 || true
    hdiutil convert "$rw" -format UDZO -imagekey zlib-level=9 -o "$dmg" >/dev/null
    rm -f "$rw"
    echo "packaging_path=$packaging_path" >&2
    echo "finder_layout_applied=$layout_applied" >&2
    echo "$dmg"
    exit 0
  fi
fi

if echo "$attach_out" | grep -qi "Operation not permitted"; then
  packaging_path="srcfolder-fallback"
else
  echo "$attach_out" >&2
  exit 1
fi

rm -f "$rw"
hdiutil create -volname "$volname" -srcfolder "$stage" -ov -format UDZO "$dmg" >/dev/null
echo "packaging_path=$packaging_path" >&2
echo "Finder icon layout skipped (hdiutil attach not permitted in this environment)." >&2
echo "$dmg"
