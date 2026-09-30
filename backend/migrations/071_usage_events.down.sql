-- Drops the cost ledger and its per-memo view. Recorded history is lost.

BEGIN;

DROP VIEW IF EXISTS memo_usage_costs;
DROP TABLE IF EXISTS usage_events;

COMMIT;
