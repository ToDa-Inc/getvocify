-- Raw STT output + single-flight pipeline lease.
ALTER TABLE memos
  ADD COLUMN IF NOT EXISTS transcript_raw TEXT,
  ADD COLUMN IF NOT EXISTS transcript_stt_meta JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS pipeline_run_id UUID,
  ADD COLUMN IF NOT EXISTS pipeline_run_started_at TIMESTAMPTZ;

COMMENT ON COLUMN memos.transcript_raw IS
  'Write-once provider transcript. Sanitize and polish write memos.transcript only.';
COMMENT ON COLUMN memos.transcript_stt_meta IS
  'STT provider/model/language, raw speaker count, and call_date (YYYY-MM-DD).';
COMMENT ON COLUMN memos.pipeline_run_id IS
  'Non-null while a pipeline run holds the single-flight lease.';
