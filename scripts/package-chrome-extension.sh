#!/usr/bin/env bash
# Build a Chrome Web Store upload zip from chrome-extension/.
# Excludes dev docs, tests, and build artifacts. Manifest stays at zip root.
# Output goes to chrome-extension/release/ (NOT repo dist/, which is the Vite app build).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/chrome-extension"
OUT_DIR="$ROOT/chrome-extension/release"
STAGE="$(mktemp -d)"

cleanup() {
  rm -rf "$STAGE"
}
trap cleanup EXIT

VERSION="$(python3 -c "import json; print(json.load(open('$SRC/manifest.json'))['version'])")"
OUT="$OUT_DIR/vocify-chrome-extension-${VERSION}.zip"

mkdir -p "$OUT_DIR"

rsync -a \
  --exclude '.gitignore' \
  --exclude 'release/' \
  --exclude '*.test.js' \
  --exclude 'README.md' \
  --exclude 'QUICKSTART.md' \
  --exclude 'RELOAD_INSTRUCTIONS.md' \
  --exclude 'create-icons.html' \
  --exclude 'icons/README.md' \
  --exclude 'icons/icon.svg' \
  --exclude '*.zip' \
  --exclude '*.crx' \
  --exclude '*.pem' \
  --exclude '.DS_Store' \
  "$SRC/" "$STAGE/"

(
  cd "$STAGE"
  zip -r -q "$OUT" . -x '*.DS_Store'
)

echo "Packaged: $OUT"
echo "Version:  $VERSION"
echo "Files:    $(unzip -l "$OUT" | tail -1)"
