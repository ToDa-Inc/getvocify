#!/usr/bin/env python3
"""Staff admin API via MASTER_KEY. Never prints the key or session tokens."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
ENV_CANDIDATES = [ROOT / "backend" / ".env", ROOT / ".env"]
DEFAULT_BASE = "https://api.getvocify.com"


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
            out.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return {**os.environ, **out}


def _master() -> str:
    env = _load_env()
    key = (env.get("MASTER_KEY") or "").strip()
    if not key:
        print("MASTER_KEY missing in backend/.env or Railway env", file=sys.stderr)
        sys.exit(2)
    return key


def _base() -> str:
    return os.environ.get("VOCIFY_API_BASE", DEFAULT_BASE).rstrip("/")


def _request(method: str, url: str, headers: dict[str, str], body: bytes | None = None) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        data=body,
        headers={"User-Agent": "vocify-debug/1.0", "Accept": "application/json", **headers},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def _admin(method: str, path: str, query: dict[str, str] | None = None, body: dict | None = None) -> None:
    url = f"{_base()}/api/v1/admin{path}"
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v})
    payload = json.dumps(body).encode() if body is not None else None
    headers = {"X-Master-Key": _master()}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    status, text = _request(method, url, headers, payload)
    print(f"http:{status}")
    print(_redact(text)[:8000])
    if status >= 400:
        sys.exit(1)


def _redact(text: str) -> str:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text
    return json.dumps(_scrub(data), indent=2)


def _scrub(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            lowered = key.lower()
            if lowered in {"access_token", "refresh_token", "token", "authorization"}:
                out[key] = "[redacted]"
            else:
                out[key] = _scrub(item)
        return out
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Vocify admin API (master key)")
    parser.add_argument(
        "command",
        choices=("runtime", "accounts", "account", "companies", "company", "stuck-memos", "as-user"),
    )
    parser.add_argument("target", nargs="?", help="user_id, company_id, or as-user path")
    parser.add_argument("rest", nargs="*", help="as-user: METHOD PATH")
    parser.add_argument("--search", default="")
    parser.add_argument("--limit", default="20")
    parser.add_argument("--write", action="store_true", help="Allow impersonate / as-user")
    args = parser.parse_args()

    if args.command == "runtime":
        _admin("GET", "/runtime")
    elif args.command == "accounts":
        _admin("GET", "/accounts", {"search": args.search, "limit": args.limit})
    elif args.command == "account":
        if not args.target:
            print("account requires user_id", file=sys.stderr)
            sys.exit(2)
        _admin("GET", f"/accounts/{args.target}")
    elif args.command == "companies":
        _admin("GET", "/companies", {"search": args.search, "limit": args.limit})
    elif args.command == "company":
        if not args.target:
            print("company requires company_id", file=sys.stderr)
            sys.exit(2)
        _admin("GET", f"/companies/{args.target}")
    elif args.command == "stuck-memos":
        _admin("GET", "/stuck-memos")
    else:
        if not args.write:
            print("as-user mints a real session; pass --write after the user confirms", file=sys.stderr)
            sys.exit(2)
        if not args.target or len(args.rest) < 2:
            print("usage: vocify-admin.sh as-user <user_id> GET /api/v1/auth/me --write", file=sys.stderr)
            sys.exit(2)
        method, path = args.rest[0].upper(), args.rest[1]
        if method != "GET":
            print("as-user is GET-only", file=sys.stderr)
            sys.exit(2)
        status, text = _request(
            "POST",
            f"{_base()}/api/v1/admin/accounts/{args.target}/impersonate",
            {"X-Master-Key": _master()},
        )
        if status >= 400:
            print(f"http:{status}", file=sys.stderr)
            print(_redact(text)[:2000], file=sys.stderr)
            sys.exit(1)
        minted = json.loads(text)
        token = minted.get("access_token")
        if not token:
            print("impersonate returned no access_token", file=sys.stderr)
            sys.exit(1)
        user = (minted.get("user") or {}).get("email") or args.target
        print(f"impersonated:{user}")
        url = path if path.startswith("http") else f"{_base()}{path}"
        status, text = _request("GET", url, {"Authorization": f"Bearer {token}"})
        print(f"http:{status}")
        print(_redact(text)[:8000])
        if status >= 400:
            sys.exit(1)


if __name__ == "__main__":
    main()
