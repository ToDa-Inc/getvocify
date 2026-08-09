-- Prevent duplicate memos from WhatsApp/Unipile webhook redelivery.
--
-- Meta and Unipile both guarantee "at least once" webhook delivery, and the
-- extract-then-insert path in whatsapp/processor.py (_extract_and_create_memo)
-- has a wide check-then-insert race window (an LLM extraction call sits
-- between the "does this message_id already have a memo?" check and the
-- actual insert). Two near-simultaneous deliveries of the same message_id can
-- both pass the check and both insert, creating a duplicate memo (and
-- potentially a duplicate CRM sync downstream). Mirrors the same fix already
-- applied to hubspot_engagement_id in migration 009.
CREATE UNIQUE INDEX IF NOT EXISTS idx_memos_whatsapp_message_id_unique
  ON memos (whatsapp_message_id)
  WHERE whatsapp_message_id IS NOT NULL;
