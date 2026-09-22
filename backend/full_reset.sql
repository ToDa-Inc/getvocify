-- ============================================
-- COMPLETE DATABASE RESET
-- ============================================
-- This script does EVERYTHING:
-- 1. Cleans all existing data/tables
-- 2. Creates fresh Vocify schema
--
-- ⚠️ WARNING: This will DELETE EVERYTHING!
-- Run this in your Supabase SQL Editor
-- ============================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS citext;

-- ============================================
-- PART 1: COMPLETE CLEANUP
-- ============================================

-- Drop ALL tables
DO $$ 
DECLARE
    r RECORD;
BEGIN
    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') 
    LOOP
        EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
    END LOOP;
END $$;

-- Drop ALL functions
DO $$ 
DECLARE
    r RECORD;
BEGIN
    FOR r IN (
        SELECT proname
        FROM pg_proc 
        WHERE pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
    ) 
    LOOP
        EXECUTE 'DROP FUNCTION IF EXISTS public.' || quote_ident(r.proname) || ' CASCADE';
    END LOOP;
END $$;

-- Drop ALL triggers
DO $$ 
DECLARE
    r RECORD;
BEGIN
    FOR r IN (
        SELECT trigger_name, event_object_table 
        FROM information_schema.triggers 
        WHERE trigger_schema = 'public'
    ) 
    LOOP
        EXECUTE 'DROP TRIGGER IF EXISTS ' || quote_ident(r.trigger_name) || 
                ' ON public.' || quote_ident(r.event_object_table) || ' CASCADE';
    END LOOP;
END $$;

-- Drop ALL policies
DO $$ 
DECLARE
    r RECORD;
BEGIN
    FOR r IN (
        SELECT schemaname, tablename, policyname 
        FROM pg_policies 
        WHERE schemaname = 'public'
    ) 
    LOOP
        EXECUTE 'DROP POLICY IF EXISTS ' || quote_ident(r.policyname) || 
                ' ON public.' || quote_ident(r.tablename);
    END LOOP;
END $$;

-- Drop ALL sequences
DO $$ 
DECLARE
    r RECORD;
BEGIN
    FOR r IN (
        SELECT sequence_name 
        FROM information_schema.sequences 
        WHERE sequence_schema = 'public'
    ) 
    LOOP
        EXECUTE 'DROP SEQUENCE IF EXISTS public.' || quote_ident(r.sequence_name) || ' CASCADE';
    END LOOP;
END $$;

-- Drop ALL views
DO $$ 
DECLARE
    r RECORD;
BEGIN
    FOR r IN (
        SELECT table_name 
        FROM information_schema.views 
        WHERE table_schema = 'public'
    ) 
    LOOP
        EXECUTE 'DROP VIEW IF EXISTS public.' || quote_ident(r.table_name) || ' CASCADE';
    END LOOP;
END $$;

-- ============================================
-- PART 2: CREATE VOCIFY SCHEMA
-- ============================================

-- 1. USER PROFILES
CREATE TABLE user_profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  full_name TEXT,
  company_name TEXT,
  avatar_url TEXT,
  phone TEXT,
  auto_create_contact_company BOOLEAN DEFAULT false,
  glossary JSONB DEFAULT '[]',
  product_context TEXT DEFAULT '',
  stt_languages TEXT[] NOT NULL DEFAULT ARRAY['es'],
  company_id UUID,
  writing_samples JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 1b. COMPANIES (shared workspace)
CREATE TABLE companies (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  seat_limit INT NOT NULL DEFAULT 1 CHECK (seat_limit >= 1),
  glossary JSONB NOT NULL DEFAULT '[]'::jsonb,
  product_context TEXT NOT NULL DEFAULT '',
  auto_create_contact_company BOOLEAN NOT NULL DEFAULT false,
  primary_crm_connection_id UUID,
  created_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE company_members (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'member')),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id),
  UNIQUE (company_id, user_id)
);

CREATE UNIQUE INDEX idx_company_members_one_owner
  ON company_members (company_id)
  WHERE role = 'owner' AND status = 'active';

CREATE TABLE company_invitations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  email CITEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('admin', 'member')),
  token_hash TEXT NOT NULL,
  invited_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  accepted_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_company_invitations_pending_email
  ON company_invitations (company_id, email)
  WHERE accepted_at IS NULL AND revoked_at IS NULL;

CREATE TABLE password_reset_tokens (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE user_profiles
  ADD CONSTRAINT user_profiles_company_id_fkey
  FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE SET NULL;

-- 2. CRM CONNECTIONS (company-scoped; user_id = connected_by)
CREATE TABLE crm_connections (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  
  provider TEXT NOT NULL CHECK (provider IN ('hubspot', 'salesforce', 'pipedrive')),
  status TEXT NOT NULL DEFAULT 'connected' CHECK (status IN ('connected', 'expired', 'error')),
  
  access_token TEXT NOT NULL,
  refresh_token TEXT,
  token_expires_at TIMESTAMPTZ,
  
  metadata JSONB DEFAULT '{}',
  
  last_synced_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  
  UNIQUE(company_id, provider)
);

ALTER TABLE user_profiles
  ADD COLUMN primary_crm_connection_id UUID REFERENCES crm_connections(id) ON DELETE SET NULL;

ALTER TABLE companies
  ADD CONSTRAINT companies_primary_crm_connection_id_fkey
  FOREIGN KEY (primary_crm_connection_id) REFERENCES crm_connections(id) ON DELETE SET NULL;

-- 3. CRM CONFIGURATIONS
CREATE TABLE crm_configurations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  connection_id UUID NOT NULL REFERENCES crm_connections(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  
  -- Pipeline scope
  default_pipeline_id TEXT NOT NULL,
  default_pipeline_name TEXT NOT NULL,
  default_stage_id TEXT NOT NULL,
  default_stage_name TEXT NOT NULL,
  
  -- Field control (whitelist approach)
  allowed_deal_fields TEXT[] DEFAULT ARRAY['dealname', 'amount', 'description', 'closedate'],
  allowed_contact_fields TEXT[] DEFAULT ARRAY['firstname', 'lastname', 'email', 'phone'],
  allowed_company_fields TEXT[] DEFAULT ARRAY['name', 'domain'],
  allowed_line_item_fields TEXT[] DEFAULT ARRAY['name', 'quantity', 'price'],
  
  -- Behavior settings
  auto_create_contacts BOOLEAN DEFAULT true,
  auto_create_companies BOOLEAN DEFAULT true,

  -- Call outcome (migration 021). lost_reasons: editable list shown in the
  -- extension's Lost picker. lost_reason_deal_property: confirmed override
  -- for the deal property that stores the portal's closed-lost reason -
  -- NULL means "let sync auto-detect it from the live deal schema" (see
  -- resolve_lost_reason_property in app/services/hubspot/call_outcome.py),
  -- not "not configured yet".
  lost_reasons JSONB NOT NULL DEFAULT
    '["No budget","No response","Chose a competitor","Bad timing","Not a fit"]'::jsonb,
  lost_reason_deal_property TEXT,

  -- Call outcome status mapping (migration 022). The admin's own portal
  -- hs_lead_status values that mean "On Hold" / "Lost" - NULL means not
  -- configured (the button doesn't appear in the extension until it is,
  -- see call_outcome.py:compute_call_outcome_availability). Vocify never
  -- creates HubSpot picklist options itself - see oauth.py's scope list.
  lost_lead_status_value TEXT,
  on_hold_lead_status_value TEXT,
  auto_sync_hubspot_calls BOOLEAN NOT NULL DEFAULT false,

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  
  UNIQUE(connection_id)
);

-- 4. CRM SCHEMAS CACHE
CREATE TABLE crm_schemas (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  connection_id UUID NOT NULL REFERENCES crm_connections(id) ON DELETE CASCADE,
  -- Includes Salesforce sObject names (migration 008) and line_items (migration 014).
  object_type TEXT NOT NULL CHECK (
    object_type IN ('deals', 'contacts', 'companies', 'line_items', 'Opportunity', 'Contact', 'Account')
  ),
  
  properties JSONB NOT NULL,
  pipelines JSONB, -- Only for deals
  
  fetched_at TIMESTAMPTZ DEFAULT NOW(),
  
  UNIQUE(connection_id, object_type)
);

-- 5. VOICE MEMOS
CREATE TABLE memos (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  
  status TEXT NOT NULL DEFAULT 'uploading' CHECK (
    status IN (
      'uploading', 'transcribing', 'extracting', 'pending_transcript',
      'pending_review', 'approved', 'rejected', 'failed'
    )
  ),
  
  -- Optional: we now store transcript only, no audio storage (migration 004).
  audio_url TEXT DEFAULT '',
  recording_path TEXT,
  audio_duration REAL,
  
  transcript TEXT,
  transcript_raw TEXT,
  transcript_confidence REAL CHECK (transcript_confidence IS NULL OR transcript_confidence BETWEEN 0 AND 1),
  transcript_stt_meta JSONB DEFAULT '{}'::jsonb,
  
  extraction JSONB,
  pipeline_meta JSONB DEFAULT '{}'::jsonb,
  pipeline_run_id UUID,
  pipeline_run_started_at TIMESTAMPTZ,
  
  -- Deal matching fields
  matched_deal_id TEXT,
  matched_deal_name TEXT,
  is_new_deal BOOLEAN DEFAULT false,
  
  error_message TEXT,
  
  created_at TIMESTAMPTZ DEFAULT NOW(),
  processed_at TIMESTAMPTZ,
  approved_at TIMESTAMPTZ,

  -- Recovery: track when processing started to identify stuck memos (see add_processing_started_at.sql).
  processing_started_at TIMESTAMPTZ,

  -- Origin + WhatsApp/HubSpot-call integration fields (migrations 009-011).
  source TEXT DEFAULT 'web' CHECK (source IN ('web', 'voice_memo', 'whatsapp', 'unipile', 'hubspot_call', 'vocify_call', 'desktop')),
  source_type VARCHAR(50) DEFAULT 'voice_memo',
  client_capture_id TEXT,
  capture_started_at TIMESTAMPTZ,
  interaction_kind TEXT CHECK (
    interaction_kind IS NULL OR interaction_kind IN ('call', 'meeting', 'visit', 'voice_note')
  ),
  sales_motion_key TEXT,
  playbook_version_id TEXT,
  company_id UUID REFERENCES companies(id) ON DELETE SET NULL,
  capture_status TEXT CHECK (
    capture_status IS NULL OR capture_status IN ('recording', 'upload_pending', 'processing', 'complete', 'failed')
  ),
  capture_content_fingerprint TEXT,
  capture_input_revision INTEGER NOT NULL DEFAULT 0,
  audio_status TEXT,
  capture_turns JSONB,
  transcript_complete BOOLEAN NOT NULL DEFAULT false,
  followup JSONB,
  followup_run_started_at TIMESTAMPTZ,
  whatsapp_message_id TEXT,
  conversation_id UUID,
  hubspot_engagement_id TEXT,
  hubspot_deal_id TEXT,
  hubspot_contact_id TEXT,
  speechmatics_job_id TEXT
);

CREATE TABLE IF NOT EXISTS memo_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID,
  memo_id UUID NOT NULL,
  kind TEXT NOT NULL,
  input_revision TEXT NOT NULL,
  revision_seq BIGINT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (
    status IN ('pending', 'running', 'success', 'failed', 'superseded')
  ),
  attempts INTEGER NOT NULL DEFAULT 0,
  available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  lease_until TIMESTAMPTZ,
  run_id UUID,
  last_error TEXT,
  result JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (memo_id, kind, input_revision),
  UNIQUE (memo_id, kind, revision_seq)
);

CREATE TABLE IF NOT EXISTS playbooks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL,
  sales_motion_key TEXT NOT NULL,
  active_version_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (company_id, sales_motion_key)
);

CREATE TABLE IF NOT EXISTS playbook_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  playbook_id UUID NOT NULL REFERENCES playbooks(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published')),
  steps JSONB NOT NULL DEFAULT '[]'::jsonb,
  entries JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS playbook_imports (
  id TEXT PRIMARY KEY,
  company_id UUID,
  playbook_id UUID,
  kind TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'ready', 'failed')),
  reason TEXT,
  draft JSONB,
  active_version_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS interaction_types (
  company_id UUID NOT NULL,
  type_key TEXT NOT NULL,
  name TEXT NOT NULL,
  active BOOLEAN NOT NULL DEFAULT true,
  PRIMARY KEY (company_id, type_key)
);

CREATE OR REPLACE FUNCTION publish_playbook_version(p_version UUID)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
  pb UUID;
BEGIN
  SELECT playbook_id INTO pb FROM playbook_versions WHERE id = p_version FOR UPDATE;
  IF pb IS NULL THEN
    RAISE EXCEPTION 'playbook version not found';
  END IF;
  PERFORM 1 FROM playbooks WHERE id = pb FOR UPDATE;
  UPDATE playbook_versions SET status = 'published' WHERE id = p_version;
  UPDATE playbooks SET active_version_id = p_version WHERE id = pb;
  RETURN p_version;
END;
$$;

CREATE OR REPLACE FUNCTION save_playbook_draft(
  p_company UUID,
  p_motion TEXT,
  p_import TEXT,
  p_payload TEXT,
  p_contradictions JSONB DEFAULT '[]'::jsonb
) RETURNS TEXT
LANGUAGE plpgsql
AS $save_draft$
DECLARE
  pb UUID;
BEGIN
  INSERT INTO playbooks (company_id, sales_motion_key)
  VALUES (p_company, p_motion)
  ON CONFLICT (company_id, sales_motion_key) DO NOTHING;

  SELECT id INTO pb FROM playbooks
  WHERE company_id = p_company AND sales_motion_key = p_motion;

  IF EXISTS (SELECT 1 FROM playbook_imports WHERE id = p_import) THEN
    RETURN 'ready';
  END IF;

  INSERT INTO playbook_versions (playbook_id, status, steps, entries)
  VALUES (
    pb,
    'draft',
    jsonb_build_array(jsonb_build_object(
      'step_id', 'imported',
      'label', left(p_payload, 80),
      'criterion', p_payload
    )),
    jsonb_build_array(jsonb_build_object(
      'entry_id', 'text:' || p_import,
      'category', 'process',
      'guidance', p_payload,
      'source_ref', 'text:' || p_import
    ))
  );

  INSERT INTO playbook_imports (
    id, company_id, playbook_id, kind, status, draft, active_version_id
  )
  VALUES (
    p_import,
    p_company,
    pb,
    'text',
    'ready',
    jsonb_build_object(
      'text', p_payload,
      'source_ref', 'text:' || p_import,
      'contradictions', COALESCE(p_contradictions, '[]'::jsonb)
    ),
    (SELECT active_version_id FROM playbooks WHERE id = pb)
  );
  RETURN 'ready';
END;
$save_draft$;

CREATE OR REPLACE FUNCTION publish_playbook_motion(p_company UUID, p_motion TEXT)
RETURNS TEXT
LANGUAGE plpgsql
AS $publish_motion$
DECLARE
  pb UUID;
  ver UUID;
BEGIN
  SELECT id INTO pb FROM playbooks
  WHERE company_id = p_company AND sales_motion_key = p_motion
  FOR UPDATE;

  IF pb IS NULL THEN
    RETURN 'not_a_draft';
  END IF;

  IF EXISTS (
    SELECT 1 FROM playbook_imports i
    WHERE i.playbook_id = pb
      AND COALESCE(jsonb_array_length(i.draft->'contradictions'), 0) > 0
      AND i.created_at = (
        SELECT max(created_at) FROM playbook_imports WHERE playbook_id = pb
      )
  ) THEN
    RETURN 'contradiction';
  END IF;

  SELECT id INTO ver FROM playbook_versions
  WHERE playbook_id = pb AND status = 'draft'
  ORDER BY created_at DESC
  LIMIT 1
  FOR UPDATE;

  IF ver IS NULL THEN
    RETURN 'not_a_draft';
  END IF;

  PERFORM publish_playbook_version(ver);
  RETURN 'published:' || ver::text;
END;
$publish_motion$;

CREATE OR REPLACE FUNCTION list_playbook_motions(p_company UUID)
RETURNS TABLE (sales_motion_key TEXT, motion_status TEXT)
LANGUAGE sql
STABLE
AS $list_motions$
  SELECT motion_key AS sales_motion_key, motion_status
  FROM (
    SELECT p.sales_motion_key AS motion_key,
      CASE
        WHEN p.active_version_id IS NOT NULL THEN 'published'
        WHEN EXISTS (
          SELECT 1 FROM playbook_versions v
          WHERE v.playbook_id = p.id AND v.status = 'draft'
        ) THEN 'draft'
        ELSE 'missing'
      END AS motion_status
    FROM playbooks p
    WHERE p.company_id = p_company
    UNION
    SELECT t.type_key,
      'missing'
    FROM interaction_types t
    WHERE t.company_id = p_company
      AND t.active
      AND NOT EXISTS (
        SELECT 1 FROM playbooks p
        WHERE p.company_id = t.company_id AND p.sales_motion_key = t.type_key
      )
  ) listed;
$list_motions$;

CREATE OR REPLACE FUNCTION add_interaction_type(p_company UUID, p_key TEXT, p_name TEXT)
RETURNS TEXT
LANGUAGE plpgsql
AS $add_type$
BEGIN
  IF btrim(p_key) = '' THEN
    RETURN 'empty';
  END IF;
  INSERT INTO interaction_types (company_id, type_key, name)
  VALUES (p_company, btrim(p_key), COALESCE(NULLIF(btrim(p_name), ''), btrim(p_key)))
  ON CONFLICT (company_id, type_key) DO NOTHING;
  RETURN btrim(p_key);
END;
$add_type$;

CREATE TABLE IF NOT EXISTS copilot_web_turns (
  id TEXT PRIMARY KEY,
  company_id UUID,
  user_id UUID NOT NULL,
  conversation_id TEXT NOT NULL,
  client_turn_id TEXT NOT NULL,
  status TEXT NOT NULL,
  body TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, conversation_id, client_turn_id)
);

CREATE TABLE IF NOT EXISTS contact_priority_context (
  company_id UUID NOT NULL,
  connection_id TEXT NOT NULL,
  contact_id TEXT NOT NULL,
  deal_id TEXT NOT NULL DEFAULT '',
  owner_user_id UUID,
  owner_ambiguous BOOLEAN NOT NULL DEFAULT false,
  coverage TEXT NOT NULL,
  history_complete BOOLEAN NOT NULL DEFAULT false,
  observed_at TIMESTAMPTZ,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (company_id, connection_id, contact_id, deal_id)
);

CREATE TABLE IF NOT EXISTS action_signals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL,
  user_id UUID NOT NULL,
  connection_id TEXT NOT NULL DEFAULT '',
  contact_id TEXT,
  deal_id TEXT,
  memo_id TEXT,
  type TEXT NOT NULL,
  dedupe_key TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL CHECK (status IN ('pending', 'done', 'dismissed', 'snoozed', 'resolved')),
  version INTEGER NOT NULL DEFAULT 1,
  snoozed_until TIMESTAMPTZ,
  previous_status TEXT,
  last_action_request_id TEXT,
  last_action_at TIMESTAMPTZ,
  undo_deadline TIMESTAMPTZ,
  coverage TEXT NOT NULL DEFAULT 'complete',
  observed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (company_id, user_id, connection_id, dedupe_key)
);

CREATE TABLE IF NOT EXISTS hoy_daily_runs (
  company_id UUID NOT NULL,
  local_date DATE NOT NULL,
  status TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (company_id, local_date)
);

CREATE TABLE IF NOT EXISTS interaction_annotations (
  author_id UUID NOT NULL,
  annotation_id TEXT NOT NULL,
  company_id UUID NOT NULL,
  client_capture_id TEXT,
  memo_id UUID,
  text TEXT NOT NULL,
  offset_ms INTEGER NOT NULL CHECK (offset_ms >= 0),
  turn_id TEXT,
  revision INTEGER NOT NULL DEFAULT 1,
  source_type TEXT NOT NULL DEFAULT 'human_note' CHECK (source_type = 'human_note'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (author_id, annotation_id)
);

CREATE TABLE IF NOT EXISTS interaction_patterns (
  memo_id UUID NOT NULL,
  pattern_id TEXT NOT NULL,
  input_revision TEXT NOT NULL,
  category TEXT NOT NULL,
  kind TEXT NOT NULL,
  resolution TEXT NOT NULL,
  response TEXT,
  evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
  superseded BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (memo_id, pattern_id, input_revision)
);

CREATE TABLE IF NOT EXISTS memo_scores (
  memo_id UUID NOT NULL,
  input_revision TEXT NOT NULL,
  revision_seq BIGINT NOT NULL,
  playbook_version_id TEXT,
  prompt_version TEXT NOT NULL DEFAULT 'scoring_v1',
  model_version TEXT,
  score JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (memo_id, input_revision)
);

CREATE TABLE IF NOT EXISTS meeting_proposals (
  proposal_id TEXT NOT NULL,
  memo_id UUID NOT NULL,
  input_revision TEXT NOT NULL,
  agreement TEXT NOT NULL,
  starts_at TIMESTAMPTZ,
  timezone TEXT,
  precision TEXT NOT NULL,
  decision TEXT NOT NULL DEFAULT 'pending',
  crm_status TEXT NOT NULL DEFAULT 'not_requested',
  evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
  remote_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (memo_id, proposal_id, input_revision)
);

CREATE TABLE IF NOT EXISTS meeting_writes (
  operation_key TEXT PRIMARY KEY,
  memo_id UUID NOT NULL,
  proposal_id TEXT NOT NULL,
  remote_id TEXT,
  crm_status TEXT NOT NULL,
  stage_changed BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS post_interaction_briefs (
  memo_id UUID NOT NULL,
  input_revision TEXT NOT NULL,
  revision_seq BIGINT NOT NULL,
  status TEXT NOT NULL,
  body JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (memo_id, input_revision)
);

CREATE TABLE IF NOT EXISTS brief_preferences (
  user_id UUID PRIMARY KEY,
  highlight_mode TEXT NOT NULL CHECK (highlight_mode IN ('immediate', 'deferred', 'end_of_day')),
  delay_minutes INTEGER,
  end_of_day TIME,
  timezone TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
  id TEXT NOT NULL,
  company_id UUID NOT NULL,
  user_id UUID NOT NULL,
  scope TEXT NOT NULL,
  period_start TIMESTAMPTZ NOT NULL,
  report_type TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  snapshot JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (id),
  UNIQUE (company_id, user_id, scope, period_start, report_type)
);

CREATE TABLE IF NOT EXISTS report_deliveries (
  idempotency_key TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  channel TEXT NOT NULL,
  delivery_status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS report_notifications (
  id TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  user_id UUID NOT NULL,
  read_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS team_outcome_observations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL,
  connection_id TEXT NOT NULL,
  deal_id TEXT NOT NULL,
  status TEXT NOT NULL,
  owner_user_id UUID,
  attribution TEXT NOT NULL,
  amount NUMERIC,
  currency TEXT,
  closed_at TIMESTAMPTZ,
  observed_at TIMESTAMPTZ NOT NULL,
  UNIQUE (company_id, connection_id, deal_id, observed_at)
);

-- F01.02 / migration 037: one client capture id per author.
CREATE UNIQUE INDEX IF NOT EXISTS idx_memos_user_client_capture_id_unique
  ON memos (user_id, client_capture_id)
  WHERE client_capture_id IS NOT NULL;

-- 6. CRM UPDATES (audit trail) - exists in production with no versioned
-- CREATE TABLE anywhere; only ALTER TABLEs for it exist (migrations 003, 015).
-- All 7 constraints transcribed verbatim from the production
-- pg_get_constraintdef dump (2026-08-11) - see migrations/018_schema_baseline.sql.
CREATE TABLE crm_updates (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  memo_id UUID NOT NULL REFERENCES memos(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  crm_connection_id UUID NOT NULL REFERENCES crm_connections(id) ON DELETE CASCADE,
  action_type TEXT NOT NULL CHECK (action_type IN (
    'create_deal',
    'update_deal',
    'upsert_company',
    'upsert_contact',
    'merge_tasks',
    'create_tasks',
    'create_note',
    'create_line_item',
    'update_call_outcome',
    'create_followup_task',
    'create_outcome_note'
  )),
  -- 'update_call_outcome' / 'create_followup_task' added by migration 021,
  -- 'create_outcome_note' by migration 022 (call outcome: Converted/On
  -- Hold/Lost - see app/services/hubspot/call_outcome.py).
  -- 'line_item' added by migration 020 - action_type already allowed
  -- create_line_item since migration 015, but resource_type never got the
  -- matching value until 020. See that migration for the full story.
  resource_type TEXT NOT NULL CHECK (resource_type IN ('deal', 'contact', 'company', 'task', 'note', 'line_item')),
  resource_id TEXT,
  data JSONB NOT NULL DEFAULT '{}'::jsonb,
  response JSONB,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'success', 'failed', 'retrying')),
  error_message TEXT,
  retry_count INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);

-- 7. WHATSAPP CONVERSATIONS (migration 012). Created after memos so
-- pending_memo_id can reference it; memos.conversation_id is added below via
-- ALTER TABLE for the same reason (mirrors the real migration order).
--
-- UNIQUE(chat_id, account_id, user_id) matches migration 012's own text
-- on purpose. Production actually enforces UNIQUE(chat_id) alone - a real
-- product bug (two different users can't share a WhatsApp chat_id), NOT
-- reproduced here. See docs/DATABASE_SCHEMA.md.
CREATE TABLE conversations (
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
      'waiting_deal_choice',
      'waiting_retarget',
      'waiting_typed_search'
    )
  ),
  pending_memo_id UUID REFERENCES memos(id) ON DELETE SET NULL,
  pending_artifact_ids JSONB,
  state_expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(chat_id, account_id, user_id)
);

CREATE TABLE conversation_messages (
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

ALTER TABLE memos ADD CONSTRAINT memos_conversation_id_fkey
  FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL;

-- 8. VOICE ENROLLMENTS (migration 017) - per-user Speechmatics speaker
-- identifiers for Call Copilot. No divergence found against production.
CREATE TABLE user_voice_enrollments (
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

-- ============================================
-- INDEXES
-- ============================================

CREATE INDEX idx_memos_user_status ON memos(user_id, status);
CREATE INDEX idx_memos_user_created ON memos(user_id, created_at DESC);
CREATE UNIQUE INDEX idx_memos_hubspot_engagement_id_unique
  ON memos (hubspot_engagement_id)
  WHERE hubspot_engagement_id IS NOT NULL;
CREATE INDEX idx_memos_hubspot_deal_created
  ON memos (hubspot_deal_id, created_at DESC)
  WHERE hubspot_deal_id IS NOT NULL;
CREATE INDEX memos_speechmatics_job_id_idx
  ON memos (speechmatics_job_id) WHERE speechmatics_job_id IS NOT NULL;
CREATE UNIQUE INDEX idx_memos_whatsapp_message_id_unique
  ON memos (whatsapp_message_id)
  WHERE whatsapp_message_id IS NOT NULL;
CREATE INDEX idx_memos_conversation_id ON memos(conversation_id);
CREATE INDEX idx_conversations_user_chat ON conversations(user_id, chat_id, account_id);
CREATE INDEX idx_conversations_state ON conversations(user_id, state, state_expires_at);
CREATE INDEX idx_conversation_messages_conversation_created
  ON conversation_messages(conversation_id, created_at DESC);
CREATE INDEX idx_crm_configurations_user ON crm_configurations(user_id);
CREATE INDEX idx_crm_configurations_connection ON crm_configurations(connection_id);
CREATE INDEX idx_crm_schemas_connection ON crm_schemas(connection_id);
CREATE UNIQUE INDEX idx_user_profiles_phone_unique
  ON user_profiles (phone)
  WHERE phone IS NOT NULL;
CREATE INDEX idx_user_profiles_primary_crm
  ON user_profiles (primary_crm_connection_id)
  WHERE primary_crm_connection_id IS NOT NULL;

-- ============================================
-- ROW LEVEL SECURITY
-- ============================================

ALTER TABLE companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE crm_connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE crm_configurations ENABLE ROW LEVEL SECURITY;
ALTER TABLE crm_schemas ENABLE ROW LEVEL SECURITY;
ALTER TABLE memos ENABLE ROW LEVEL SECURITY;

-- User Profiles Policies
CREATE POLICY "Users can view own profile"
  ON user_profiles FOR SELECT
  USING (auth.uid() = id);

CREATE POLICY "Users can update own profile"
  ON user_profiles FOR UPDATE
  USING (auth.uid() = id);

CREATE POLICY "Users can insert own profile"
  ON user_profiles FOR INSERT
  WITH CHECK (auth.uid() = id);

-- CRM Connections Policies (members of owning company)
CREATE POLICY "Company members can manage connections"
  ON crm_connections FOR ALL
  USING (
    company_id IN (
      SELECT company_id FROM company_members
      WHERE user_id = auth.uid() AND status = 'active'
    )
  );

-- CRM Configurations Policies
CREATE POLICY "Users can manage own configurations"
  ON crm_configurations FOR ALL
  USING (auth.uid() = user_id);

-- CRM Schemas Policies
CREATE POLICY "Users can view own schemas"
  ON crm_schemas FOR ALL
  USING (
    connection_id IN (
      SELECT id FROM crm_connections WHERE user_id = auth.uid()
    )
  );

-- Memos Policies
CREATE POLICY "Users can manage own memos"
  ON memos FOR ALL
  USING (auth.uid() = user_id);

-- crm_updates, conversations and conversation_messages: RLS + policies below
-- match production exactly (confirmed via pg_tables.rowsecurity and
-- pg_policies, 2026-08-13), even though none of migrations 003, 012 or 015
-- ever added them. crm_updates only gets a SELECT policy - writes to it go
-- through the backend's service_role client, which bypasses RLS.
ALTER TABLE crm_updates ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own conversations"
  ON conversations FOR ALL
  USING (auth.uid() = user_id);

CREATE POLICY "Users can manage messages in own conversations"
  ON conversation_messages FOR ALL
  USING (
    conversation_id IN (
      SELECT id FROM conversations WHERE user_id = auth.uid()
    )
  );

CREATE POLICY "Users can view own crm updates"
  ON crm_updates FOR SELECT
  USING (auth.uid() = user_id);

-- User Voice Enrollments Policies (migration 017)
ALTER TABLE user_voice_enrollments ENABLE ROW LEVEL SECURITY;

CREATE POLICY user_voice_enrollments_select_own
  ON user_voice_enrollments FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY user_voice_enrollments_insert_own
  ON user_voice_enrollments FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY user_voice_enrollments_update_own
  ON user_voice_enrollments FOR UPDATE
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY user_voice_enrollments_delete_own
  ON user_voice_enrollments FOR DELETE
  USING (auth.uid() = user_id);

-- ============================================
-- FUNCTIONS & TRIGGERS
-- ============================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER user_profiles_updated_at
  BEFORE UPDATE ON user_profiles
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER crm_connections_updated_at
  BEFORE UPDATE ON crm_connections
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER crm_configurations_updated_at
  BEFORE UPDATE ON crm_configurations
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- No trigger for conversations.updated_at: migration 012 never added one
-- (the column has a DEFAULT but nothing bumps it on UPDATE). Not adding one
-- here either - full_reset.sql should match what's actually versioned.

CREATE OR REPLACE FUNCTION set_user_voice_enrollments_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER user_voice_enrollments_updated_at
  BEFORE UPDATE ON user_voice_enrollments
  FOR EACH ROW EXECUTE FUNCTION set_user_voice_enrollments_updated_at();

-- ============================================
-- DONE!
-- ============================================
-- Your database is now completely clean and
-- ready for Vocify.
--
-- Next: Create the "voice-memos" storage bucket
-- (see storage_setup.md)
-- ============================================


