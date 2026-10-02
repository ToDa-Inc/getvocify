-- Drops recorded costs from memos. The history is lost.

BEGIN;

DROP FUNCTION IF EXISTS add_memo_cost(UUID, TEXT, NUMERIC, INTEGER, INTEGER, NUMERIC);
ALTER TABLE memos DROP COLUMN IF EXISTS cost_breakdown;
ALTER TABLE memos DROP COLUMN IF EXISTS cost_usd;

COMMIT;
