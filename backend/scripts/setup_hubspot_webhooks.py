#!/usr/bin/env python3
"""
Register (or update) HubSpot app webhook target URL + subscriptions.

HubSpot only supports ONE targetUrl per app at a time.
Use --env=dev  → ngrok tunnel (auto-detected or set HUBSPOT_WEBHOOK_TARGET_URL)
Use --env=prod → https://api.getvocify.com/webhooks/hubspot

Requires env:
  HUBSPOT_APP_ID            — numeric app ID (HubSpot developer account → app overview)
  HUBSPOT_DEVELOPER_API_KEY — developer API key (HubSpot developer account → app → Auth)

Optional:
  HUBSPOT_WEBHOOK_TARGET_URL — override target URL (any env)
  HUBSPOT_MAX_CONCURRENT     — default 10
"""
import argparse
import json
import os
import sys
import urllib.request

import httpx

BASE = "https://api.hubapi.com"
PROD_URL = "https://api.getvocify.com/webhooks/hubspot"

SUBSCRIPTIONS = [
    # Fires when a call object is created (catches recordings set at creation time)
    # objectTypeId 0-48 = CALL (generic format, replaces legacy engagement.creation)
    {"eventType": "object.creation", "objectTypeId": "0-48", "active": True},
    # Fires when hs_call_recording_url is set/updated on a call object
    {
        "eventType": "object.propertyChange",
        "objectTypeId": "0-48",
        "propertyName": "hs_call_recording_url",
        "active": True,
    },
]


def _ngrok_url() -> str | None:
    try:
        with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=2) as r:
            d = json.load(r)
    except OSError:
        return None
    for t in d.get("tunnels") or []:
        u = str(t.get("public_url") or "")
        if u.startswith("https://"):
            return u + "/webhooks/hubspot"
    return None


def _get_existing_subscriptions(client, app_id, headers, auth_params) -> list[dict]:
    r = client.get(f"{BASE}/webhooks/v3/{app_id}/subscriptions", headers=headers, params=auth_params)
    if r.status_code == 200:
        return r.json().get("results") or []
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Register HubSpot webhook target + subscriptions.")
    parser.add_argument(
        "--env",
        choices=["dev", "prod"],
        default="dev",
        help="dev = ngrok tunnel (local testing), prod = https://api.getvocify.com",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be sent without calling HubSpot.",
    )
    args = parser.parse_args()

    app_id = os.environ.get("HUBSPOT_APP_ID", "").strip()
    key = os.environ.get("HUBSPOT_DEVELOPER_API_KEY", "").strip()
    override = os.environ.get("HUBSPOT_WEBHOOK_TARGET_URL", "").strip()

    # Resolve target URL
    if override:
        target = override
    elif args.env == "prod":
        target = PROD_URL
    else:
        target = _ngrok_url() or ""

    if not target:
        print(
            "ERROR: No ngrok tunnel detected. Run `make ngrok` in another terminal first,\n"
            "       or set HUBSPOT_WEBHOOK_TARGET_URL explicitly.",
            file=sys.stderr,
        )
        return 1

    if not app_id or not key:
        print(
            "ERROR: Set HUBSPOT_APP_ID and HUBSPOT_DEVELOPER_API_KEY.\n"
            "       Find them in your HubSpot developer account → app overview page.",
            file=sys.stderr,
        )
        return 1

    max_conc = int(os.environ.get("HUBSPOT_MAX_CONCURRENT", "10"))
    # Webhooks v3 management API authenticates via hapikey query param (developer API key)
    auth_params = {"hapikey": key}
    headers = {"Content-Type": "application/json"}

    print(f"Mode:       {args.env}")
    print(f"Target URL: {target}")
    print(f"App ID:     {app_id}")
    print()

    if args.dry_run:
        print("-- dry-run, no changes made --")
        print(f"Would PUT  {BASE}/webhooks/v3/{app_id}/settings")
        print(f"  targetUrl={target}  maxConcurrentRequests={max_conc}")
        for s in SUBSCRIPTIONS:
            print(f"Would POST {BASE}/webhooks/v3/{app_id}/subscriptions  {s}")
        return 0

    with httpx.Client(timeout=30.0) as client:
        # 1. Set target URL (replaces any existing one)
        r = client.put(
            f"{BASE}/webhooks/v3/{app_id}/settings",
            headers=headers,
            params=auth_params,
            json={"targetUrl": target, "maxConcurrentRequests": max_conc},
        )
        print(f"PUT  settings          → {r.status_code}")
        if not r.is_success:
            print("     ", r.text[:500])
            r.raise_for_status()

        # 2. Check existing subscriptions to avoid duplicates
        existing = _get_existing_subscriptions(client, app_id, headers, auth_params)
        existing_types = {
            (s.get("eventType"), s.get("propertyName")): s
            for s in existing
        }
        print(f"     existing subs: {len(existing)}")

        for body in SUBSCRIPTIONS:
            key_tuple = (body["eventType"], body.get("propertyName"))
            if key_tuple in existing_types:
                sub = existing_types[key_tuple]
                print(f"SKIP subscription already exists: id={sub['id']} type={body['eventType']} active={sub.get('active')}")
                # Re-activate if it was paused
                if not sub.get("active"):
                    ru = client.patch(
                        f"{BASE}/webhooks/v3/{app_id}/subscriptions/{sub['id']}",
                        headers=headers,
                        params=auth_params,
                        json={"active": True},
                    )
                    print(f"     re-activated → {ru.status_code}")
                continue

            rs = client.post(
                f"{BASE}/webhooks/v3/{app_id}/subscriptions",
                headers=headers,
                params=auth_params,
                json=body,
            )
            print(f"POST subscription {body['eventType']} → {rs.status_code}")
            if not rs.is_success:
                print("     ", rs.text[:300])
                rs.raise_for_status()

    print()
    print("Done.")
    print()
    if args.env == "dev":
        print(f"HubSpot will now POST to: {target}")
        print("Make a call in HubSpot → recording appears → webhook fires automatically.")
        print()
        print("To switch back to production when done:")
        print(f"  HUBSPOT_APP_ID=... HUBSPOT_DEVELOPER_API_KEY=... python3 {__file__} --env=prod")
    else:
        print(f"Production webhook active: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
