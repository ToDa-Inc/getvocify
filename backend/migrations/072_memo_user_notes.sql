-- Notes the rep types while a meeting records (desktop). They steer the AI summary
-- and are shown back on the memo. NULL when the rep wrote nothing.
-- Rollback: 072_memo_user_notes.down.sql

ALTER TABLE memos ADD COLUMN IF NOT EXISTS user_notes TEXT;
