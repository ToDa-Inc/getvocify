-- Append-only ledger of every paid vendor call (LLM tokens, STT audio time), attributed to the
-- user / memo / capture it served. Backend-only: service role writes, nobody else reads.
-- cost_usd is the vendor's own figure when it reports one (OpenRouter usage.cost), else
-- computed from audio time x rate; cost_source says which. NULL = unpriced, never a guess.
-- Rollback: 071_usage_events.down.sql

BEGIN;

CREATE TABLE IF NOT EXISTS usage_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  kind TEXT NOT NULL CHECK (kind IN ('llm', 'stt')),
  provider TEXT NOT NULL,
  model TEXT,
  purpose TEXT NOT NULL DEFAULT 'unknown',
  user_id UUID,
  company_id UUID,
  memo_id UUID,
  capture_id TEXT,
  scope_id UUID,
  prompt_tokens INTEGER,
  completion_tokens INTEGER,
  reasoning_tokens INTEGER,
  cached_tokens INTEGER,
  audio_seconds NUMERIC(12, 2),
  channels SMALLINT,
  cost_usd NUMERIC(12, 6),
  cost_source TEXT NOT NULL DEFAULT 'unpriced'
    CHECK (cost_source IN ('provider_reported', 'computed', 'unpriced')),
  duration_ms INTEGER,
  meta JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS usage_events_memo_idx ON usage_events (memo_id) WHERE memo_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS usage_events_capture_idx ON usage_events (capture_id) WHERE capture_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS usage_events_scope_idx ON usage_events (scope_id) WHERE scope_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS usage_events_user_time_idx ON usage_events (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS usage_events_time_idx ON usage_events (created_at DESC);

-- One row per memo: events tied to it directly, plus events from its desktop capture.
CREATE OR REPLACE VIEW memo_usage_costs AS
SELECT
  m.id AS memo_id,
  m.user_id,
  COALESCE(SUM(e.cost_usd), 0) AS cost_usd,
  COALESCE(SUM(e.cost_usd) FILTER (WHERE e.kind = 'llm'), 0) AS llm_cost_usd,
  COALESCE(SUM(e.cost_usd) FILTER (WHERE e.kind = 'stt'), 0) AS stt_cost_usd,
  COALESCE(SUM(e.audio_seconds) FILTER (WHERE e.kind = 'stt'), 0) AS stt_seconds,
  COUNT(e.id) AS events,
  COUNT(e.id) FILTER (WHERE e.cost_source = 'unpriced') AS unpriced_events
FROM memos m
JOIN usage_events e
  ON e.memo_id = m.id
  OR (m.client_capture_id IS NOT NULL AND e.capture_id = m.client_capture_id)
GROUP BY m.id, m.user_id;

ALTER TABLE usage_events ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    REVOKE ALL ON usage_events FROM anon;
    REVOKE ALL ON memo_usage_costs FROM anon;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON usage_events FROM authenticated;
    REVOKE ALL ON memo_usage_costs FROM authenticated;
  END IF;
END $$;

COMMIT;
