-- The apps a user connected to the MCP server by signing in with their Vocify account (Claude.ai, Claude
-- Desktop connectors, ChatGPT), for Settings → AI agents and to revoke them. One JSON object per user:
--   { "<app key>": { "name", "host", "at", "chains": { "<connection>": { "rt": "<current refresh token id>", ... } } } }
-- Deleting an entry disconnects the app: its tokens stop working. No secrets are stored; the tokens themselves are
-- signed, not saved. Until this runs, "sign in with Vocify" cannot finish (API keys are not affected).
-- Rollback: 080_mcp_oauth_grants.down.sql

BEGIN;

ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS oauth_grants JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMIT;
