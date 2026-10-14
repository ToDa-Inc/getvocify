-- Drops the MCP API key columns. Every key stops working.

BEGIN;

DROP INDEX IF EXISTS user_profiles_api_key_hash_key;
ALTER TABLE user_profiles DROP COLUMN IF EXISTS api_key_created_at;
ALTER TABLE user_profiles DROP COLUMN IF EXISTS api_key_prefix;
ALTER TABLE user_profiles DROP COLUMN IF EXISTS api_key_hash;

COMMIT;
