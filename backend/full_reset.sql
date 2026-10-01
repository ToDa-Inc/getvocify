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

  -- F14 (migration 052): stage for a saved booked meeting. NULL = never move a stage.
  meeting_booked_pipeline_id TEXT,
  meeting_booked_stage_id TEXT,
  CONSTRAINT crm_configurations_meeting_booked_stage_check
    CHECK (meeting_booked_stage_id IS NULL OR meeting_booked_pipeline_id IS NOT NULL),

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
  user_notes TEXT,
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
  -- Migration 055: the type's business objective (reserved: the app computes the default).
  goal TEXT,
  -- 066_playbooks_v2: the type's name and the rule for which calls it applies to, the on/off
  -- switch (it never touches active_version_id) and the soft delete.
  label TEXT,
  applies_to JSONB,
  state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'paused')),
  archived_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (company_id, sales_motion_key)
);

CREATE TABLE IF NOT EXISTS playbook_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  playbook_id UUID NOT NULL REFERENCES playbooks(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published')),
  steps JSONB NOT NULL DEFAULT '[]'::jsonb,
  entries JSONB NOT NULL DEFAULT '[]'::jsonb,
  qualification JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
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

CREATE OR REPLACE FUNCTION save_ask_turn(
  p_company UUID,
  p_user UUID,
  p_conversation TEXT,
  p_client_turn TEXT,
  p_text TEXT
) RETURNS TABLE (turn_id TEXT, body TEXT, replayed BOOLEAN)
LANGUAGE plpgsql
AS $save_ask$
DECLARE
  existing_id TEXT;
  new_id TEXT;
BEGIN
  SELECT id INTO existing_id
  FROM copilot_web_turns
  WHERE user_id = p_user
    AND conversation_id = p_conversation
    AND client_turn_id = p_client_turn;

  IF existing_id IS NOT NULL THEN
    RETURN QUERY
    SELECT t.id, t.body, true
    FROM copilot_web_turns t
    WHERE t.id = existing_id;
    RETURN;
  END IF;

  BEGIN
    new_id := gen_random_uuid()::text;
    INSERT INTO copilot_web_turns (
      id, company_id, user_id, conversation_id, client_turn_id, status, body
    )
    VALUES (new_id, p_company, p_user, p_conversation, p_client_turn, 'pending', p_text);
    RETURN QUERY SELECT new_id, p_text, false;
  EXCEPTION WHEN unique_violation THEN
    RETURN QUERY
    SELECT t.id, t.body, true
    FROM copilot_web_turns t
    WHERE t.user_id = p_user
      AND t.conversation_id = p_conversation
      AND t.client_turn_id = p_client_turn;
  END;
END;
$save_ask$;

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
  stage_changed BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_meeting_writes_created_at
  ON meeting_writes (created_at)
  WHERE stage_changed;

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

-- F13.04 / migration 053: per-person report opt-outs. No row = all on. Service role only.
CREATE TABLE IF NOT EXISTS report_preferences (
  user_id UUID PRIMARY KEY,
  daily_enabled BOOLEAN NOT NULL DEFAULT true,
  weekly_enabled BOOLEAN NOT NULL DEFAULT true,
  team_enabled BOOLEAN NOT NULL DEFAULT true,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE report_preferences ENABLE ROW LEVEL SECURITY;

-- Migration 070: a rep's connected calendar (Recall.ai Calendar V2) and their switch for
-- whether the Vocify bot joins their meetings. One per rep. Service role only.
CREATE TABLE IF NOT EXISTS calendar_connections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  platform TEXT NOT NULL CHECK (platform IN ('google_calendar', 'microsoft_outlook')),
  recall_calendar_id UUID NOT NULL UNIQUE,
  email TEXT,
  status TEXT NOT NULL DEFAULT 'connecting' CHECK (status IN ('connecting', 'connected', 'disconnected')),
  auto_join BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE calendar_connections ENABLE ROW LEVEL SECURITY;

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

-- Migration 066_playbooks_v2 (everything of the playbooks feature that is not a table above): the
-- company knowledge table, the updated_at triggers, the playbooks_live view and the SQL functions.
-- Kept identical to migrations/066_playbooks_v2.sql (tests/playbooks/test_migration_066.py checks it).
CREATE TABLE IF NOT EXISTS company_sales_knowledge (
  company_id UUID PRIMARY KEY,
  data JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_id TEXT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─── updated_at triggers ────────────────────────────────────────────────────────────────────
-- Strictly later than the row's previous value (by more than the millisecond the stale checks compare
-- at), so two quick saves never share a timestamp.

CREATE OR REPLACE FUNCTION playbook_versions_touch_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $touch$
BEGIN
  NEW.updated_at = GREATEST(clock_timestamp(), OLD.updated_at + interval '2 milliseconds');
  RETURN NEW;
END;
$touch$;

DROP TRIGGER IF EXISTS playbook_versions_updated_at ON playbook_versions;
CREATE TRIGGER playbook_versions_updated_at
  BEFORE UPDATE ON playbook_versions
  FOR EACH ROW EXECUTE FUNCTION playbook_versions_touch_updated_at();

CREATE OR REPLACE FUNCTION company_sales_knowledge_touch_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $touch$
BEGIN
  NEW.updated_at = GREATEST(clock_timestamp(), OLD.updated_at + interval '2 milliseconds');
  RETURN NEW;
END;
$touch$;

DROP TRIGGER IF EXISTS company_sales_knowledge_updated_at ON company_sales_knowledge;
CREATE TRIGGER company_sales_knowledge_updated_at
  BEFORE UPDATE ON company_sales_knowledge
  FOR EACH ROW EXECUTE FUNCTION company_sales_knowledge_touch_updated_at();

-- ─── playbooks_live: what applies to a call ─────────────────────────────────────────────────

CREATE OR REPLACE VIEW playbooks_live AS
SELECT
  p.id AS playbook_id,
  p.company_id,
  p.sales_motion_key,
  p.active_version_id AS version_id
FROM playbooks p
WHERE p.active_version_id IS NOT NULL
  AND p.state = 'active'
  AND p.archived_at IS NULL;

-- ─── helpers ────────────────────────────────────────────────────────────────────────────────

-- The pending draft of a playbook: its latest draft row, when it is newer than the active version (or there
-- is no active version). An older draft left behind (by an earlier publish, or by the one-row-per-save era)
-- is not "the draft".
CREATE OR REPLACE FUNCTION playbook_pending_draft(p_playbook UUID)
RETURNS UUID
LANGUAGE sql
STABLE
AS $pending$
  SELECT v.id
  FROM playbook_versions v
  WHERE v.playbook_id = p_playbook
    AND v.status = 'draft'
    AND (
      NOT EXISTS (
        SELECT 1 FROM playbooks p WHERE p.id = p_playbook AND p.active_version_id IS NOT NULL
      )
      OR v.created_at > (
        SELECT a.created_at
        FROM playbooks p JOIN playbook_versions a ON a.id = p.active_version_id
        WHERE p.id = p_playbook
      )
    )
  ORDER BY v.created_at DESC
  LIMIT 1;
$pending$;

-- A deleted type that is written to again comes back empty: the old published version is not resurrected
-- (it stays as a row nothing points at) and the old drafts were deleted with it.
CREATE OR REPLACE FUNCTION playbook_unarchive(p_playbook UUID)
RETURNS VOID
LANGUAGE sql
AS $unarchive$
  UPDATE playbooks
  SET archived_at = NULL, active_version_id = NULL, state = 'active'
  WHERE id = p_playbook AND archived_at IS NOT NULL;
$unarchive$;

-- A source document ({id, kind, name}) of the company; NULL for anything else.
CREATE OR REPLACE FUNCTION playbook_source_view(p_company UUID, p_source_id TEXT)
RETURNS JSONB
LANGUAGE sql
STABLE
AS $source_view$
  SELECT jsonb_build_object('id', i.id, 'kind', i.kind, 'name', COALESCE(i.draft->>'name', ''))
  FROM playbook_imports i
  WHERE i.id = p_source_id
    AND p_source_id LIKE 'source:%'
    AND i.company_id = p_company;
$source_view$;

CREATE OR REPLACE FUNCTION playbook_version_json(p_version UUID)
RETURNS JSONB
LANGUAGE sql
STABLE
AS $version_json$
  SELECT jsonb_build_object(
    'id', v.id, 'status', v.status, 'steps', v.steps, 'entries', v.entries,
    'qualification', v.qualification, 'created_at', v.created_at, 'updated_at', v.updated_at
  )
  FROM playbook_versions v
  WHERE v.id = p_version;
$version_json$;

-- ─── the 040 functions, updated ─────────────────────────────────────────────────────────────

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
  -- Publishing turns the playbook on and lifts a delete.
  UPDATE playbooks
  SET active_version_id = p_version, state = 'active', archived_at = NULL
  WHERE id = pb;
  RETURN p_version;
END;
$$;

-- The legacy text import (POST /playbooks/imports): a draft made of the whole document. Idempotent per import id.
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
  WHERE company_id = p_company AND sales_motion_key = p_motion
  FOR UPDATE;

  PERFORM playbook_unarchive(pb);

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

-- Publishes the pending draft. Returns 'published:<version id>'.
-- Raises: not_a_draft (no such type, deleted, or nothing pending), contradiction.
CREATE OR REPLACE FUNCTION publish_playbook_motion(p_company UUID, p_motion TEXT)
RETURNS TEXT
LANGUAGE plpgsql
AS $publish_motion$
DECLARE
  pb playbooks%ROWTYPE;
  ver UUID;
BEGIN
  SELECT * INTO pb FROM playbooks
  WHERE company_id = p_company AND sales_motion_key = p_motion
  FOR UPDATE;

  IF NOT FOUND OR pb.archived_at IS NOT NULL THEN
    RAISE EXCEPTION 'not_a_draft';
  END IF;

  IF EXISTS (
    SELECT 1 FROM playbook_imports i
    WHERE i.playbook_id = pb.id
      AND COALESCE(jsonb_array_length(i.draft->'contradictions'), 0) > 0
      AND i.created_at = (
        SELECT max(created_at) FROM playbook_imports WHERE playbook_id = pb.id
      )
  ) THEN
    RAISE EXCEPTION 'contradiction';
  END IF;

  ver := playbook_pending_draft(pb.id);
  IF ver IS NULL THEN
    RAISE EXCEPTION 'not_a_draft';
  END IF;

  PERFORM publish_playbook_version(ver);
  RETURN 'published:' || ver::text;
END;
$publish_motion$;

-- Status per type: published | paused (published, switched off) | draft | missing. Deleted types are not there;
-- a type that only lives in interaction_types (no playbooks row) is 'missing'.
CREATE OR REPLACE FUNCTION list_playbook_motions(p_company UUID)
RETURNS TABLE (sales_motion_key TEXT, motion_status TEXT)
LANGUAGE sql
STABLE
AS $list_motions$
  SELECT motion_key AS sales_motion_key, motion_status
  FROM (
    SELECT p.sales_motion_key AS motion_key,
      CASE
        WHEN p.active_version_id IS NOT NULL AND p.state = 'paused' THEN 'paused'
        WHEN p.active_version_id IS NOT NULL THEN 'published'
        WHEN EXISTS (
          SELECT 1 FROM playbook_versions v
          WHERE v.playbook_id = p.id AND v.status = 'draft'
        ) THEN 'draft'
        ELSE 'missing'
      END AS motion_status
    FROM playbooks p
    WHERE p.company_id = p_company
      AND p.archived_at IS NULL
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

-- Adds a type (or turns a deleted one back on, empty). Returns the key. Raises: empty_type.
CREATE OR REPLACE FUNCTION add_interaction_type(p_company UUID, p_key TEXT, p_name TEXT)
RETURNS TEXT
LANGUAGE plpgsql
AS $add_type$
BEGIN
  IF btrim(p_key) = '' THEN
    RAISE EXCEPTION 'empty_type';
  END IF;
  INSERT INTO interaction_types (company_id, type_key, name)
  VALUES (p_company, btrim(p_key), COALESCE(NULLIF(btrim(p_name), ''), btrim(p_key)))
  ON CONFLICT (company_id, type_key) DO UPDATE SET active = true;
  -- Creating a deleted type again brings it back empty: the old version is not resurrected.
  PERFORM playbook_unarchive(id)
  FROM playbooks
  WHERE company_id = p_company AND sales_motion_key = btrim(p_key);
  RETURN btrim(p_key);
END;
$add_type$;

-- ─── writes ─────────────────────────────────────────────────────────────────────────────────

-- The name and/or the rule of a type. p_meta carries only the keys to set: {"label": text|null,
-- "applies_to": object|null}. Creates the playbooks row when the type has none (listed as 'missing'). Returns the key.
CREATE OR REPLACE FUNCTION playbook_set_meta(p_company UUID, p_motion TEXT, p_meta JSONB)
RETURNS TEXT
LANGUAGE plpgsql
AS $set_meta$
BEGIN
  INSERT INTO playbooks (company_id, sales_motion_key)
  VALUES (p_company, p_motion)
  ON CONFLICT (company_id, sales_motion_key) DO NOTHING;

  UPDATE playbooks
  SET label = CASE WHEN p_meta ? 'label' THEN NULLIF(p_meta->>'label', '') ELSE label END,
      applies_to = CASE WHEN p_meta ? 'applies_to' THEN NULLIF(p_meta->'applies_to', 'null'::jsonb) ELSE applies_to END
  WHERE company_id = p_company AND sales_motion_key = p_motion;
  RETURN p_motion;
END;
$set_meta$;

-- add_interaction_type plus, in the same transaction, the type's name and rule when p_meta is given.
-- Returns the key. Raises: empty_type.
CREATE OR REPLACE FUNCTION playbook_add_type(p_company UUID, p_key TEXT, p_name TEXT, p_meta JSONB DEFAULT NULL)
RETURNS TEXT
LANGUAGE plpgsql
AS $add_playbook_type$
DECLARE
  k TEXT := btrim(COALESCE(p_key, ''));
BEGIN
  PERFORM add_interaction_type(p_company, k, p_name);
  IF p_meta IS NOT NULL AND jsonb_typeof(p_meta) = 'object' THEN
    PERFORM playbook_set_meta(p_company, k, p_meta);
  END IF;
  RETURN k;
END;
$add_playbook_type$;

-- Saves the editor's draft of a type and returns the saved playbook_versions row.
--   * The playbook row is created if needed; a deleted one is un-archived first (empty, switched on).
--   * A pending draft is UPDATED in place (same version id, autosave keeps one row). The conflict check is
--     part of that UPDATE: WHERE updated_at = p_base_updated_at. Otherwise a new draft is inserted; with a
--     base given that must be the active version's updated_at (a first save over a live version).
--   * p_qualification NULL leaves the draft's criteria as they are; a new draft starts from the live one's.
--   * p_source_id is kept only if it is a source document of this company.
--   * The draft has ONE import row (kind 'editor', id editor:<version id>, no contradictions), created with
--     it and rewritten by later saves; it becomes the playbook's latest import, so a contradictory legacy
--     import stops blocking publishing once the editor has saved over it. p_text is the plain-text copy
--     the caller renders for it (audit).
-- Raises: stale_draft.
CREATE OR REPLACE FUNCTION playbook_save_draft(
  p_company UUID,
  p_motion TEXT,
  p_steps JSONB,
  p_entries JSONB,
  p_qualification JSONB,
  p_source_id TEXT,
  p_base_updated_at TIMESTAMPTZ,
  p_text TEXT DEFAULT NULL
) RETURNS playbook_versions
LANGUAGE plpgsql
AS $save_draft_v2$
DECLARE
  pb playbooks%ROWTYPE;
  live playbook_versions%ROWTYPE;
  pending UUID;
  v playbook_versions%ROWTYPE;
  src TEXT := NULL;
  prior JSONB;
  had_import BOOLEAN;
  effective TEXT;
  import_draft JSONB;
BEGIN
  INSERT INTO playbooks (company_id, sales_motion_key)
  VALUES (p_company, p_motion)
  ON CONFLICT (company_id, sales_motion_key) DO NOTHING;

  -- The playbook row serializes every save of this type.
  SELECT * INTO pb FROM playbooks
  WHERE company_id = p_company AND sales_motion_key = p_motion
  FOR UPDATE;

  IF pb.archived_at IS NOT NULL THEN
    PERFORM playbook_unarchive(pb.id);
    SELECT * INTO pb FROM playbooks WHERE id = pb.id;
  END IF;

  IF p_source_id IS NOT NULL AND playbook_source_view(p_company, p_source_id) IS NOT NULL THEN
    src := p_source_id;
  END IF;

  SELECT * INTO live FROM playbook_versions WHERE id = pb.active_version_id;
  pending := playbook_pending_draft(pb.id);

  IF pending IS NOT NULL THEN
    UPDATE playbook_versions
    SET steps = p_steps,
        entries = p_entries,
        qualification = COALESCE(p_qualification, qualification)
    WHERE id = pending
      AND status = 'draft'
      AND (
        p_base_updated_at IS NULL
        OR date_trunc('milliseconds', updated_at) = date_trunc('milliseconds', p_base_updated_at)
      )
    RETURNING * INTO v;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'stale_draft';
    END IF;
  ELSE
    IF p_base_updated_at IS NOT NULL AND (
      live.id IS NULL
      OR date_trunc('milliseconds', live.updated_at) <> date_trunc('milliseconds', p_base_updated_at)
    ) THEN
      RAISE EXCEPTION 'stale_draft';
    END IF;
    INSERT INTO playbook_versions (playbook_id, status, steps, entries, qualification)
    VALUES (pb.id, 'draft', p_steps, p_entries, COALESCE(p_qualification, live.qualification, '[]'::jsonb))
    RETURNING * INTO v;
  END IF;

  SELECT draft INTO prior FROM playbook_imports WHERE id = 'editor:' || v.id;
  had_import := FOUND;
  effective := COALESCE(src, prior->>'source_id');
  IF effective IS NULL AND NOT had_import AND live.id IS NOT NULL THEN
    -- The first edit over a published version keeps pointing at its source.
    SELECT draft->>'source_id' INTO effective FROM playbook_imports WHERE id = 'editor:' || live.id;
  END IF;
  import_draft := jsonb_build_object(
    'text', COALESCE(p_text, ''),
    'source_ref', 'editor',
    'contradictions', '[]'::jsonb,
    'version_id', v.id
  );
  IF effective IS NOT NULL THEN
    import_draft := import_draft || jsonb_build_object('source_id', effective);
  END IF;
  INSERT INTO playbook_imports (id, company_id, playbook_id, kind, status, draft, active_version_id, created_at)
  VALUES ('editor:' || v.id, p_company, pb.id, 'editor', 'ready', import_draft, pb.active_version_id, clock_timestamp())
  ON CONFLICT (id) DO UPDATE SET draft = EXCLUDED.draft, created_at = EXCLUDED.created_at;

  RETURN v;
END;
$save_draft_v2$;

-- Deletes the pending drafts (every draft newer than the active version, or all of them when there is none)
-- and their editor import rows. Published versions and source documents stay. Returns whether anything was deleted.
CREATE OR REPLACE FUNCTION playbook_discard_draft(p_company UUID, p_motion TEXT)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $discard$
DECLARE
  pb playbooks%ROWTYPE;
  ids UUID[];
BEGIN
  SELECT * INTO pb FROM playbooks
  WHERE company_id = p_company AND sales_motion_key = p_motion
  FOR UPDATE;
  IF NOT FOUND THEN
    RETURN false;
  END IF;

  SELECT COALESCE(array_agg(v.id), ARRAY[]::UUID[]) INTO ids
  FROM playbook_versions v
  WHERE v.playbook_id = pb.id
    AND v.status = 'draft'
    AND (
      pb.active_version_id IS NULL
      OR v.created_at > (SELECT a.created_at FROM playbook_versions a WHERE a.id = pb.active_version_id)
    );
  IF cardinality(ids) = 0 THEN
    RETURN false;
  END IF;

  DELETE FROM playbook_imports
  WHERE kind = 'editor' AND id IN (SELECT 'editor:' || x FROM unnest(ids) AS x);
  DELETE FROM playbook_versions WHERE id = ANY(ids) AND status = 'draft';
  RETURN true;
END;
$discard$;

-- The on/off switch and the soft delete of a type. p_action:
--   pause    (raises not_published unless there is an active version and the playbook is on)
--   resume   (raises not_paused unless it is paused)
--   archive  ("Eliminar": deletes the pending drafts and their editor imports, sets archived_at, turns the
--            interaction type off; works for a type that only lives in interaction_types; raises not_found
--            when the company has neither)
--   restore  (raises not_archived unless it is deleted; clears archived_at and turns the interaction type
--            on; `state` is untouched, so a paused one comes back paused and an active one active)
-- Returns the action that was applied.
CREATE OR REPLACE FUNCTION playbook_set_state(p_company UUID, p_motion TEXT, p_action TEXT)
RETURNS TEXT
LANGUAGE plpgsql
AS $set_state$
DECLARE
  pb playbooks%ROWTYPE;
  has_row BOOLEAN;
BEGIN
  IF p_action NOT IN ('pause', 'resume', 'archive', 'restore') THEN
    RAISE EXCEPTION 'invalid_action';
  END IF;

  SELECT * INTO pb FROM playbooks
  WHERE company_id = p_company AND sales_motion_key = p_motion
  FOR UPDATE;
  has_row := FOUND;

  IF p_action = 'pause' THEN
    IF NOT has_row OR pb.archived_at IS NOT NULL OR pb.active_version_id IS NULL OR pb.state <> 'active' THEN
      RAISE EXCEPTION 'not_published';
    END IF;
    UPDATE playbooks SET state = 'paused' WHERE id = pb.id;

  ELSIF p_action = 'resume' THEN
    IF NOT has_row OR pb.archived_at IS NOT NULL OR pb.active_version_id IS NULL OR pb.state <> 'paused' THEN
      RAISE EXCEPTION 'not_paused';
    END IF;
    UPDATE playbooks SET state = 'active' WHERE id = pb.id;

  ELSIF p_action = 'archive' THEN
    IF has_row AND pb.archived_at IS NULL THEN
      -- Drafts and their import rows first: a half-done delete would leave nothing hidden.
      DELETE FROM playbook_imports
      WHERE kind = 'editor'
        AND id IN (SELECT 'editor:' || v.id FROM playbook_versions v WHERE v.playbook_id = pb.id AND v.status = 'draft');
      DELETE FROM playbook_versions WHERE playbook_id = pb.id AND status = 'draft';
      UPDATE playbooks SET archived_at = now() WHERE id = pb.id;
    ELSIF has_row OR NOT EXISTS (
      SELECT 1 FROM interaction_types t
      WHERE t.company_id = p_company AND t.type_key = p_motion AND t.active
    ) THEN
      RAISE EXCEPTION 'not_found';
    END IF;
    UPDATE interaction_types SET active = false WHERE company_id = p_company AND type_key = p_motion;

  ELSE
    IF has_row THEN
      IF pb.archived_at IS NULL THEN
        RAISE EXCEPTION 'not_archived';
      END IF;
      UPDATE playbooks SET archived_at = NULL WHERE id = pb.id;
    ELSIF NOT EXISTS (
      SELECT 1 FROM interaction_types t
      WHERE t.company_id = p_company AND t.type_key = p_motion AND NOT t.active
    ) THEN
      RAISE EXCEPTION 'not_archived';
    END IF;
    UPDATE interaction_types SET active = true WHERE company_id = p_company AND type_key = p_motion;
  END IF;

  RETURN p_action;
END;
$set_state$;

-- What Vocify knows about the company (no draft: a save takes effect at once). The caller sends the data
-- already normalized. p_source_id NULL keeps the saved one. With p_base_updated_at the check is part of the
-- write: it applies only if the row still has that updated_at, and a base with no row is stale too.
-- Returns the saved row. Raises: stale_knowledge.
CREATE OR REPLACE FUNCTION company_knowledge_save(
  p_company UUID,
  p_data JSONB,
  p_source_id TEXT,
  p_base_updated_at TIMESTAMPTZ
) RETURNS company_sales_knowledge
LANGUAGE plpgsql
AS $knowledge_save$
DECLARE
  k company_sales_knowledge%ROWTYPE;
BEGIN
  IF p_base_updated_at IS NULL THEN
    INSERT INTO company_sales_knowledge (company_id, data, source_id)
    VALUES (p_company, COALESCE(p_data, '{}'::jsonb), p_source_id)
    ON CONFLICT (company_id) DO UPDATE
    SET data = EXCLUDED.data,
        source_id = COALESCE(EXCLUDED.source_id, company_sales_knowledge.source_id)
    RETURNING * INTO k;
  ELSE
    UPDATE company_sales_knowledge
    SET data = COALESCE(p_data, '{}'::jsonb),
        source_id = COALESCE(p_source_id, source_id)
    WHERE company_id = p_company
      AND date_trunc('milliseconds', updated_at) = date_trunc('milliseconds', p_base_updated_at)
    RETURNING * INTO k;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'stale_knowledge';
    END IF;
  END IF;
  RETURN k;
END;
$knowledge_save$;

-- One input for the whole company, in ONE transaction: every detected type's draft (playbook_save_draft) and
-- the company knowledge (already merged by the caller; NULL = none). If anything fails nothing is saved.
-- p_types: [{key, steps, entries, qualification (null = keep), text, ensure: {name, meta} (optional)}].
-- `ensure` creates the type first when the company does not have it yet (a catalog type found in the document).
-- Returns {types: [{sales_motion_key, version_id}], knowledge: row | null}. Raises: invalid_type_item.
CREATE OR REPLACE FUNCTION playbook_intake_save(
  p_company UUID,
  p_types JSONB,
  p_knowledge JSONB,
  p_source_id TEXT
) RETURNS JSONB
LANGUAGE plpgsql
AS $intake_save$
DECLARE
  item JSONB;
  ensure JSONB;
  v playbook_versions%ROWTYPE;
  saved JSONB := '[]'::jsonb;
  k company_sales_knowledge%ROWTYPE;
  knowledge JSONB := NULL;
BEGIN
  FOR item IN SELECT value FROM jsonb_array_elements(COALESCE(p_types, '[]'::jsonb))
  LOOP
    IF jsonb_typeof(item) <> 'object'
       OR COALESCE(btrim(item->>'key'), '') = ''
       OR jsonb_typeof(item->'steps') IS DISTINCT FROM 'array'
       OR jsonb_typeof(item->'entries') IS DISTINCT FROM 'array' THEN
      RAISE EXCEPTION 'invalid_type_item';
    END IF;

    ensure := item->'ensure';
    IF ensure IS NOT NULL AND jsonb_typeof(ensure) = 'object' AND NOT EXISTS (
      SELECT 1 FROM list_playbook_motions(p_company) l WHERE l.sales_motion_key = item->>'key'
    ) THEN
      PERFORM playbook_add_type(p_company, item->>'key', COALESCE(ensure->>'name', item->>'key'), ensure->'meta');
    END IF;

    v := playbook_save_draft(
      p_company,
      item->>'key',
      item->'steps',
      item->'entries',
      CASE WHEN jsonb_typeof(item->'qualification') = 'array' THEN item->'qualification' ELSE NULL END,
      p_source_id,
      NULL,
      item->>'text'
    );
    saved := saved || jsonb_build_array(jsonb_build_object('sales_motion_key', item->>'key', 'version_id', v.id));
  END LOOP;

  IF p_knowledge IS NOT NULL AND jsonb_typeof(p_knowledge) = 'object' THEN
    k := company_knowledge_save(p_company, p_knowledge, p_source_id, NULL);
    knowledge := to_jsonb(k);
  END IF;

  RETURN jsonb_build_object('types', saved, 'knowledge', knowledge);
END;
$intake_save$;

-- Keeps the original material a playbook was structured from (an import row, id source:<uuid>). Creates no
-- version. p_motion NULL = a document for the whole company: no playbooks row is created for it (that would
-- list a phantom call type). Returns {id, kind, name}.
CREATE OR REPLACE FUNCTION playbook_source_save(
  p_company UUID,
  p_motion TEXT,
  p_kind TEXT,
  p_name TEXT,
  p_text TEXT
) RETURNS JSONB
LANGUAGE plpgsql
AS $source_save$
DECLARE
  pb playbooks%ROWTYPE;
  sid TEXT := 'source:' || gen_random_uuid()::text;
BEGIN
  IF p_motion IS NOT NULL THEN
    INSERT INTO playbooks (company_id, sales_motion_key)
    VALUES (p_company, p_motion)
    ON CONFLICT (company_id, sales_motion_key) DO NOTHING;
    SELECT * INTO pb FROM playbooks WHERE company_id = p_company AND sales_motion_key = p_motion;
  END IF;
  INSERT INTO playbook_imports (id, company_id, playbook_id, kind, status, draft, active_version_id)
  VALUES (
    sid, p_company, pb.id, p_kind, 'ready',
    jsonb_build_object('text', p_text, 'name', COALESCE(p_name, ''), 'source_ref', p_kind || ':' || sid),
    pb.active_version_id
  );
  RETURN jsonb_build_object('id', sid, 'kind', p_kind, 'name', COALESCE(p_name, ''));
END;
$source_save$;

-- ─── reads (jsonb, so the repository needs nothing but rpc) ─────────────────────────────────

-- The types of the company, one entry each: {key, status, label, applies_to, has_draft, paused, version}.
-- `version` is the one the editor opens: the pending draft when p_include_draft (managers), else the
-- active version (also when it is paused); null when the type has neither. has_draft is false for a rep.
CREATE OR REPLACE FUNCTION playbook_overview(p_company UUID, p_include_draft BOOLEAN DEFAULT true)
RETURNS JSONB
LANGUAGE sql
STABLE
AS $overview$
  SELECT COALESCE(jsonb_agg(entry ORDER BY entry->>'key'), '[]'::jsonb)
  FROM (
    SELECT jsonb_build_object(
      'key', l.sales_motion_key,
      'status', l.motion_status,
      'label', p.label,
      'applies_to', p.applies_to,
      'has_draft', p_include_draft AND pend.id IS NOT NULL,
      'paused', l.motion_status = 'paused',
      'version', CASE
        WHEN p_include_draft AND pend.id IS NOT NULL THEN playbook_version_json(pend.id)
        WHEN p.active_version_id IS NOT NULL THEN playbook_version_json(p.active_version_id)
        ELSE NULL
      END
    ) AS entry
    FROM list_playbook_motions(p_company) l
    LEFT JOIN playbooks p
      ON p.company_id = p_company AND p.sales_motion_key = l.sales_motion_key
    LEFT JOIN LATERAL (SELECT playbook_pending_draft(p.id) AS id) pend ON true
  ) entries;
$overview$;

-- What the editor shows for one type: {state, version, has_live, source, paused}. state is 'draft' (the
-- pending draft, only when p_include_draft), 'published' (the active version, also when paused) or 'empty'
-- (also for a deleted type). source = the material the shown version was structured from, or null.
CREATE OR REPLACE FUNCTION playbook_editor(p_company UUID, p_motion TEXT, p_include_draft BOOLEAN DEFAULT true)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
AS $editor$
DECLARE
  pb playbooks%ROWTYPE;
  pend UUID := NULL;
  shown UUID := NULL;
  st TEXT := 'empty';
  recorded TEXT;
BEGIN
  SELECT * INTO pb FROM playbooks
  WHERE company_id = p_company AND sales_motion_key = p_motion;
  IF NOT FOUND OR pb.archived_at IS NOT NULL THEN
    RETURN jsonb_build_object('state', 'empty', 'version', NULL, 'has_live', false, 'source', NULL, 'paused', false);
  END IF;

  IF p_include_draft THEN
    pend := playbook_pending_draft(pb.id);
  END IF;
  IF pend IS NOT NULL THEN
    st := 'draft';
    shown := pend;
  ELSIF pb.active_version_id IS NOT NULL THEN
    st := 'published';
    shown := pb.active_version_id;
  END IF;

  IF shown IS NOT NULL THEN
    SELECT draft->>'source_id' INTO recorded FROM playbook_imports WHERE id = 'editor:' || shown;
  END IF;

  RETURN jsonb_build_object(
    'state', st,
    'version', CASE WHEN shown IS NULL THEN NULL ELSE playbook_version_json(shown) END,
    'has_live', pb.active_version_id IS NOT NULL,
    'source', CASE WHEN recorded IS NULL THEN NULL ELSE playbook_source_view(p_company, recorded) END,
    'paused', pb.active_version_id IS NOT NULL AND pb.state = 'paused'
  );
END;
$editor$;

CREATE OR REPLACE FUNCTION playbook_source_get(p_company UUID, p_source_id TEXT)
RETURNS JSONB
LANGUAGE sql
STABLE
AS $source_get$
  SELECT playbook_source_view(p_company, p_source_id);
$source_get$;

CREATE OR REPLACE FUNCTION playbook_import_get(p_company UUID, p_import TEXT)
RETURNS JSONB
LANGUAGE sql
STABLE
AS $import_get$
  SELECT jsonb_build_object(
    'id', i.id, 'import_id', i.id, 'kind', i.kind, 'status', i.status, 'draft', i.draft,
    'active_version_id', i.active_version_id, 'published', false
  )
  FROM playbook_imports i
  WHERE i.id = p_import AND i.company_id = p_company;
$import_get$;

CREATE OR REPLACE FUNCTION company_knowledge_get(p_company UUID)
RETURNS JSONB
LANGUAGE sql
STABLE
AS $knowledge_get$
  SELECT jsonb_build_object('data', k.data, 'source_id', k.source_id, 'updated_at', k.updated_at)
  FROM company_sales_knowledge k
  WHERE k.company_id = p_company;
$knowledge_get$;

-- ============================================
-- DONE!
-- ============================================
-- Your database is now completely clean and
-- ready for Vocify.
--
-- Next: Create the "voice-memos" storage bucket
-- (see storage_setup.md)
-- ============================================


