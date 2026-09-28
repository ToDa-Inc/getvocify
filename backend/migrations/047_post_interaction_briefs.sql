-- F11: highlight preference does not delay processing. An older brief cannot replace a newer revision.

CREATE TABLE IF NOT EXISTS post_interaction_briefs (
  memo_id UUID NOT NULL,
  input_revision TEXT NOT NULL,
  revision_seq BIGINT NOT NULL,
  status TEXT NOT NULL,
  body JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (memo_id, input_revision)
);

CREATE TABLE IF NOT EXISTS brief_preferences (
  user_id UUID PRIMARY KEY,
  highlight_mode TEXT NOT NULL CHECK (highlight_mode IN ('immediate', 'deferred', 'end_of_day')),
  delay_minutes INTEGER,
  end_of_day TIME,
  timezone TEXT NOT NULL
);
