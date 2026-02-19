-- Make audio_url optional (we now store transcript only, no audio storage)
ALTER TABLE memos ALTER COLUMN audio_url DROP NOT NULL;
ALTER TABLE memos ALTER COLUMN audio_url SET DEFAULT '';
