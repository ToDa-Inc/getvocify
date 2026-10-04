-- Drops the per-rep follow-up switch; every rep gets drafts again (company flag permitting).

ALTER TABLE user_profiles DROP COLUMN IF EXISTS followup_suggestions;
