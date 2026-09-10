# Salesforce

CRM OAuth via Connected App.

| | |
|---|---|
| Env | `SALESFORCE_CLIENT_ID`, `SALESFORCE_CLIENT_SECRET`, `SALESFORCE_REDIRECT_URI`, `SALESFORCE_LOGIN_BASE` |
| Logs | `salesforce` |
| Docs | https://developer.salesforce.com |

Production redirect should be the API host, not `localhost`. Tokens are per-user
in `crm_connections`.
