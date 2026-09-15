-- Private call-recording object path. Signed on GET; never store a public URL.
ALTER TABLE memos ADD COLUMN IF NOT EXISTS recording_path TEXT;
