#!/usr/bin/env python3
"""GET-only vendor HTTP for Vocify debug. Keys from backend/.env or repo .env."""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
ENV_CANDIDATES = [ROOT / "backend" / ".env", ROOT / ".env"]


def _load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    for path in ENV_CANDIDATES:
        if not path.is_file():
            continue
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            out.setdefault(key.strip(), value)
    return out


def _need(env: dict[str, str], *names: str) -> dict[str, str]:
    missing = [n for n in names if not env.get(n)]
    if missing:
        print(f"missing env (set in backend/.env or Railway): {', '.join(missing)}", file=sys.stderr)
        sys.exit(2)
    return {n: env[n] for n in names}


def _request(url: str, headers: dict[str, str], method: str) -> None:
    headers = {"User-Agent": "vocify-debug/1.0", **headers}
    req = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            print(f"http:{resp.status}")
            print(body[:8000])
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"http:{exc.code}", file=sys.stderr)
        print(body[:2000], file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Vocify vendor HTTP (GET by default)")
    parser.add_argument("vendor", choices=("resend", "stripe", "twilio", "telnyx", "unipile", "deepgram", "openrouter"))
    parser.add_argument("method", default="GET", nargs="?", help="HTTP method")
    parser.add_argument("path", help="Path including query, e.g. /emails")
    parser.add_argument("--write", action="store_true", help="Allow non-GET (ask the user first)")
    args = parser.parse_args()
    method = args.method.upper()
    if method != "GET" and not args.write:
        print("non-GET requires --write after the user confirms", file=sys.stderr)
        sys.exit(2)

    env = {**os.environ, **_load_env()}
    path = args.path if args.path.startswith("/") else f"/{args.path}"

    if args.vendor == "resend":
        keys = _need(env, "RESEND_API_KEY")
        url = f"https://api.resend.com{path}"
        headers = {
            "Authorization": f"Bearer {keys['RESEND_API_KEY']}",
            "Accept": "application/json",
            "User-Agent": "vocify-debug/1.0",
        }
    elif args.vendor == "stripe":
        keys = _need(env, "STRIPE_SECRET_KEY")
        url = f"https://api.stripe.com{path}"
        headers = {"Authorization": f"Bearer {keys['STRIPE_SECRET_KEY']}", "Accept": "application/json"}
    elif args.vendor == "twilio":
        keys = _need(env, "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN")
        sid = keys["TWILIO_ACCOUNT_SID"]
        token = keys["TWILIO_AUTH_TOKEN"]
        if not path.startswith("/2010-04-01/"):
            path = f"/2010-04-01/Accounts/{sid}{path}"
        url = f"https://api.twilio.com{path}"
        headers = {"Accept": "application/json"}
        password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        password_mgr.add_password(None, "https://api.twilio.com", sid, token)
        opener = urllib.request.build_opener(urllib.request.HTTPBasicAuthHandler(password_mgr))
        urllib.request.install_opener(opener)
    elif args.vendor == "telnyx":
        keys = _need(env, "TELNYX_API_KEY")
        url = f"https://api.telnyx.com{path}"
        headers = {"Authorization": f"Bearer {keys['TELNYX_API_KEY']}", "Accept": "application/json"}
    elif args.vendor == "unipile":
        keys = _need(env, "UNIPILE_API_KEY")
        base = env.get("UNIPILE_BASE_URL", "https://api23.unipile.com:15349").rstrip("/")
        url = f"{base}{path}"
        headers = {"X-API-KEY": keys["UNIPILE_API_KEY"], "Accept": "application/json"}
    elif args.vendor == "deepgram":
        keys = _need(env, "DEEPGRAM_API_KEY")
        url = f"https://api.deepgram.com{path}"
        headers = {"Authorization": f"Token {keys['DEEPGRAM_API_KEY']}", "Accept": "application/json"}
    else:
        keys = _need(env, "OPENROUTER_API_KEY")
        url = f"https://openrouter.ai{path}"
        headers = {"Authorization": f"Bearer {keys['OPENROUTER_API_KEY']}", "Accept": "application/json"}

    _request(url, headers, method)


if __name__ == "__main__":
    main()
