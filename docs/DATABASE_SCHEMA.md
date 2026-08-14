# Database schema: git is the source of truth

The schema lives in `backend/migrations/*.sql` (applied in filename order) and
`backend/full_reset.sql` (a from-scratch equivalent, used for fresh
environments/tests). Both files describe what the schema **should** be.
Production is not automatically guaranteed to match them: anyone with
dashboard access can add a column, drop a `NOT NULL`, or rename a constraint
without ever touching git.

If you're about to write a migration, or you suspect prod and git have
diverged, verify first. Don't assume "it's recent, so it's probably right" -
that assumption is exactly what produced the divergences below.

## What was verified against production (2026-08-13), and how

Verification happened in two independent ways, cross-checked against each
other:

1. Manual `information_schema.columns` dump (all `public` tables), run by
   hand in the Supabase SQL editor and pasted for review.
2. `backend/scripts/dump_schema.py`, run against the same production project
   via the PostgREST OpenAPI doc (no `DATABASE_URL` was available locally).

Both agreed on every column, type, nullability and default they could both
see. PostgREST doesn't expose CHECK constraints or is not fully reliable for
defaults, so those were only checked via method 1.

**Not verified**: `pg_get_constraintdef` for every constraint in
`public` - only for the specific ones flagged below. There may be other
constraints (naming, composition, or CHECK clauses) that have drifted from
git without anyone noticing yet. Function/trigger definitions and indexes
were not audited at all in this pass.

RLS **enabled/disabled** state and **policies** were both checked for
`crm_updates`, `conversations` and `conversation_messages` (2026-08-13):
`rowsecurity = true` for all three, and exactly 3 policies exist:

| Table | Policy | Command | `USING` |
|---|---|---|---|
| `conversations` | `Users can manage own conversations` | `ALL` | `auth.uid() = user_id` |
| `conversation_messages` | `Users can manage messages in own conversations` | `ALL` | `conversation_id IN (SELECT id FROM conversations WHERE user_id = auth.uid())` |
| `crm_updates` | `Users can view own crm updates` | `SELECT` only | `auth.uid() = user_id` |

`crm_updates` has no `INSERT`/`UPDATE`/`DELETE` policy for regular users -
writes to it go through the backend's `service_role` client, which bypasses
RLS entirely. Regular users can only read their own rows. This lines up with
the "Fix crm_updates RLS 42501 by keeping DB client on service_role" commit
in git history.

## Divergences found (baselined into `018_schema_baseline.sql`)

These are real differences between what git's migrations would produce on a
fresh database and what production actually has today. None of them have a
corresponding migration - they happened by hand.

| Object | Git says | Production has | Baselined as |
|---|---|---|---|
| `crm_updates` | Only `ALTER TABLE`s exist (003, 015) - no `CREATE TABLE` anywhere | Full table, in use since early on, with 7 constraints (1 PK, 3 FK, 3 CHECK) | `CREATE TABLE IF NOT EXISTS` with all 7 constraints transcribed verbatim from the production `pg_get_constraintdef` dump (2026-08-11) - `crm_updates_status_check` (`pending`/`success`/`failed`/`retrying`), `crm_updates_resource_type_check` (`deal`/`contact`/`company`/`task`/`note`), `crm_updates_action_type_check`, and the 3 `ON DELETE CASCADE` FKs to `memos`, `auth.users` and `crm_connections`. Nothing inferred. |
| `memos.conversation_id` | `TEXT`, no FK (from 009, contradicted by 012's `UUID ... REFERENCES conversations(id)` running later against a column that already existed as `TEXT`) | `UUID REFERENCES conversations(id) ON DELETE SET NULL` (confirmed: `memos_conversation_id_fkey`) | Baselined as `UUID` with the FK, matching production. This is the one that actually matters: on a truly fresh DB, migrations 009 then 012 currently leave this column in a different state than production has today. |
| `memos.source` | `TEXT` (010) | `TEXT DEFAULT 'web'` | Baselined with the `'web'` default. Web-upload memos rely on this default; a fresh environment without it behaves differently than prod for that path. |
| `memos.source_type` | `TEXT`, no default (009) | `VARCHAR(50) DEFAULT 'voice_memo'` | Baselined as `VARCHAR(50) DEFAULT 'voice_memo'`, matching production. |
| `conversations_chat_id_key` | Migration 012 declares `UNIQUE(chat_id, account_id, user_id)` | Confirmed via `pg_get_constraintdef`: `UNIQUE (chat_id)` alone | **Not baselined into DDL, deliberately.** This is a real product bug - two different users cannot both have a conversation with the same WhatsApp `chat_id`. Reproducing it in git (even to "match production") would mean every future fresh install inherits the bug. Migrations and `full_reset.sql` keep creating the safer composite constraint from 012's original text; this table documents the divergence instead. Fixing production's actual constraint needs a data-dedup pass first, in its own PR - not a schema-versioning problem. |
| `crm_configurations.connection_id`, `crm_configurations.user_id`, `crm_schemas.connection_id` | `NOT NULL` (their original migrations) | Nullable, with no migration ever relaxing them (changed by hand) | **Restored to `NOT NULL`** in `018_schema_baseline.sql`, not baselined as nullable. As of 2026-08-13: `crm_configurations` has 6 rows total with 0 NULLs in either column, and `crm_schemas` has 16 rows with 0 NULLs in `connection_id`. With zero existing NULLs, versioning the weaker (nullable) state would version a regression for no reason - the migration restores `NOT NULL` behind a guard that fails loudly and explicitly if that ever stops holding. |
| RLS + policies on `crm_updates`, `conversations`, `conversation_messages` | None of migrations 003, 012 or 015 ever enabled RLS or added policies | `rowsecurity = true` for all three, with exactly 3 policies total (confirmed via `pg_tables` + `pg_policies`, 2026-08-13) - see table above | RLS enabled and all 3 policies added verbatim, each behind a `DO $$ ... $$` guard (`CREATE POLICY` has no `IF NOT EXISTS` in Postgres) so re-running the migration doesn't error. |

`user_voice_enrollments` (migration 017) was checked with the same rigor as
everything else and has **no divergence** - production matches git exactly,
confirmed independently through both methods above.

## How to repeat this check (detect future drift)

`backend/scripts/dump_schema.py` reads production credentials
(`DATABASE_URL` or `SUPABASE_SERVICE_ROLE_KEY`) directly. The service role
key bypasses RLS entirely - full read/write access to every table. Run this
script yourself; do not ask an agent to read `backend/.env` or run it on your
behalf. If an agent needs a production fact to do its job, it should ask for
the specific query and you run it.

Run:

```bash
python backend/scripts/dump_schema.py
```

- If `DATABASE_URL` is set, it dumps `information_schema.columns` **and**
  `pg_constraint` (via `pg_get_constraintdef`) straight from Postgres into
  `backend/migrations/_schema_dump.sql` (gitignored - it's a snapshot to diff
  against git, never something to commit or trust as a source of truth).
- Otherwise, if `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` are set (e.g. in
  `backend/.env`), it reads the PostgREST OpenAPI doc instead. This gives you
  columns, types, and nullability, but not CHECK constraints or dependable
  defaults. The script prints the exact SQL to run by hand in the Supabase
  SQL editor to fill that gap - the same two queries used for this
  verification pass:

```sql
SELECT table_name, column_name, ordinal_position, data_type, udt_name,
       is_nullable, column_default, character_maximum_length
FROM information_schema.columns
WHERE table_schema = 'public'
ORDER BY table_name, ordinal_position;
```

```sql
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE connamespace = 'public'::regnamespace
ORDER BY conname;
```

Diff the output against `backend/migrations/` and `backend/full_reset.sql` by
hand. There is no automated diff tool for this yet - if drift is found
often enough to justify one, that's a reasonable follow-up.

## What actually changes in production when `018_schema_baseline.sql` is applied

Confirmed, statement by statement, against the column/constraint/RLS state
already verified above. Only section 7 changes anything real.

| # | Statement(s) | Effect on production |
|---|---|---|
| 1 | `CREATE TABLE IF NOT EXISTS crm_updates (...)` | No-op. Table already exists. |
| 2 | `CREATE TABLE IF NOT EXISTS conversations (...)`, `CREATE TABLE IF NOT EXISTS conversation_messages (...)`, 3x `CREATE INDEX IF NOT EXISTS` | No-op. Both tables already exist (migration 012). The 3 indexes are the same ones migration 012 already created with these exact names, so `IF NOT EXISTS` skips them too. |
| 3 | 3x `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`, then 3x `DO $$ ... $$`-guarded `CREATE POLICY` | No-op. `rowsecurity` is already `true` on all three tables, and all 3 policies already exist with these exact names (confirmed via `pg_tables` + `pg_policies`, 2026-08-13), so each guard's `IF NOT EXISTS` is false and no `CREATE POLICY` executes. |
| 4 | `CREATE TABLE IF NOT EXISTS user_voice_enrollments (...)` | No-op. Table already exists (migration 017). |
| 5 | 2x `DO $$ ... $$` guarding `memos.conversation_id` type + FK | No-op. Both `IF` conditions evaluate false on production: the column is already `uuid` (not `<> 'uuid'`), and an FK on that column already exists (`memos_conversation_id_fkey`, so `NOT EXISTS (...)` is false). Neither `ALTER TABLE` inside the blocks executes. |
| 6 | `ALTER TABLE memos ALTER COLUMN source SET DEFAULT 'web'`, `... source_type TYPE VARCHAR(50)`, `... source_type SET DEFAULT 'voice_memo'` | Executes, but sets values identical to what's already there (`source` default is already `'web'`, `source_type` is already `varchar(50)` default `'voice_memo'`). This briefly takes a metadata lock on `memos` but the end state is byte-for-byte the same as before. Not a true no-op at the statement level, but a no-op in effect. |
| 7 | 2x `DO $$ ... $$` NULL-guards, then 3x `ALTER TABLE ... SET NOT NULL` | **The only real change.** All three columns (`crm_configurations.connection_id`, `crm_configurations.user_id`, `crm_schemas.connection_id`) are nullable today and become `NOT NULL`. The NULL-guards should not raise (0 NULLs confirmed 2026-08-13) but if data changed since then and a NULL now exists, the guard raises `EXCEPTION`. |

Your read was correct: the three `SET NOT NULL` statements in section 7 are
the only ones that change production's actual behavior. Everything else
either changes nothing (sections 1-5) or changes nothing observable
(section 6, since it sets values already in place).

The whole file is wrapped in an explicit `BEGIN;` / `COMMIT;`, so this isn't
just "should roll back" - if the NULL-guard raises, Postgres rolls back the
entire transaction, including sections 1-6, regardless of whether the SQL
client you're using would otherwise treat pasted statements as one implicit
transaction or several independent ones.

## Post-apply verification (run after applying `018_schema_baseline.sql`)

Run each of these against production right after applying the migration and
compare against the expected result. If any of them don't match, stop and
investigate before assuming the migration is done.

**1. `crm_updates` has all 7 constraints:**

```sql
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'crm_updates'::regclass
ORDER BY conname;
```

Expected: exactly 7 rows - `crm_updates_pkey` (`PRIMARY KEY (id)`),
`crm_updates_memo_id_fkey`, `crm_updates_user_id_fkey`,
`crm_updates_crm_connection_id_fkey` (all `ON DELETE CASCADE`),
`crm_updates_action_type_check`, `crm_updates_resource_type_check`, and
`crm_updates_status_check` (`CHECK (status = ANY (ARRAY['pending'::text,
'success'::text, 'failed'::text, 'retrying'::text]))`).

**2. The three `NOT NULL`s were restored:**

```sql
SELECT table_name, column_name, is_nullable
FROM information_schema.columns
WHERE (table_name = 'crm_configurations' AND column_name IN ('connection_id', 'user_id'))
   OR (table_name = 'crm_schemas' AND column_name = 'connection_id')
ORDER BY table_name, column_name;
```

Expected: `is_nullable = 'NO'` on all 3 rows.

**3. `memos.source` / `memos.source_type` / `memos.conversation_id` types and defaults:**

```sql
SELECT column_name, data_type, udt_name, column_default, character_maximum_length
FROM information_schema.columns
WHERE table_name = 'memos' AND column_name IN ('source', 'source_type', 'conversation_id')
ORDER BY column_name;
```

Expected: `conversation_id` → `uuid`; `source` → `text`, default
`'web'::text`; `source_type` → `character varying(50)`, default
`'voice_memo'::character varying`. (These three should already match today -
the migration should change nothing here; this just confirms it stayed that way.)

**4. `memos.conversation_id` has its FK:**

```sql
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'memos'::regclass AND contype = 'f' AND conname LIKE '%conversation_id%';
```

Expected: 1 row - `FOREIGN KEY (conversation_id) REFERENCES conversations(id)
ON DELETE SET NULL`.

**5. RLS + policies on the three previously-unversioned tables:**

```sql
SELECT tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN ('crm_updates', 'conversations', 'conversation_messages')
ORDER BY tablename;
```

Expected: `rowsecurity = true` on all 3 (should already be true today; this
just confirms the migration didn't change it).

```sql
SELECT tablename, policyname, cmd
FROM pg_policies
WHERE schemaname = 'public'
  AND tablename IN ('crm_updates', 'conversations', 'conversation_messages')
ORDER BY tablename, policyname;
```

Expected: exactly 3 rows - `conversations` / `Users can manage own
conversations` / `ALL`; `conversation_messages` / `Users can manage messages
in own conversations` / `ALL`; `crm_updates` / `Users can view own crm
updates` / `SELECT`.

## Adding new columns/constraints going forward

Every schema change must ship as a new numbered file in `backend/migrations/`
**and** be reflected in `backend/full_reset.sql`, in the same PR. A change
that only exists in the Supabase dashboard does not exist as far as this
codebase is concerned, and will silently rot into another entry in the table
above.
