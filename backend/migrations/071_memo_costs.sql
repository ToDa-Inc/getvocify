-- What one interaction cost us, on the memo itself: no new table.
--   cost_usd        running total in USD (only priced calls; unpriced ones are counted below)
--   cost_breakdown  per step: {"live_stt": {"usd", "events", "unpriced", "prompt_tokens",
--                   "completion_tokens", "audio_seconds"}, "sanitize": {...}, "extract": {...}}
-- add_memo_cost() is the only writer. Sanitize, extract and follow-up finish in parallel, so the
-- add happens inside one UPDATE (row-locked) instead of read-modify-write in Python.
-- Rollback: 071_memo_costs.down.sql

BEGIN;

ALTER TABLE memos ADD COLUMN IF NOT EXISTS cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0;
ALTER TABLE memos ADD COLUMN IF NOT EXISTS cost_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE OR REPLACE FUNCTION add_memo_cost(
  p_memo UUID,
  p_purpose TEXT,
  p_usd NUMERIC,
  p_prompt_tokens INTEGER,
  p_completion_tokens INTEGER,
  p_audio_seconds NUMERIC
) RETURNS VOID
LANGUAGE sql
AS $add_memo_cost$
  UPDATE memos SET
    cost_usd = cost_usd + COALESCE(p_usd, 0),
    cost_breakdown = jsonb_set(
      cost_breakdown,
      ARRAY[p_purpose],
      jsonb_build_object(
        'usd', COALESCE((cost_breakdown -> p_purpose ->> 'usd')::numeric, 0) + COALESCE(p_usd, 0),
        'events', COALESCE((cost_breakdown -> p_purpose ->> 'events')::int, 0) + 1,
        'unpriced', COALESCE((cost_breakdown -> p_purpose ->> 'unpriced')::int, 0) + (p_usd IS NULL)::int,
        'prompt_tokens', COALESCE((cost_breakdown -> p_purpose ->> 'prompt_tokens')::int, 0) + COALESCE(p_prompt_tokens, 0),
        'completion_tokens', COALESCE((cost_breakdown -> p_purpose ->> 'completion_tokens')::int, 0) + COALESCE(p_completion_tokens, 0),
        'audio_seconds', COALESCE((cost_breakdown -> p_purpose ->> 'audio_seconds')::numeric, 0) + COALESCE(p_audio_seconds, 0)
      ),
      true
    )
  WHERE id = p_memo;
$add_memo_cost$;

REVOKE ALL ON FUNCTION add_memo_cost(UUID, TEXT, NUMERIC, INTEGER, INTEGER, NUMERIC) FROM PUBLIC;

COMMIT;
