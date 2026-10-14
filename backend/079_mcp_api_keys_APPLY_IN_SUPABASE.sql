-- One personal API key per user, for the MCP server at /mcp (spec 2026-10-14-vocify-mcp-server-design).
-- Only a SHA-256 hash of the key is stored; the key itself is shown once, when it is generated. The prefix
-- is the first characters, so Settings can show which key is active without showing the key.
-- Regenerating overwrites the three columns; revoking clears them. Until this runs, generating a key fails
-- and /mcp accepts OAuth sign-in only.
-- Rollback: 079_mcp_api_keys.down.sql

BEGIN;

ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS api_key_hash TEXT NULL;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS api_key_prefix TEXT NULL;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS api_key_created_at TIMESTAMPTZ NULL;

CREATE UNIQUE INDEX IF NOT EXISTS user_profiles_api_key_hash_key
  ON user_profiles (api_key_hash)
  WHERE api_key_hash IS NOT NULL;

COMMIT;
