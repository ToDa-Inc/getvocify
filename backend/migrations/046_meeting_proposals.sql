-- F14: a proposed meeting is not a closed deal. Ambiguous times stay null.

CREATE TABLE IF NOT EXISTS meeting_proposals (
  proposal_id TEXT NOT NULL,
  memo_id UUID NOT NULL,
  input_revision TEXT NOT NULL,
  agreement TEXT NOT NULL,
  starts_at TIMESTAMPTZ,
  timezone TEXT,
  precision TEXT NOT NULL,
  decision TEXT NOT NULL DEFAULT 'pending',
  crm_status TEXT NOT NULL DEFAULT 'not_requested',
  evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
  remote_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (memo_id, proposal_id, input_revision)
);
