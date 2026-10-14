-- What the client saw as each turn check started (live_assist_events.client): which rule fired it (audio pause,
-- settled words, the slow fallback, the backstop), how long their audio had been quiet, how long since the
-- transcript last changed, and whether the words were still changing after their audio went quiet. With the
-- server's own times it says where the seconds between "they stopped talking" and "the card" went.
-- Rollback: 080_live_assist_events_client.down.sql

BEGIN;

ALTER TABLE live_assist_events ADD COLUMN IF NOT EXISTS client JSONB;

COMMIT;
