-- «Sugerencias» (app/services/playbooks/suggestions.py): the head of sales' decision on each suggestion the team's calls
-- produced. One row per company and suggestion key (kind + call type + topic):
--   accepted   taken into the playbook (an answer, or a situation of «Cómo trabajamos») with the words they approved;
--   dismissed  set aside with a reason Vocify learns from: isolated (comes back if it keeps happening), not_applicable
--              (never again, and the call reading stops proposing it), covered (covered_by names the answer that covers it).
-- Service role only (the backend talks to it). Until it exists the list still shows and nothing can be decided.
-- Rollback: 089_playbook_suggestions.down.sql

BEGIN;

CREATE TABLE IF NOT EXISTS playbook_suggestion_decisions (
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  key TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('objection', 'question', 'worked', 'opportunity')),
  motion TEXT NOT NULL,
  topic TEXT NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('accepted', 'dismissed')),
  reason TEXT CHECK (reason IN ('isolated', 'not_applicable', 'covered')),
  covered_by TEXT,
  count_at INTEGER NOT NULL DEFAULT 0,
  text TEXT,
  user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  decided_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (company_id, key)
);

ALTER TABLE playbook_suggestion_decisions ENABLE ROW LEVEL SECURITY;

COMMIT;
