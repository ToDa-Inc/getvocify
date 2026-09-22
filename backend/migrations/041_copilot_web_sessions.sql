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

CREATE OR REPLACE FUNCTION save_ask_turn(
  p_company UUID,
  p_user UUID,
  p_conversation TEXT,
  p_client_turn TEXT,
  p_text TEXT
) RETURNS TABLE (turn_id TEXT, body TEXT, replayed BOOLEAN)
LANGUAGE plpgsql
AS $save_ask$
DECLARE
  existing_id TEXT;
  new_id TEXT;
BEGIN
  SELECT id INTO existing_id
  FROM copilot_web_turns
  WHERE user_id = p_user
    AND conversation_id = p_conversation
    AND client_turn_id = p_client_turn;

  IF existing_id IS NOT NULL THEN
    RETURN QUERY
    SELECT t.id, t.body, true
    FROM copilot_web_turns t
    WHERE t.id = existing_id;
    RETURN;
  END IF;

  BEGIN
    new_id := gen_random_uuid()::text;
    INSERT INTO copilot_web_turns (
      id, company_id, user_id, conversation_id, client_turn_id, status, body
    )
    VALUES (new_id, p_company, p_user, p_conversation, p_client_turn, 'pending', p_text);
    RETURN QUERY SELECT new_id, p_text, false;
  EXCEPTION WHEN unique_violation THEN
    RETURN QUERY
    SELECT t.id, t.body, true
    FROM copilot_web_turns t
    WHERE t.user_id = p_user
      AND t.conversation_id = p_conversation
      AND t.client_turn_id = p_client_turn;
  END;
END;
$save_ask$;
