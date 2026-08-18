-- Per-memo STT / sanitize / extract timings and LLM prompt snapshots.
ALTER TABLE memos
  ADD COLUMN IF NOT EXISTS pipeline_meta JSONB DEFAULT '{}'::jsonb;

COMMENT ON COLUMN memos.pipeline_meta IS
  'Per-run pipeline timings (ms) and LLM prompt snapshots for STT, sanitize, extract.';
