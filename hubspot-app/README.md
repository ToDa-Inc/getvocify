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

### 5. Publish for self-serve install (marketplace distribution)

With `distribution: "marketplace"`, any account can self-install via the sample install URL — no allowlist needed:

- **Distribution** tab → **Begin publishing** → sign the Acceptable Use Policy (AUP)
- Until the app is reviewed and listed, installs are capped at 25 accounts and installers see an "unverified app" warning they must accept
- To soften the warning (without a full marketplace review), verify your domain: **Development** → **Domain** → **Verify a domain** (`getvocify.com`)
- Test accounts (Settings → Account & Billing → Developer test accounts) never need the allowlist and don't count toward the cap, regardless of distribution mode

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
- `crm.objects.line_items.read/write`
- `crm.schemas.contacts/companies/deals/line_items.read`

After changing scopes, run `hs project upload`, then existing installs must **reconnect** (disconnect → Connect HubSpot again) so HubSpot re-issues a token with the new grants. New installs get them on first consent.

## Distribution

- **private**: Allowlist only (max 10 accounts), and you must already be a user of each account you approve. No review needed.
- **marketplace**: Self-serve install for any account (max 25 until listed, unlimited after). Requires signing the AUP; full public listing requires HubSpot review (≥3 active unaffiliated installs, docs, demo videos).

Switch in `app-hsmeta.json` → `config.distribution`. Switching from `private` to `marketplace` does not interrupt existing installs.

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
