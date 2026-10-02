-- Drops the rep's meeting notes. Notes already written are lost.

ALTER TABLE memos DROP COLUMN IF EXISTS user_notes;
