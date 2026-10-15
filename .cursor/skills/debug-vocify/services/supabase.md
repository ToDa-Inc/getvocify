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

## Read-only rows (service role, from `backend/.env`)

When MCP is not connected, read rows with the backend's own client. SELECT only;
never print the key.

```bash
cd ~/getvocify/backend && source .venv/bin/activate && python3 -I - <<'PY'
import re
env = {}
for line in open('.env'):
    m = re.match(r'^([A-Z_]+)="?([^"\n]*)"?$', line.strip())
    if m: env[m.group(1)] = m.group(2)
from supabase import create_client
s = create_client(env['SUPABASE_URL'], env['SUPABASE_SERVICE_ROLE_KEY'])
rows = (s.table('outbound_calls')
        .select('created_at,call_disposition,status,answered_at,recording_duration,carrier_call_id,memo_id')
        .eq('user_id', '<user_id>').gte('created_at', '2026-10-15T00:00:00')
        .order('created_at').limit(50).execute().data)
for r in rows: print(r)
PY
```

`.env` points at production (`ENVIRONMENT=production`): treat every query as production.
