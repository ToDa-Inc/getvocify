-- Whether Vocify drafts follow-up emails for this rep. Off = no draft is generated after a
-- call (FOLLOWUP_ENABLED still decides per company). The rep turns it back on in settings.
-- Rollback: 073_followup_suggestions.down.sql

ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS followup_suggestions BOOLEAN NOT NULL DEFAULT true;
