-- Allow hubspot_call as a valid source value (existing rows use: web, whatsapp)
ALTER TABLE memos DROP CONSTRAINT IF EXISTS memos_source_check;
ALTER TABLE memos ADD CONSTRAINT memos_source_check CHECK (
  source IN ('web', 'voice_memo', 'whatsapp', 'unipile', 'hubspot_call')
);
