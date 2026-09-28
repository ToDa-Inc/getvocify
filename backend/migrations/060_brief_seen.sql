-- Lista 3 (T12): which post-interaction briefs a rep has already seen in the bell's
-- "Feedback" section. One row per (user_id, memo_id); marking one seen again is a no-op.
-- Rollback: 060_brief_seen.down.sql

BEGIN;

CREATE TABLE IF NOT EXISTS brief_seen (
  user_id UUID NOT NULL,
  memo_id UUID NOT NULL,
  seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, memo_id)
);

ALTER TABLE brief_seen ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    REVOKE ALL ON brief_seen FROM anon;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON brief_seen FROM authenticated;
  END IF;
END $$;

COMMIT;
