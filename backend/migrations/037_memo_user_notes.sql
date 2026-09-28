-- Notes the rep types while a meeting records (desktop). They steer the AI summary
-- and are shown back on the memo. NULL when the rep wrote nothing.

ALTER TABLE memos ADD COLUMN IF NOT EXISTS user_notes TEXT;
