-- Drops the per-role / per-person field lists; everyone falls back to the company's.

BEGIN;

DROP TABLE IF EXISTS crm_field_permissions;

COMMIT;
