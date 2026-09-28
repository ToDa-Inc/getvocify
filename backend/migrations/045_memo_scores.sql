-- F09: one score per memo and input revision. An older revision cannot replace a newer one.

CREATE TABLE IF NOT EXISTS memo_scores (
  memo_id UUID NOT NULL,
  input_revision TEXT NOT NULL,
  revision_seq BIGINT NOT NULL,
  playbook_version_id TEXT,
  prompt_version TEXT NOT NULL DEFAULT 'scoring_v1',
  model_version TEXT,
  score JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (memo_id, input_revision)
);
