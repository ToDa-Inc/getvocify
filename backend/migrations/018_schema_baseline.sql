-- Schema baseline: makes git match what production ALREADY has today.
--
-- Context: reviewing information_schema.columns + pg_get_constraintdef from
-- production against these migrations and backend/full_reset.sql found several
-- objects that exist in production with no corresponding migration (created by
-- hand at some point). See docs/DATABASE_SCHEMA.md for the full list, what was
-- verified and how, and how to repeat the check to catch future drift.
--
-- Rules followed here, per explicit instruction:
--   * Idempotent - safe to run more than once.
--   * Additive/non-breaking - nothing is dropped, renamed, or has data deleted.
--   * On production specifically, every statement below should be a no-op,
--     because production already has all of this. The statements exist so that
--     a FRESH database (full_reset.sql + migrations 001-018) ends up identical
--     to production instead of silently different.
--
-- Explicitly NOT done here:
--   * conversations_chat_id_key is UNIQUE(chat_id) alone in production, not the
--     composite UNIQUE(chat_id, account_id, user_id) that migration 012 declares.
--     That is a real product bug (two different users cannot both have a
--     conversation with the same WhatsApp chat_id) - it is NOT reproduced here.
--     Git keeps creating the safer composite constraint; production's bug is
--     documented in docs/DATABASE_SCHEMA.md, not baked into DDL. Fixing it for
--     real needs a data-dedup pass before anything is tightened, in its own PR.
--
-- Wrapped in an explicit transaction so this is atomic regardless of how the
-- SQL client sends it: if the NULL-guard in section 7 ever raises, EVERYTHING
-- in this file rolls back, not just the statements after it.
BEGIN;

-- =====================================================================
-- 1. crm_updates: table exists in production, but only ALTER TABLEs for it
--    ever made it into git (003, 015). No CREATE TABLE was ever versioned.
--    IF NOT EXISTS means this never touches production (table already
--    exists there) - it only matters for fresh databases.
--
--    All 7 constraints below (1 PK, 3 FK, 3 CHECK) are transcribed verbatim
--    from the production pg_get_constraintdef dump (2026-08-11), not inferred.
-- =====================================================================
CREATE TABLE IF NOT EXISTS crm_updates (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  memo_id UUID NOT NULL REFERENCES memos(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  crm_connection_id UUID NOT NULL REFERENCES crm_connections(id) ON DELETE CASCADE,
  action_type TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id TEXT,
  data JSONB NOT NULL DEFAULT '{}'::jsonb,
  response JSONB,
  status TEXT NOT NULL DEFAULT 'pending',
  error_message TEXT,
  retry_count INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  CONSTRAINT crm_updates_status_check CHECK (status = ANY (ARRAY['pending'::text, 'success'::text, 'failed'::text, 'retrying'::text])),
  CONSTRAINT crm_updates_resource_type_check CHECK (resource_type = ANY (ARRAY['deal'::text, 'contact'::text, 'company'::text, 'task'::text, 'note'::text])),
  CONSTRAINT crm_updates_action_type_check CHECK (action_type = ANY (ARRAY[
    'create_deal'::text,
    'update_deal'::text,
    'upsert_company'::text,
    'upsert_contact'::text,
    'merge_tasks'::text,
    'create_tasks'::text,
    'create_note'::text,
    'create_line_item'::text
  ]))
);

-- =====================================================================
-- 2. conversations / conversation_messages: same situation as crm_updates -
--    already created by migration 012, IF NOT EXISTS is a no-op on
--    production and on any environment that already ran 012.
--
--    UNIQUE(chat_id, account_id, user_id) below matches migration 012's own
--    text exactly, on purpose - see header comment. This is NOT what
--    production enforces today; it is what git says should be enforced.
-- =====================================================================
CREATE TABLE IF NOT EXISTS conversations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  chat_id TEXT NOT NULL,
  account_id TEXT NOT NULL,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  channel TEXT NOT NULL DEFAULT 'whatsapp',
  state TEXT NOT NULL DEFAULT 'idle' CHECK (
    state IN (
      'idle',
      'waiting_approval',
      'waiting_add_fields',
      'waiting_crm_instruction',
      'waiting_deal_choice'
    )
  ),
  pending_memo_id UUID REFERENCES memos(id) ON DELETE SET NULL,
  pending_artifact_ids JSONB,
  state_expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(chat_id, account_id, user_id)
);

CREATE TABLE IF NOT EXISTS conversation_messages (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  direction TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
  content_type TEXT NOT NULL DEFAULT 'text' CHECK (
    content_type IN ('text', 'extraction_summary', 'system')
  ),
  content TEXT,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversations_user_chat ON conversations(user_id, chat_id, account_id);
CREATE INDEX IF NOT EXISTS idx_conversations_state ON conversations(user_id, state, state_expires_at);
CREATE INDEX IF NOT EXISTS idx_conversation_messages_conversation_created
  ON conversation_messages(conversation_id, created_at DESC);

-- =====================================================================
-- 3. RLS: crm_updates, conversations and conversation_messages have
--    rowsecurity = true in production today (confirmed via pg_tables,
--    2026-08-13), even though none of migrations 003, 012 or 015 ever
--    enabled it. Enabling it here is a no-op on production and closes the
--    gap for fresh databases, which would otherwise leave these three
--    tables world-readable/writable to any authenticated role.
--
--    All 3 policies below are transcribed verbatim from production's
--    pg_policies (confirmed 2026-08-13), not invented. Note crm_updates
--    only has a SELECT policy - no INSERT/UPDATE/DELETE policy for regular
--    users, consistent with the backend writing to it via service_role
--    (which bypasses RLS) and only exposing read access to owners.
--    CREATE POLICY has no IF NOT EXISTS in Postgres, so each is wrapped in
--    a DO block guard for idempotency.
-- =====================================================================
ALTER TABLE crm_updates ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_messages ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'conversations'
      AND policyname = 'Users can manage own conversations'
  ) THEN
    CREATE POLICY "Users can manage own conversations"
      ON conversations FOR ALL
      USING (auth.uid() = user_id);
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'conversation_messages'
      AND policyname = 'Users can manage messages in own conversations'
  ) THEN
    CREATE POLICY "Users can manage messages in own conversations"
      ON conversation_messages FOR ALL
      USING (
        conversation_id IN (
          SELECT id FROM conversations WHERE user_id = auth.uid()
        )
      );
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'crm_updates'
      AND policyname = 'Users can view own crm updates'
  ) THEN
    CREATE POLICY "Users can view own crm updates"
      ON crm_updates FOR SELECT
      USING (auth.uid() = user_id);
  END IF;
END $$;

-- =====================================================================
-- 4. user_voice_enrollments: no divergence found - production matches
--    migration 017 exactly. Included here only so full_reset.sql-driven
--    fresh databases get it too (017 already handles incremental installs).
--    IF NOT EXISTS makes this a no-op wherever 017 already ran.
-- =====================================================================
CREATE TABLE IF NOT EXISTS user_voice_enrollments (
  user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  rep_label TEXT NOT NULL DEFAULT 'Salesperson',
  speaker_identifiers JSONB NOT NULL DEFAULT '[]'::jsonb,
  sample_count INT NOT NULL DEFAULT 1,
  consent_version TEXT NOT NULL,
  consented_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT user_voice_enrollments_identifiers_array
    CHECK (jsonb_typeof(speaker_identifiers) = 'array'),
  CONSTRAINT user_voice_enrollments_sample_count_positive
    CHECK (sample_count > 0)
);

-- =====================================================================
-- 5. memos.conversation_id: migration 009 added it as TEXT (no FK); 012's
--    `ADD COLUMN IF NOT EXISTS conversation_id UUID REFERENCES conversations(id)`
--    is a no-op on any database where 009 already ran, because the column
--    already exists (as TEXT). Production has UUID + FK anyway (confirmed:
--    memos_conversation_id_fkey, FOREIGN KEY (conversation_id) REFERENCES
--    conversations(id) ON DELETE SET NULL), meaning it either never ran 009
--    as currently written, or was corrected by hand. Either way, a fresh
--    database running 009 then 012 today ends up with TEXT and no FK -
--    different from production. Fix that here.
-- =====================================================================
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'memos'
      AND column_name = 'conversation_id' AND data_type <> 'uuid'
  ) THEN
    ALTER TABLE memos ALTER COLUMN conversation_id TYPE UUID USING conversation_id::uuid;
  END IF;
END $$;

-- Name-agnostic check: adds the FK only if memos.conversation_id doesn't
-- already have one under ANY name, so this doesn't assume what production's
-- existing FK (if any) happens to be called.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint c
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
    WHERE c.conrelid = 'memos'::regclass
      AND c.contype = 'f'
      AND a.attname = 'conversation_id'
  ) THEN
    ALTER TABLE memos
      ADD CONSTRAINT memos_conversation_id_fkey
      FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL;
  END IF;
END $$;

-- =====================================================================
-- 6. memos.source / memos.source_type: git (010, 009) leaves these as
--    TEXT with default 'voice_memo' / TEXT with no default. Production has
--    TEXT default 'web' and VARCHAR(50) default 'voice_memo' respectively.
--    memos.source's 'web' default matters for the web-upload path.
-- =====================================================================
ALTER TABLE memos ALTER COLUMN source SET DEFAULT 'web';
ALTER TABLE memos ALTER COLUMN source_type TYPE VARCHAR(50);
ALTER TABLE memos ALTER COLUMN source_type SET DEFAULT 'voice_memo';

-- =====================================================================
-- 7. CORRECTIVE: restore NOT NULL on crm_configurations.connection_id,
--    crm_configurations.user_id and crm_schemas.connection_id. Their
--    original migrations declared NOT NULL; production has them nullable
--    with no migration ever relaxing them (changed by hand). Checked
--    directly against production on 2026-08-13: crm_configurations has 6
--    rows total with 0 NULLs in either column, and crm_schemas has 16 rows
--    with 0 NULLs in connection_id. Versioning the weaker (nullable) state
--    would version a regression with no data-migration cost to justify it,
--    so this restores NOT NULL instead of documenting the drift as debt.
--    The DO block fails loudly and explicitly if that 0-NULL assumption
--    ever stops holding, instead of a bare constraint-violation error.
-- =====================================================================
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM crm_configurations WHERE connection_id IS NULL) THEN
    RAISE EXCEPTION 'crm_configurations.connection_id has NULL rows - cannot restore NOT NULL blindly. Investigate before re-running this migration.';
  END IF;
  IF EXISTS (SELECT 1 FROM crm_configurations WHERE user_id IS NULL) THEN
    RAISE EXCEPTION 'crm_configurations.user_id has NULL rows - cannot restore NOT NULL blindly. Investigate before re-running this migration.';
  END IF;
END $$;

ALTER TABLE crm_configurations ALTER COLUMN connection_id SET NOT NULL;
ALTER TABLE crm_configurations ALTER COLUMN user_id SET NOT NULL;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM crm_schemas WHERE connection_id IS NULL) THEN
    RAISE EXCEPTION 'crm_schemas.connection_id has NULL rows - cannot restore NOT NULL blindly. Investigate before re-running this migration.';
  END IF;
END $$;

ALTER TABLE crm_schemas ALTER COLUMN connection_id SET NOT NULL;

COMMIT;
