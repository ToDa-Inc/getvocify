# Vocify HubSpot App (2025.2)

Minimal HubSpot developer platform app for Vocify OAuth. No UI extensions, cards, or webhooks—just the app definition for OAuth with contacts, companies, and deals.

## Prerequisites

- [Node.js](https://nodejs.org/) (LTS)
- [HubSpot CLI](https://developers.hubspot.com/developer-tooling/local-development/hubspot-cli/install-the-cli) v7.6.0+

```bash
npm install -g @hubspot/cli@latest
```

## Setup

### 1. Authenticate with HubSpot

```bash
hs auth
```

This opens a browser to link the CLI to your HubSpot developer account.

### 2. Create a test account (optional but recommended)

In HubSpot: **Settings → Account & Billing → Developer test accounts → Create test account**

Use a test account to avoid impacting production data.

### 3. Upload the project

From the **getvocify** repo root:

```bash
cd hubspot-app
hs project upload
```

On first run, the CLI will ask whether to create the project in your account—confirm yes. It detects `hsproject.json` and `src/app/app-hsmeta.json` and uploads the config.

Subsequent runs update the existing project.

### 4. Get Client ID and Secret

```bash
hs project open
```

In the HubSpot UI:
- **Project components** → click your app (e.g. `vocify`)
- **Auth** tab → copy **Client ID** and **Client secret**

Add to your backend `.env`:

```
HUBSPOT_CLIENT_ID=your-client-id
HUBSPOT_CLIENT_SECRET=your-client-secret
HUBSPOT_REDIRECT_URI=https://api.getvocify.com/api/v1/crm/hubspot/callback
```

(Local dev: `HUBSPOT_REDIRECT_URI=http://localhost:8000/api/v1/crm/hubspot/callback`)

### 5. Add test installs (private distribution)

For `distribution: "private"`, you must allowlist accounts:

- **Distribution** tab → **Test installs** → Add your test account
- Or **Standard install** → allow your production portal

## Config reference

| File | Purpose |
|------|---------|
| `hsproject.json` | Project root: name, srcDir, platformVersion |
| `src/app/app-hsmeta.json` | App definition: name, OAuth, scopes, redirect URLs |

## Redirect URLs

Must be HTTPS in production. Currently configured:

- `https://api.getvocify.com/api/v1/crm/hubspot/callback` (production)
- `http://localhost:8000/api/v1/crm/hubspot/callback` (local dev)

Add more in `app-hsmeta.json` → `auth.redirectUrls` if needed.

## Scopes

Required for Vocify:

- `crm.objects.contacts.read/write`
- `crm.objects.companies.read/write`
- `crm.objects.deals.read/write`
- `crm.schemas.contacts/companies/deals.read`

## Distribution

- **private**: Allowlist only. Quick to ship, no marketplace review.
- **marketplace**: List on HubSpot App Marketplace. Requires review.

Switch in `app-hsmeta.json` → `config.distribution`.

## Backend: OAuth flow

Vocify backend must implement:

1. **GET /api/v1/crm/hubspot/authorize** – Redirect user to HubSpot OAuth URL with `client_id`, `redirect_uri`, `scope`, `state`.
2. **GET /api/v1/crm/hubspot/callback** – Receive `code` and `state`, exchange for tokens, store in `crm_connections`, redirect user to frontend.

Current backend has `POST /hubspot/connect` (token paste). Add the OAuth initiate + callback routes to support public app install.

## Useful commands

```bash
hs project upload    # Deploy config changes
hs project open       # Open project in HubSpot
hs project dev        # Local dev with hot reload (for extensions; not needed for OAuth-only)
```
