-- Drops every per-company override; each company falls back to the global env value.

BEGIN;

DROP TABLE IF EXISTS company_feature_flags;

COMMIT;
