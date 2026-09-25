-- F10: a human note is not a prospect quote. One annotation id is one note.
-- Patterns keep every revision; an older projection does not add a second frequency.

CREATE TABLE IF NOT EXISTS interaction_annotations (
  author_id UUID NOT NULL,
  annotation_id TEXT NOT NULL,
  company_id UUID NOT NULL,
  client_capture_id TEXT,
  memo_id UUID,
  text TEXT NOT NULL,
  offset_ms INTEGER NOT NULL CHECK (offset_ms >= 0),
  turn_id TEXT,
  revision INTEGER NOT NULL DEFAULT 1,
  source_type TEXT NOT NULL DEFAULT 'human_note' CHECK (source_type = 'human_note'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (author_id, annotation_id)
);

CREATE TABLE IF NOT EXISTS interaction_patterns (
  memo_id UUID NOT NULL,
  pattern_id TEXT NOT NULL,
  input_revision TEXT NOT NULL,
  category TEXT NOT NULL,
  kind TEXT NOT NULL,
  resolution TEXT NOT NULL,
  response TEXT,
  evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
  superseded BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (memo_id, pattern_id, input_revision)
);
