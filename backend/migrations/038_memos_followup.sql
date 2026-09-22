-- F02: follow-up draft per memo and the rep's voice samples.
-- Renumbered from PF 037 because 037 is memo capture context.

ALTER TABLE memos
  ADD COLUMN IF NOT EXISTS followup JSONB,
  ADD COLUMN IF NOT EXISTS followup_run_started_at TIMESTAMPTZ;

COMMENT ON COLUMN memos.followup IS
  'Draft lifecycle {status: generating|ready|sent|unavailable, subject, body, final_subject, final_body, edit_ratio, no_edit, channel, run_id, prompt_version, ...}. sent means handoff to the mail client, not confirmed delivery.';
COMMENT ON COLUMN memos.followup_run_started_at IS
  'Non-null while a follow-up generation holds the single-flight lease.';

ALTER TABLE user_profiles
  ADD COLUMN IF NOT EXISTS writing_samples JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN user_profiles.writing_samples IS
  'Last follow-ups the rep reshaped before sending (max 5): few-shot voice for drafts.';
