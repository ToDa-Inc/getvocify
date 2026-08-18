#!/usr/bin/env bash
# Publish desktop/ as a standalone git tree (create ToDa-Inc/getvocify-desktop first).
# Cursor's GitHub App can push this split to getvocify; pushing to getvocify-desktop
# requires the App to be granted access on that repo (org Settings → GitHub Apps → Cursor).
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
REMOTE="${1:-https://github.com/ToDa-Inc/getvocify-desktop.git}"
EXPORT_BRANCH="${EXPORT_BRANCH:-cursor/desktop-export-a838}"
SPLIT_BRANCH="${SPLIT_BRANCH:-getvocify-desktop-split}"
cd "$ROOT"

git branch -D "$SPLIT_BRANCH" >/dev/null 2>&1 || true
git subtree split --prefix=desktop -b "$SPLIT_BRANCH"
git push -u origin "$SPLIT_BRANCH:$EXPORT_BRANCH"

if git push -f "$REMOTE" "$SPLIT_BRANCH:main"; then
  echo "Pushed desktop/ to $REMOTE (branch main)."
else
  cat <<EOF
Could not push to $REMOTE (this token has no write access on getvocify-desktop).

Grant Cursor GitHub App access: org Settings → GitHub Apps → Cursor →
Repository access → add getvocify-desktop → Save, then re-run this script.

Or from a machine logged in as a ToDa-Inc admin:
  git clone --branch $EXPORT_BRANCH --single-branch https://github.com/ToDa-Inc/getvocify.git getvocify-desktop
  cd getvocify-desktop
  git checkout -B main
  git remote set-url origin $REMOTE
  git push -u origin main
EOF
  exit 1
fi
