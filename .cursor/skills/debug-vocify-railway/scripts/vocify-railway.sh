#!/usr/bin/env bash
# Vocify production Railway helper. Reuses ~/.railway CLI login.
set -euo pipefail

if [ -f "$HOME/.railway/env" ]; then
  # shellcheck disable=SC1090
  source "$HOME/.railway/env"
fi

RAILWAY="${RAILWAY_BIN:-$(command -v railway || true)}"
if [ -z "${RAILWAY}" ] && [ -x "$HOME/.railway/bin/railway" ]; then
  RAILWAY="$HOME/.railway/bin/railway"
fi
if [ -z "${RAILWAY}" ]; then
  echo "railway CLI not found. Install with: bash <(curl -fsSL https://railway.com/install.sh) -y --agents --local" >&2
  exit 1
fi

PROJECT="${VOCIFY_RAILWAY_PROJECT:-4c68b2b8-116f-49fd-9a2e-1db9a4297d03}"
SERVICE="${VOCIFY_RAILWAY_SERVICE:-ac08092e-f71e-4536-bb84-66ec96106813}"
ENVIRONMENT="${VOCIFY_RAILWAY_ENVIRONMENT:-production}"
export RAILWAY_CALLER="${RAILWAY_CALLER:-skill:debug-vocify-railway}"

cmd="${1:-help}"
shift || true

run() {
  "$RAILWAY" "$@" --project "$PROJECT" --environment "$ENVIRONMENT" --service "$SERVICE"
}

case "$cmd" in
  whoami)
    "$RAILWAY" whoami
    ;;
  health)
    curl -sS -w "\nhttp:%{http_code} time:%{time_total}\n" --max-time 15 \
      https://api.getvocify.com/health
    ;;
  deploys|deployments)
    run deployment list --limit "${1:-8}" --json
    ;;
  errors)
    run logs --lines "${1:-200}" --filter "@level:error" --json
    ;;
  logs)
    if [ "$#" -eq 0 ]; then
      run logs --lines 200 --json
    else
      run logs --lines 200 --json "$@"
    fi
    ;;
  vars|variables)
    run variable list --json
    ;;
  status)
    run status --json
    ;;
  help|-h|--help|*)
    cat <<'EOF'
Usage: vocify-railway.sh <command> [args]

  whoami       Show Railway CLI user (no re-login if this works)
  health       GET https://api.getvocify.com/health
  deploys      Recent production deployments (JSON)
  errors       Last 200 error log lines
  logs [args]  Runtime logs (pass extra railway logs flags, e.g. --filter email)
  vars         List service variables (do not paste secrets into chat)
  status       Linked/explicit service status
EOF
    if [ "$cmd" = "help" ] || [ "$cmd" = "-h" ] || [ "$cmd" = "--help" ]; then
      exit 0
    fi
    exit 1
    ;;
esac
