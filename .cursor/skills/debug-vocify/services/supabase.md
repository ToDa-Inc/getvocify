# Supabase

Auth + Postgres (profiles, companies, memos, invitations).

| | |
|---|---|
| Env | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET` |
| MCP | `supabase2` (management). Never print the access token. |
| Logs | Railway + Supabase dashboard |

Use MCP for schema/migrations when needed. For a specific row failure, grep
Railway logs for the PostgREST URL and status (`42501`, `PGRST106`, `406`).
Service-role must stay on the shared client or RLS breaks inserts.
