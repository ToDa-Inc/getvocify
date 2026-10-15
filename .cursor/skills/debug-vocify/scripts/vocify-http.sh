#!/usr/bin/env python3
"""GET-only vendor HTTP for Vocify debug. Keys from backend/.env or repo .env."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

def _vocify_root() -> Path:
    for key in ("VOCIFY_REPO", "GETVOCIFY_REPO"):
        if os.environ.get(key):
            return Path(os.environ[key]).expanduser().resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "backend" / "app").is_dir():
            return parent
    for candidate in (
        Path.home() / "getvocify",
        Path.home() / "Projects" / "getvocify",
        Path.home() / "Developer" / "getvocify",
    ):
        if (candidate / "backend" / "app").is_dir():
            return candidate.resolve()
    return here.parents[4]


ROOT = _vocify_root()
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


# One reply is capped so a vendor list cannot flood the agent's context. A cut JSON body is not valid JSON,
# so past the cap the full body is saved to a file and what is printed says so (never a silent cut).
STDOUT_LIMIT = 8000
ERROR_LIMIT = 2000


def _pick(data, fields: list[str]):
    """Keep only `fields` of every item of every list of objects (top level or one key down); scalars stay."""
    def keep(item):
        return {k: item[k] for k in fields if k in item} if isinstance(item, dict) else item

    if isinstance(data, list):
        return [keep(item) for item in data]
    if isinstance(data, dict):
        return {k: ([keep(i) for i in v] if isinstance(v, list) else v) for k, v in data.items()}
    return data


def _summary(data) -> str:
    """Shape of a JSON body: each top-level key with its type and size."""
    if isinstance(data, list):
        return f"list[{len(data)}]"
    if not isinstance(data, dict):
        return type(data).__name__
    parts = []
    for key, value in data.items():
        if isinstance(value, list):
            first = value[0] if value and isinstance(value[0], dict) else None
            inner = f" of {{{', '.join(list(first)[:12])}}}" if first else ""
            parts.append(f"{key}: list[{len(value)}]{inner}")
        elif isinstance(value, dict):
            parts.append(f"{key}: object")
        else:
            parts.append(f"{key}: {str(value)[:60]}")
    return "\n".join(parts)


def _save(body: str) -> str:
    fd, path = tempfile.mkstemp(prefix=f"vocify-http-{int(time.time())}-", suffix=".json")
    with os.fdopen(fd, "w") as handle:  # mkstemp creates it 0600
        handle.write(body)
    return path


def _emit(body: str, *, limit: int, full: bool, pick: list[str], out) -> None:
    try:
        data = json.loads(body)
    except ValueError:
        data = None
    shown = json.dumps(_pick(data, pick), ensure_ascii=False, separators=(",", ":")) if pick and data is not None else body
    if full or len(shown) <= limit:
        print(shown, file=out)
        return
    path = _save(body)
    notice = f"# not shown whole: {len(shown)} chars, cap {limit}. Full body saved to {path} (re-run with --full, or --pick field,field)"
    if data is not None:
        print(notice, file=out)
        print(_summary(data), file=out)
    else:
        print(shown[:limit], file=out)
        print(notice, file=out)


def _request(url: str, headers: dict[str, str], method: str, *, full: bool, pick: list[str]) -> None:
    headers = {"User-Agent": "vocify-debug/1.0", **headers}
    req = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            print(f"http:{resp.status}")
            _emit(body, limit=STDOUT_LIMIT, full=full, pick=pick, out=sys.stdout)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"http:{exc.code}", file=sys.stderr)
        _emit(body, limit=ERROR_LIMIT, full=full, pick=[], out=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Vocify vendor HTTP (GET by default)")
    parser.add_argument("vendor", choices=("resend", "stripe", "twilio", "telnyx", "unipile", "deepgram", "openrouter"))
    parser.add_argument("method", default="GET", nargs="?", help="HTTP method")
    parser.add_argument("path", help="Path including query, e.g. /emails")
    parser.add_argument("--write", action="store_true", help="Allow non-GET (ask the user first)")
    parser.add_argument("--pick", default="", help="Comma-separated fields to keep of each list item (e.g. sid,status,to)")
    parser.add_argument("--full", action="store_true", help=f"Print the whole body instead of capping at {STDOUT_LIMIT} chars")
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

    _request(url, headers, method, full=args.full, pick=[f.strip() for f in args.pick.split(",") if f.strip()])


if __name__ == "__main__":
    main()
