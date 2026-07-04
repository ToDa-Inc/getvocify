-- Track Speechmatics job ID on memos so the webhook callback can match back.
ALTER TABLE memos ADD COLUMN IF NOT EXISTS speechmatics_job_id text;
CREATE INDEX IF NOT EXISTS memos_speechmatics_job_id_idx ON memos (speechmatics_job_id) WHERE speechmatics_job_id IS NOT NULL;
