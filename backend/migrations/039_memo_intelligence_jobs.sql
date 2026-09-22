-- F0/F0.1: recoverable intelligence jobs. One row per memo, kind and input revision.
-- Claim is atomic. A late older revision cannot overwrite a newer success.

CREATE TABLE IF NOT EXISTS memo_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID,
  memo_id UUID NOT NULL,
  kind TEXT NOT NULL,
  input_revision TEXT NOT NULL,
  revision_seq BIGINT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (
    status IN ('pending', 'running', 'success', 'failed', 'superseded')
  ),
  attempts INTEGER NOT NULL DEFAULT 0,
  available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  lease_until TIMESTAMPTZ,
  run_id UUID,
  last_error TEXT,
  result JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (memo_id, kind, input_revision),
  UNIQUE (memo_id, kind, revision_seq)
);

CREATE INDEX IF NOT EXISTS idx_memo_jobs_claim
  ON memo_jobs (kind, available_at)
  WHERE status IN ('pending', 'running');

CREATE OR REPLACE FUNCTION claim_memo_job(p_kind TEXT, p_lease_seconds INTEGER)
RETURNS TABLE (job_id UUID, claimed_run_id UUID, claimed_memo_id UUID, claimed_revision TEXT)
LANGUAGE plpgsql
AS $$
DECLARE
  target_id UUID;
  new_run UUID := gen_random_uuid();
BEGIN
  SELECT id INTO target_id
  FROM memo_jobs
  WHERE kind = p_kind
    AND status IN ('pending', 'running')
    AND available_at <= now()
    AND (lease_until IS NULL OR lease_until < now())
  ORDER BY revision_seq, created_at
  FOR UPDATE SKIP LOCKED
  LIMIT 1;

  IF target_id IS NULL THEN
    RETURN;
  END IF;

  RETURN QUERY
  UPDATE memo_jobs
  SET status = 'running',
      attempts = attempts + 1,
      run_id = new_run,
      lease_until = now() + make_interval(secs => p_lease_seconds),
      updated_at = now()
  WHERE id = target_id
  RETURNING id, run_id, memo_id, input_revision;
END;
$$;

CREATE OR REPLACE FUNCTION publish_memo_job(p_job_id UUID, p_run_id UUID, p_result JSONB)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
  job memo_jobs%ROWTYPE;
BEGIN
  SELECT * INTO job FROM memo_jobs WHERE id = p_job_id FOR UPDATE;
  IF NOT FOUND THEN
    RETURN 'rejected';
  END IF;
  IF job.run_id IS DISTINCT FROM p_run_id
     OR job.status <> 'running'
     OR job.lease_until IS NULL
     OR job.lease_until < now() THEN
    RETURN 'rejected';
  END IF;
  IF EXISTS (
    SELECT 1 FROM memo_jobs newer
    WHERE newer.memo_id = job.memo_id
      AND newer.kind = job.kind
      AND newer.revision_seq > job.revision_seq
      AND newer.status = 'success'
  ) THEN
    UPDATE memo_jobs
    SET status = 'superseded', lease_until = NULL, updated_at = now()
    WHERE id = job.id;
    RETURN 'superseded';
  END IF;

  UPDATE memo_jobs
  SET status = 'success',
      result = p_result,
      lease_until = NULL,
      updated_at = now()
  WHERE id = job.id AND run_id = p_run_id;

  UPDATE memo_jobs
  SET status = 'superseded', lease_until = NULL, updated_at = now()
  WHERE memo_id = job.memo_id
    AND kind = job.kind
    AND revision_seq < job.revision_seq
    AND status IN ('pending', 'running');

  RETURN 'success';
END;
$$;
