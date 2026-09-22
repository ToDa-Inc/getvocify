-- F07: web Ask turns. Idempotency is per user, conversation and client turn id.

CREATE TABLE IF NOT EXISTS copilot_web_turns (
  id TEXT PRIMARY KEY,
  company_id UUID,
  user_id UUID NOT NULL,
  conversation_id TEXT NOT NULL,
  client_turn_id TEXT NOT NULL,
  status TEXT NOT NULL,
  body TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, conversation_id, client_turn_id)
);
