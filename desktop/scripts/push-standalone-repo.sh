#!/usr/bin/env bash
# Push desktop/ to a standalone GitHub repo (create ToDa-Inc/getvocify-desktop first).
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
REMOTE="${1:-https://github.com/ToDa-Inc/getvocify-desktop.git}"
cd "$ROOT"
git subtree split --prefix=desktop -b getvocify-desktop-split
git push -f "$REMOTE" getvocify-desktop-split:main
echo "Pushed desktop/ to $REMOTE (branch main)."
