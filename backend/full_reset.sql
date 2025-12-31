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
  
  -- Behavior settings
  auto_create_contacts BOOLEAN DEFAULT true,
  auto_create_companies BOOLEAN DEFAULT true,
  
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  
  UNIQUE(connection_id)
);

-- 4. CRM SCHEMAS CACHE
CREATE TABLE crm_schemas (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  connection_id UUID NOT NULL REFERENCES crm_connections(id) ON DELETE CASCADE,
  object_type TEXT NOT NULL CHECK (object_type IN ('deals', 'contacts', 'companies')),
  
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
    status IN ('uploading', 'transcribing', 'extracting', 'pending_review', 'approved', 'rejected', 'failed')
  ),
  
  audio_url TEXT NOT NULL,
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
  approved_at TIMESTAMPTZ
);

-- ============================================
-- INDEXES
-- ============================================

CREATE INDEX idx_memos_user_status ON memos(user_id, status);
CREATE INDEX idx_memos_user_created ON memos(user_id, created_at DESC);
CREATE INDEX idx_crm_configurations_user ON crm_configurations(user_id);
CREATE INDEX idx_crm_configurations_connection ON crm_configurations(connection_id);
CREATE INDEX idx_crm_schemas_connection ON crm_schemas(connection_id);

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

-- ============================================
-- DONE!
-- ============================================
-- Your database is now completely clean and
-- ready for Vocify.
--
-- Next: Create the "voice-memos" storage bucket
-- (see storage_setup.md)
-- ============================================


