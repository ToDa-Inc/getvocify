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
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. CRM CONNECTIONS
CREATE TABLE crm_connections (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  
  provider TEXT NOT NULL CHECK (provider IN ('hubspot', 'salesforce', 'pipedrive')),
  status TEXT NOT NULL DEFAULT 'connected' CHECK (status IN ('connected', 'expired', 'error')),
  
  access_token TEXT NOT NULL,
  refresh_token TEXT,
  token_expires_at TIMESTAMPTZ,
  
  metadata JSONB DEFAULT '{}',
  
  last_synced_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  
  UNIQUE(user_id, provider)
);

ALTER TABLE user_profiles
  ADD COLUMN primary_crm_connection_id UUID REFERENCES crm_connections(id) ON DELETE SET NULL;

-- 3. CRM CONFIGURATIONS
CREATE TABLE crm_configurations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  connection_id UUID NOT NULL REFERENCES crm_connections(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  
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
  audio_duration REAL,
  
  transcript TEXT,
  transcript_confidence REAL CHECK (transcript_confidence IS NULL OR transcript_confidence BETWEEN 0 AND 1),
  
  extraction JSONB,
  
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
  source TEXT DEFAULT 'web' CHECK (source IN ('web', 'voice_memo', 'whatsapp', 'unipile', 'hubspot_call')),
  source_type VARCHAR(50) DEFAULT 'voice_memo',
  whatsapp_message_id TEXT,
  conversation_id UUID,
  hubspot_engagement_id TEXT,
  hubspot_deal_id TEXT,
  hubspot_contact_id TEXT,
  speechmatics_job_id TEXT
);

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
    'create_followup_task'
  )),
  -- 'update_call_outcome' / 'create_followup_task' added by migration 021
  -- (call outcome: Converted/On Hold/Lost - see app/services/hubspot/call_outcome.py).
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

-- CRM Connections Policies
CREATE POLICY "Users can manage own connections"
  ON crm_connections FOR ALL
  USING (auth.uid() = user_id);

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


