-- Meeting attendees from calendar event: name and email from attendee list.
--   attendees   JSONB array of {email: str, name: str|null} (never null, default is empty array)
-- Exposed on memo list/detail API responses; helps dashboard show avatars on meeting rows.

BEGIN;

ALTER TABLE memos ADD COLUMN IF NOT EXISTS attendees JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMIT;
