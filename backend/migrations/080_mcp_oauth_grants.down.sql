-- Drops the connected-apps column. Every app connected by signing in stops working.

BEGIN;

ALTER TABLE user_profiles DROP COLUMN IF EXISTS oauth_grants;

COMMIT;
