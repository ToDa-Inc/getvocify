-- Drops connected calendars. The Recall calendars themselves stay until deleted through
-- Recall's API or dashboard.

BEGIN;

DROP TABLE IF EXISTS calendar_connections;

COMMIT;
