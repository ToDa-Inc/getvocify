-- T14: Recall.ai meeting bot writes memos.source = 'recall'. Extends
-- memos_source_check (last defined in 037_memo_capture_context.sql) with that value;
-- every value allowed since then stays valid, so existing rows are not rejected.
-- Until this runs, app.services.captures.reserve_capture retries a 23514 check
-- violation with source='web' instead of failing the reservation (see
-- app/services/meetings/recall_bot.py).

BEGIN;

ALTER TABLE memos DROP CONSTRAINT IF EXISTS memos_source_check;
ALTER TABLE memos ADD CONSTRAINT memos_source_check
  CHECK (source IN (
    'web', 'voice_memo', 'whatsapp', 'unipile', 'hubspot_call', 'vocify_call', 'desktop', 'recall'
  ));

COMMIT;
