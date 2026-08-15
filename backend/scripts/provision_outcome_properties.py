#!/usr/bin/env python3
"""
OPTIONAL / DEV-ONLY. Production accounts no longer need this script: sync
self-provisions these same properties automatically the first time a
preview is built for a portal that's missing them (idempotent, once per
portal - see ensure_call_outcome_capability in
backend/app/services/hubspot/call_outcome.py, which this script's constants
now import from to stay in sync). If self-provisioning can't succeed
(typically a missing crm.schemas.contacts.write scope on an OAuth
connection that predates this feature), the extension simply doesn't show
the Converted/On Hold/Lost buttons for that account - it does NOT fall back
to expecting someone to run this script.

This script is kept for local/dev testing against a Private App token in a
sandbox portal, where there's no OAuth connection row for
ensure_call_outcome_capability to self-provision through.

Idempotently provisions:

  1. Two custom options on the CONTACT's hs_lead_status property:
     VOCIFY_LOST and VOCIFY_FOLLOW_UP. ("Converted" reuses OPEN_DEAL, a real
     HubSpot default option - never created here.)
  2. A custom CONTACT property, vocify_lost_reason (single-line text), that
     holds the Lost reason when there's no deal to mirror it onto.

Safe to re-run: every step reads the current property first and only PATCHes
options / creates the property that don't already exist. Running this twice
in a row is a no-op the second time.

This does NOT touch the deal-side "closed lost reason" property - that one
is either the portal's own pre-existing property (auto-detected, see
resolve_lost_reason_property) or a confirmed override
(crm_configurations.lost_reason_deal_property, set from the HubSpot
Configuration screen). There is nothing to provision for it: sync only ever
writes to a property that's already there.

Usage:
    python backend/scripts/provision_outcome_properties.py [--access-token TOKEN] [--dry-run]

Auth (in this order):
    --access-token CLI flag
    HUBSPOT_ACCESS_TOKEN or HUBSPOT_DEVELOPER_API_KEY (backend/.env or ./.env),
    same convention as scripts/create_hubspot_properties.sh.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]

CONTACT_OBJECT_TYPE = "contacts"

# Imported from the app so this script can't silently drift from what sync
# actually writes/self-provisions - falls back to hardcoded values if the
# app package isn't importable in whatever environment runs this script
# (e.g. a bare venv without the backend's full dependency set installed).
try:
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from app.services.hubspot.call_outcome import (  # noqa: E402
        CONTACT_LOST_REASON_PROPERTY as LOST_REASON_PROPERTY,
        HS_LEAD_STATUS_PROPERTY,
        REQUIRED_LEAD_STATUS_OPTIONS as NEW_LEAD_STATUS_OPTIONS,
    )
except Exception:
    HS_LEAD_STATUS_PROPERTY = "hs_lead_status"
    LOST_REASON_PROPERTY = "vocify_lost_reason"
    NEW_LEAD_STATUS_OPTIONS = [
        {"label": "Lost (Vocify)", "value": "VOCIFY_LOST"},
        {"label": "Follow-up (Vocify)", "value": "VOCIFY_FOLLOW_UP"},
    ]


def _load_dotenv() -> None:
    """Best-effort load of backend/.env then ./.env, without overwriting
    already-set env vars. Matches dump_schema.py / create_hubspot_properties.sh."""
    for env_path in (REPO_ROOT / "backend" / ".env", REPO_ROOT / ".env"):
        if not env_path.exists():
            continue
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def _base_url(token: str) -> str:
    # EU-hosted portals issue pat-eu1-* tokens; everything else is the
    # default (na1) API host. Same detection as create_hubspot_properties.sh.
    return "https://api-eu1.hubapi.com" if token.startswith("pat-eu1-") else "https://api.hubapi.com"


def _get_property(client: httpx.Client, base_url: str, headers: dict, object_type: str, name: str) -> dict | None:
    r = client.get(f"{base_url}/crm/v3/properties/{object_type}/{name}", headers=headers)
    if r.status_code == 200:
        return r.json()
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return None


def provision_lead_status_options(client: httpx.Client, base_url: str, headers: dict, dry_run: bool) -> None:
    prop = _get_property(client, base_url, headers, CONTACT_OBJECT_TYPE, HS_LEAD_STATUS_PROPERTY)
    if prop is None:
        print(
            f"ERROR: contact property '{HS_LEAD_STATUS_PROPERTY}' not found on this portal - "
            "this is a HubSpot default property that should always exist. Check the access "
            "token's scopes (crm.schemas.contacts.read) and portal.",
            file=sys.stderr,
        )
        sys.exit(1)

    existing_options = prop.get("options") or []
    existing_values = {opt.get("value") for opt in existing_options}
    missing = [opt for opt in NEW_LEAD_STATUS_OPTIONS if opt["value"] not in existing_values]

    if not missing:
        print(f"✅ {HS_LEAD_STATUS_PROPERTY}: VOCIFY_LOST and VOCIFY_FOLLOW_UP already present, skipping.")
        return

    next_order = max((opt.get("displayOrder", -1) for opt in existing_options), default=-1) + 1
    merged_options = list(existing_options) + [
        {**opt, "displayOrder": next_order + i, "hidden": False}
        for i, opt in enumerate(missing)
    ]

    print(f"→ {HS_LEAD_STATUS_PROPERTY}: adding {[o['value'] for o in missing]}")
    if dry_run:
        print("  (dry-run, not applied)")
        return

    r = client.patch(
        f"{base_url}/crm/v3/properties/{CONTACT_OBJECT_TYPE}/{HS_LEAD_STATUS_PROPERTY}",
        headers=headers,
        json={"options": merged_options},
    )
    if not r.is_success:
        print(f"  FAILED ({r.status_code}): {r.text[:500]}", file=sys.stderr)
        r.raise_for_status()
    print("  ✅ done")


def provision_lost_reason_property(client: httpx.Client, base_url: str, headers: dict, dry_run: bool) -> None:
    prop = _get_property(client, base_url, headers, CONTACT_OBJECT_TYPE, LOST_REASON_PROPERTY)
    if prop is not None:
        print(f"✅ contact property '{LOST_REASON_PROPERTY}' already exists, skipping.")
        return

    print(f"→ creating contact property '{LOST_REASON_PROPERTY}'")
    if dry_run:
        print("  (dry-run, not applied)")
        return

    r = client.post(
        f"{base_url}/crm/v3/properties/{CONTACT_OBJECT_TYPE}",
        headers=headers,
        json={
            "groupName": "contactinformation",
            "name": LOST_REASON_PROPERTY,
            "label": "Lost reason (Vocify)",
            "description": (
                "Why this contact was marked Lost from a Vocify call. Written by "
                "the extension's call-outcome step, not editable by allowlists."
            ),
            "type": "string",
            "fieldType": "text",
        },
    )
    if not r.is_success:
        print(f"  FAILED ({r.status_code}): {r.text[:500]}", file=sys.stderr)
        r.raise_for_status()
    print("  ✅ created")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--access-token", help="HubSpot Private App token (overrides env vars)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without calling HubSpot")
    args = parser.parse_args()

    _load_dotenv()
    token = args.access_token or os.environ.get("HUBSPOT_ACCESS_TOKEN") or os.environ.get("HUBSPOT_DEVELOPER_API_KEY")
    if not token:
        print(
            "ERROR: No HubSpot token. Pass --access-token, or set HUBSPOT_ACCESS_TOKEN "
            "(or HUBSPOT_DEVELOPER_API_KEY) in backend/.env or .env.",
            file=sys.stderr,
        )
        return 1

    base_url = _base_url(token)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    print(f"Portal API: {base_url}")
    print(f"Token:      {token[:20]}...")
    print()

    with httpx.Client(timeout=30.0) as client:
        provision_lead_status_options(client, base_url, headers, args.dry_run)
        provision_lost_reason_property(client, base_url, headers, args.dry_run)

    print()
    print("Done." if not args.dry_run else "Dry-run complete, nothing was changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
