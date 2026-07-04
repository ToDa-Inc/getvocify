-- HubSpot call recording memos + align memos with code (WhatsApp columns, pending_transcript status)

ALTER TABLE memos ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'voice_memo';
ALTER TABLE memos ADD COLUMN IF NOT EXISTS hubspot_engagement_id TEXT;
ALTER TABLE memos ADD COLUMN IF NOT EXISTS hubspot_deal_id TEXT;
ALTER TABLE memos ADD COLUMN IF NOT EXISTS hubspot_contact_id TEXT;
ALTER TABLE memos ADD COLUMN IF NOT EXISTS whatsapp_message_id TEXT;
ALTER TABLE memos ADD COLUMN IF NOT EXISTS conversation_id TEXT;
ALTER TABLE memos ADD COLUMN IF NOT EXISTS source_type TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_memos_hubspot_engagement_id_unique
  ON memos (hubspot_engagement_id)
  WHERE hubspot_engagement_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_memos_hubspot_deal_created
  ON memos (hubspot_deal_id, created_at DESC)
  WHERE hubspot_deal_id IS NOT NULL;

ALTER TABLE memos DROP CONSTRAINT IF EXISTS memos_status_check;
ALTER TABLE memos ADD CONSTRAINT memos_status_check CHECK (
  status IN (
    'uploading',
    'transcribing',
    'extracting',
    'pending_transcript',
    'pending_review',
    'approved',
    'rejected',
    'failed'
  )
);
