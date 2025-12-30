-- ============================================
-- VOCIFY DATABASE SCHEMA
-- ============================================
-- This script clears existing data and creates
-- the proper schema for Vocify MVP.
--
-- Run this in your Supabase SQL Editor
-- ============================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- CLEANUP: Drop existing tables and policies
-- ============================================

-- Drop triggers first
DROP TRIGGER IF EXISTS crm_connections_updated_at ON crm_connections;
DROP TRIGGER IF EXISTS user_profiles_updated_at ON user_profiles;

-- Drop functions
DROP FUNCTION IF EXISTS update_updated_at();

-- Drop policies
DROP POLICY IF EXISTS "Users can manage own memos" ON memos;
DROP POLICY IF EXISTS "Users can manage own connections" ON crm_connections;
DROP POLICY IF EXISTS "Users can update own profile" ON user_profiles;
DROP POLICY IF EXISTS "Users can view own profile" ON user_profiles;

-- Drop tables (in reverse dependency order)
DROP TABLE IF EXISTS memos CASCADE;
DROP TABLE IF EXISTS crm_connections CASCADE;
DROP TABLE IF EXISTS user_profiles CASCADE;

-- ============================================
-- CREATE TABLES
-- ============================================

-- 1. USER PROFILES
-- Extends Supabase auth.users
CREATE TABLE user_profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  full_name TEXT,
  company_name TEXT,
  avatar_url TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. CRM CONNECTIONS
-- OAuth connections to CRM providers
CREATE TABLE crm_connections (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  
  provider TEXT NOT NULL CHECK (provider IN ('hubspot', 'salesforce', 'pipedrive')),
  status TEXT NOT NULL DEFAULT 'connected' CHECK (status IN ('connected', 'expired', 'error')),
  
  -- Encrypted tokens (use Supabase Vault in production)
  access_token TEXT NOT NULL,
  refresh_token TEXT,
  token_expires_at TIMESTAMPTZ,
  
  -- Provider-specific metadata
  metadata JSONB DEFAULT '{}',
  
  last_synced_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  
  UNIQUE(user_id, provider)
);

-- 3. VOICE MEMOS
-- The core entity
CREATE TABLE memos (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  
  -- Status lifecycle
  status TEXT NOT NULL DEFAULT 'uploading' CHECK (
    status IN ('uploading', 'transcribing', 'extracting', 'pending_review', 'approved', 'rejected', 'failed')
  ),
  
  -- Audio
  audio_url TEXT NOT NULL,
  audio_duration REAL,  -- seconds
  
  -- Transcription (from Deepgram)
  transcript TEXT,
  transcript_confidence REAL CHECK (transcript_confidence IS NULL OR transcript_confidence BETWEEN 0 AND 1),
  
  -- Extraction (from GPT-5-mini)
  extraction JSONB,
  
  -- Error handling
  error_message TEXT,
  
  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  processed_at TIMESTAMPTZ,
  approved_at TIMESTAMPTZ
);

-- ============================================
-- INDEXES
-- ============================================

-- Memos indexes for common queries
CREATE INDEX idx_memos_user_status ON memos(user_id, status);
CREATE INDEX idx_memos_user_created ON memos(user_id, created_at DESC);

-- ============================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================

-- Enable RLS on all tables
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE crm_connections ENABLE ROW LEVEL SECURITY;
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

-- Memos Policies
CREATE POLICY "Users can manage own memos"
  ON memos FOR ALL
  USING (auth.uid() = user_id);

-- ============================================
-- FUNCTIONS & TRIGGERS
-- ============================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply triggers
CREATE TRIGGER user_profiles_updated_at
  BEFORE UPDATE ON user_profiles
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER crm_connections_updated_at
  BEFORE UPDATE ON crm_connections
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================
-- DONE!
-- ============================================
-- Your database is now ready for Vocify.
-- Next step: Create the "voice-memos" storage bucket
-- in Supabase Storage (make it public for MVP).
-- ============================================


