-- Migration: Add upsert_company and upsert_contact to crm_updates action_type check
-- Purpose: Fix 500 error when approving sync - constraint was blocking these action types
-- Date: 2026-02-17
--
-- Run this in your Supabase SQL Editor

-- Drop the existing check constraint (name from error: crm_updates_action_type_check)
ALTER TABLE crm_updates
DROP CONSTRAINT IF EXISTS crm_updates_action_type_check;

-- Add new constraint with all action types used by the sync service
ALTER TABLE crm_updates
ADD CONSTRAINT crm_updates_action_type_check
CHECK (action_type IN (
  'create_deal',
  'update_deal',
  'upsert_company',
  'upsert_contact'
));
