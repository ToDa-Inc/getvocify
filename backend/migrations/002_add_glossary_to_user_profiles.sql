-- Add glossary column to user_profiles
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS glossary JSONB DEFAULT '[]';

-- Update RLS for user_profiles to ensure users can manage their own profile (already exists but ensuring)
-- Policies are already in schema.sql, just adding the column is enough.
