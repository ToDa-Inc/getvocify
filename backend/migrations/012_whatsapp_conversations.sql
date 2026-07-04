-- Durable WhatsApp conversation/session state for Meta and Unipile.
-- The processor keys sessions by normalized phone when provider chat IDs are missing.

CREATE TABLE IF NOT EXISTS conversations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  chat_id TEXT NOT NULL,
  account_id TEXT NOT NULL,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  channel TEXT NOT NULL DEFAULT 'whatsapp',
  state TEXT NOT NULL DEFAULT 'idle' CHECK (
    state IN (
      'idle',
      'waiting_approval',
      'waiting_add_fields',
      'waiting_crm_instruction',
      'waiting_deal_choice'
    )
  ),
  pending_memo_id UUID REFERENCES memos(id) ON DELETE SET NULL,
  pending_artifact_ids JSONB,
  state_expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(chat_id, account_id, user_id)
);

CREATE TABLE IF NOT EXISTS conversation_messages (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  direction TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
  content_type TEXT NOT NULL DEFAULT 'text' CHECK (
    content_type IN ('text', 'extraction_summary', 'system')
  ),
  content TEXT,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE memos ADD COLUMN IF NOT EXISTS conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_conversations_user_chat ON conversations(user_id, chat_id, account_id);
CREATE INDEX IF NOT EXISTS idx_conversations_state ON conversations(user_id, state, state_expires_at);
CREATE INDEX IF NOT EXISTS idx_conversation_messages_conversation_created
  ON conversation_messages(conversation_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memos_conversation_id ON memos(conversation_id);
