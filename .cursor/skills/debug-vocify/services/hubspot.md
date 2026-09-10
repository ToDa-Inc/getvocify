# HubSpot

CRM OAuth, contact search, recording sync.

| | |
|---|---|
| Env | `HUBSPOT_CLIENT_ID`, `HUBSPOT_CLIENT_SECRET`, `HUBSPOT_REDIRECT_URI`, `HUBSPOT_APP_ID` |
| Code | `backend/app/services/hubspot/`, `src/components/dashboard/hubspot/` |
| Logs | `hubspot` |
| Docs | https://developers.hubspot.com |

User tokens live in `crm_connections`, not env. Debug: Railway logs, then the
user's connection row (no token dump). Callback must match
`https://api.getvocify.com/api/v1/crm/hubspot/callback` in production.
