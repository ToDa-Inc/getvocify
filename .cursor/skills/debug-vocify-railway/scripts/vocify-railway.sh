#!/usr/bin/env bash
# Vocify Railway helper (production + staging). Reuses ~/.railway CLI login.
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
export RAILWAY_CALLER="${RAILWAY_CALLER:-skill:debug-vocify-railway}"

ENV_IN="${VOCIFY_RAILWAY_ENVIRONMENT:-production}"
while [ $# -gt 0 ]; do
  case "$1" in
    --env|-e)
      ENV_IN="${2:-}"
      shift 2
      ;;
    --env=*|-e=*)
      ENV_IN="${1#*=}"
      shift
      ;;
    *)
      break
      ;;
  esac
done

case "$ENV_IN" in
  production|prod|72257ae8-4260-4cb4-aaa6-9e5eb083f09b)
    ENVIRONMENT="production"
    ENVIRONMENT_ID="72257ae8-4260-4cb4-aaa6-9e5eb083f09b"
    HEALTH_URL="https://api.getvocify.com/health"
    ;;
  staging|stage|2b38e5b7-ebed-43f8-88e4-baab117a144c)
    ENVIRONMENT="staging"
    ENVIRONMENT_ID="2b38e5b7-ebed-43f8-88e4-baab117a144c"
    HEALTH_URL="https://getvocify-staging.up.railway.app/health"
    ;;
  *)
    echo "vocify-railway: unknown env '$ENV_IN' (use production|staging)" >&2
    exit 2
    ;;
esac

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
    echo "env:$ENVIRONMENT health:$HEALTH_URL" >&2
    curl -sS -w "\nhttp:%{http_code} time:%{time_total}\n" --max-time 15 \
      "$HEALTH_URL"
    ;;
  deploys|deployments)
    echo "env:$ENVIRONMENT id:$ENVIRONMENT_ID" >&2
    run deployment list --limit "${1:-8}" --json
    ;;
  errors)
    echo "env:$ENVIRONMENT" >&2
    run logs --lines "${1:-200}" --filter "@level:error" --json
    ;;
  logs)
    echo "env:$ENVIRONMENT" >&2
    if [ "$#" -eq 0 ]; then
      run logs --lines 200 --json
    else
      run logs --lines 200 --json "$@"
    fi
    ;;
  vars|variables)
    echo "env:$ENVIRONMENT" >&2
    run variable list --json
    ;;
  status)
    echo "env:$ENVIRONMENT id:$ENVIRONMENT_ID" >&2
    run status --json
    ;;
  help|-h|--help|*)
    cat <<'EOF'
Usage: vocify-railway.sh [--env production|staging] <command> [args]

  Default env is production. Staging: --env staging  (or VOCIFY_RAILWAY_ENVIRONMENT=staging)

  whoami       Show Railway CLI user (no re-login if this works)
  health       GET env health URL
  deploys      Recent deployments for that env (JSON)
  errors       Last 200 error log lines
  logs [args]  Runtime logs (pass extra railway logs flags, e.g. --filter email)
  vars         List service variables (do not paste secrets into chat)
  status       Linked/explicit service status

Envs:
  production  72257ae8-4260-4cb4-aaa6-9e5eb083f09b  https://api.getvocify.com/health
  staging     2b38e5b7-ebed-43f8-88e4-baab117a144c  https://getvocify-staging.up.railway.app/health
EOF
    if [ "$cmd" = "help" ] || [ "$cmd" = "-h" ] || [ "$cmd" = "--help" ]; then
      exit 0
    fi
    exit 1
    ;;
esac
