-- Vocify v1 schema bundle: migrations 037 through 049.
-- Apply once on a database that already has migrations through 036
-- (memos, user_profiles, companies).
--
--   psql "$DATABASE_URL" -f backend/migrations/037_049_vocify_v1.sql
--
-- One transaction. A failure rolls the whole bundle back.
-- Safe to re-run after a successful apply: columns use IF NOT EXISTS,
-- tables use CREATE TABLE IF NOT EXISTS, functions use CREATE OR REPLACE.
-- A partial table from a failed run outside this transaction is NOT repaired
-- by CREATE TABLE IF NOT EXISTS.
--
-- 037 replaces memos_source_check and adds 'desktop'. Values allowed since
-- 025 stay valid, so existing rows are not rejected.
-- The INSERT policy is created only when public.company_members exists.

BEGIN;

-- ----- 037_memo_capture_context.sql -----

-- F01.02: capture identity on memos. capture_id is memos.id; no Interaction table.
-- Capture lifecycle stays off the memos.status enum:
--   recording      → memos.status = uploading
--   upload_pending → memos.status = uploading
--   processing     → memos.status = extracting
--   complete       → memos.status = pending_review
--   failed         → memos.status = failed
-- company_id and author (user_id) are taken from the session, never from a client company_id.


ALTER TABLE memos
  ADD COLUMN IF NOT EXISTS client_capture_id TEXT,
  ADD COLUMN IF NOT EXISTS capture_started_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS interaction_kind TEXT,
  ADD COLUMN IF NOT EXISTS sales_motion_key TEXT,
  ADD COLUMN IF NOT EXISTS playbook_version_id TEXT,
  ADD COLUMN IF NOT EXISTS company_id UUID REFERENCES companies(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS capture_status TEXT,
  ADD COLUMN IF NOT EXISTS capture_content_fingerprint TEXT,
  ADD COLUMN IF NOT EXISTS capture_input_revision INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS audio_status TEXT,
  ADD COLUMN IF NOT EXISTS capture_turns JSONB,
  ADD COLUMN IF NOT EXISTS transcript_complete BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE memos DROP CONSTRAINT IF EXISTS memos_interaction_kind_check;
ALTER TABLE memos ADD CONSTRAINT memos_interaction_kind_check
  CHECK (
    interaction_kind IS NULL
    OR interaction_kind IN ('call', 'meeting', 'visit', 'voice_note')
  );

ALTER TABLE memos DROP CONSTRAINT IF EXISTS memos_capture_status_check;
ALTER TABLE memos ADD CONSTRAINT memos_capture_status_check
  CHECK (
    capture_status IS NULL
    OR capture_status IN (
      'recording', 'upload_pending', 'processing', 'complete', 'failed'
    )
  );

ALTER TABLE memos DROP CONSTRAINT IF EXISTS memos_source_check;
ALTER TABLE memos ADD CONSTRAINT memos_source_check
  CHECK (source IN (
    'web', 'voice_memo', 'whatsapp', 'unipile', 'hubspot_call', 'vocify_call', 'desktop'
  ));

CREATE UNIQUE INDEX IF NOT EXISTS idx_memos_user_client_capture_id_unique
  ON memos (user_id, client_capture_id)
  WHERE client_capture_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_memos_company_id
  ON memos (company_id)
  WHERE company_id IS NOT NULL;

COMMENT ON COLUMN memos.client_capture_id IS
  'Client-assigned capture key. Unique per author (user_id). Recovery before the server id is known.';
COMMENT ON COLUMN memos.company_id IS
  'Original workspace from the creating session. Immutable. Never taken from a client body.';
COMMENT ON COLUMN memos.interaction_kind IS
  'call | meeting | visit | voice_note. Distinct from source_type, which keeps existing origin values.';
COMMENT ON COLUMN memos.capture_status IS
  'recording/upload_pending/processing/complete/failed. Mapped onto memos.status; not added to that enum.';
COMMENT ON COLUMN memos.capture_content_fingerprint IS
  'Hash of the completed input. Identical complete is idempotent; a different payload needs a new review.';

CREATE OR REPLACE FUNCTION memos_lock_capture_identity()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF NEW.company_id IS DISTINCT FROM OLD.company_id THEN
      RAISE EXCEPTION 'memos.company_id is immutable';
    END IF;
    IF OLD.client_capture_id IS NOT NULL
       AND NEW.client_capture_id IS DISTINCT FROM OLD.client_capture_id THEN
      RAISE EXCEPTION 'memos.client_capture_id is immutable';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS memos_lock_capture_identity ON memos;
CREATE TRIGGER memos_lock_capture_identity
  BEFORE UPDATE ON memos
  FOR EACH ROW
  EXECUTE FUNCTION memos_lock_capture_identity();

-- JWT clients still only see their own memos (existing ALL policy).
-- This extra INSERT check rejects a forged company_id on a user JWT.
-- The API uses service_role (bypasses RLS) and must copy company_id from the session.
DO $$
BEGIN
  IF to_regclass('public.company_members') IS NULL THEN
    RETURN;
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'memos'
      AND policyname = 'Memos capture company matches membership'
  ) THEN
    RETURN;
  END IF;
  EXECUTE $policy$
    CREATE POLICY "Memos capture company matches membership"
      ON memos FOR INSERT
      WITH CHECK (
        company_id IS NULL
        OR company_id IN (
          SELECT company_members.company_id
          FROM company_members
          WHERE company_members.user_id = auth.uid()
            AND company_members.status = 'active'
        )
      )
  $policy$;
END
$$;

-- ----- 038_memos_followup.sql -----

-- F02: follow-up draft per memo and the rep's voice samples.
-- Renumbered from PF 037 because 037 is memo capture context.

ALTER TABLE memos
  ADD COLUMN IF NOT EXISTS followup JSONB,
  ADD COLUMN IF NOT EXISTS followup_run_started_at TIMESTAMPTZ;

COMMENT ON COLUMN memos.followup IS
  'Draft lifecycle {status: generating|ready|sent|unavailable, subject, body, final_subject, final_body, edit_ratio, no_edit, channel, run_id, prompt_version, ...}. sent means handoff to the mail client, not confirmed delivery.';
COMMENT ON COLUMN memos.followup_run_started_at IS
  'Non-null while a follow-up generation holds the single-flight lease.';

ALTER TABLE user_profiles
  ADD COLUMN IF NOT EXISTS writing_samples JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN user_profiles.writing_samples IS
  'Last follow-ups the rep reshaped before sending (max 5): few-shot voice for drafts.';

-- ----- 039_memo_intelligence_jobs.sql -----

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

-- ----- 040_company_playbooks.sql -----

-- F08: playbook versions. One active snapshot per playbook. Older versions stay readable.

CREATE TABLE IF NOT EXISTS playbooks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL,
  sales_motion_key TEXT NOT NULL,
  active_version_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (company_id, sales_motion_key)
);

CREATE TABLE IF NOT EXISTS playbook_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  playbook_id UUID NOT NULL REFERENCES playbooks(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published')),
  steps JSONB NOT NULL DEFAULT '[]'::jsonb,
  entries JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS playbook_imports (
  id TEXT PRIMARY KEY,
  company_id UUID,
  playbook_id UUID,
  kind TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'ready', 'failed')),
  reason TEXT,
  draft JSONB,
  active_version_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS interaction_types (
  company_id UUID NOT NULL,
  type_key TEXT NOT NULL,
  name TEXT NOT NULL,
  active BOOLEAN NOT NULL DEFAULT true,
  PRIMARY KEY (company_id, type_key)
);

CREATE OR REPLACE FUNCTION publish_playbook_version(p_version UUID)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
  pb UUID;
BEGIN
  SELECT playbook_id INTO pb FROM playbook_versions WHERE id = p_version FOR UPDATE;
  IF pb IS NULL THEN
    RAISE EXCEPTION 'playbook version not found';
  END IF;
  PERFORM 1 FROM playbooks WHERE id = pb FOR UPDATE;
  UPDATE playbook_versions SET status = 'published' WHERE id = p_version;
  UPDATE playbooks SET active_version_id = p_version WHERE id = pb;
  RETURN p_version;
END;
$$;

CREATE OR REPLACE FUNCTION save_playbook_draft(
  p_company UUID,
  p_motion TEXT,
  p_import TEXT,
  p_payload TEXT,
  p_contradictions JSONB DEFAULT '[]'::jsonb
) RETURNS TEXT
LANGUAGE plpgsql
AS $save_draft$
DECLARE
  pb UUID;
BEGIN
  INSERT INTO playbooks (company_id, sales_motion_key)
  VALUES (p_company, p_motion)
  ON CONFLICT (company_id, sales_motion_key) DO NOTHING;

  SELECT id INTO pb FROM playbooks
  WHERE company_id = p_company AND sales_motion_key = p_motion;

  IF EXISTS (SELECT 1 FROM playbook_imports WHERE id = p_import) THEN
    RETURN 'ready';
  END IF;

  INSERT INTO playbook_versions (playbook_id, status, steps, entries)
  VALUES (
    pb,
    'draft',
    jsonb_build_array(jsonb_build_object(
      'step_id', 'imported',
      'label', left(p_payload, 80),
      'criterion', p_payload
    )),
    jsonb_build_array(jsonb_build_object(
      'entry_id', 'text:' || p_import,
      'category', 'process',
      'guidance', p_payload,
      'source_ref', 'text:' || p_import
    ))
  );

  INSERT INTO playbook_imports (
    id, company_id, playbook_id, kind, status, draft, active_version_id
  )
  VALUES (
    p_import,
    p_company,
    pb,
    'text',
    'ready',
    jsonb_build_object(
      'text', p_payload,
      'source_ref', 'text:' || p_import,
      'contradictions', COALESCE(p_contradictions, '[]'::jsonb)
    ),
    (SELECT active_version_id FROM playbooks WHERE id = pb)
  );
  RETURN 'ready';
END;
$save_draft$;

CREATE OR REPLACE FUNCTION publish_playbook_motion(p_company UUID, p_motion TEXT)
RETURNS TEXT
LANGUAGE plpgsql
AS $publish_motion$
DECLARE
  pb UUID;
  ver UUID;
BEGIN
  SELECT id INTO pb FROM playbooks
  WHERE company_id = p_company AND sales_motion_key = p_motion
  FOR UPDATE;

  IF pb IS NULL THEN
    RETURN 'not_a_draft';
  END IF;

  IF EXISTS (
    SELECT 1 FROM playbook_imports i
    WHERE i.playbook_id = pb
      AND COALESCE(jsonb_array_length(i.draft->'contradictions'), 0) > 0
      AND i.created_at = (
        SELECT max(created_at) FROM playbook_imports WHERE playbook_id = pb
      )
  ) THEN
    RETURN 'contradiction';
  END IF;

  SELECT id INTO ver FROM playbook_versions
  WHERE playbook_id = pb AND status = 'draft'
  ORDER BY created_at DESC
  LIMIT 1
  FOR UPDATE;

  IF ver IS NULL THEN
    RETURN 'not_a_draft';
  END IF;

  PERFORM publish_playbook_version(ver);
  RETURN 'published:' || ver::text;
END;
$publish_motion$;

CREATE OR REPLACE FUNCTION list_playbook_motions(p_company UUID)
RETURNS TABLE (sales_motion_key TEXT, motion_status TEXT)
LANGUAGE sql
STABLE
AS $list_motions$
  SELECT motion_key AS sales_motion_key, motion_status
  FROM (
    SELECT p.sales_motion_key AS motion_key,
      CASE
        WHEN p.active_version_id IS NOT NULL THEN 'published'
        WHEN EXISTS (
          SELECT 1 FROM playbook_versions v
          WHERE v.playbook_id = p.id AND v.status = 'draft'
        ) THEN 'draft'
        ELSE 'missing'
      END AS motion_status
    FROM playbooks p
    WHERE p.company_id = p_company
    UNION
    SELECT t.type_key,
      'missing'
    FROM interaction_types t
    WHERE t.company_id = p_company
      AND t.active
      AND NOT EXISTS (
        SELECT 1 FROM playbooks p
        WHERE p.company_id = t.company_id AND p.sales_motion_key = t.type_key
      )
  ) listed;
$list_motions$;

CREATE OR REPLACE FUNCTION add_interaction_type(p_company UUID, p_key TEXT, p_name TEXT)
RETURNS TEXT
LANGUAGE plpgsql
AS $add_type$
BEGIN
  IF btrim(p_key) = '' THEN
    RETURN 'empty';
  END IF;
  INSERT INTO interaction_types (company_id, type_key, name)
  VALUES (p_company, btrim(p_key), COALESCE(NULLIF(btrim(p_name), ''), btrim(p_key)))
  ON CONFLICT (company_id, type_key) DO NOTHING;
  RETURN btrim(p_key);
END;
$add_type$;

-- ----- 041_copilot_web_sessions.sql -----

-- F07: web Ask turns. Idempotency is per user, conversation and client turn id.

CREATE TABLE IF NOT EXISTS copilot_web_turns (
  id TEXT PRIMARY KEY,
  company_id UUID,
  user_id UUID NOT NULL,
  conversation_id TEXT NOT NULL,
  client_turn_id TEXT NOT NULL,
  status TEXT NOT NULL,
  body TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, conversation_id, client_turn_id)
);

CREATE OR REPLACE FUNCTION save_ask_turn(
  p_company UUID,
  p_user UUID,
  p_conversation TEXT,
  p_client_turn TEXT,
  p_text TEXT
) RETURNS TABLE (turn_id TEXT, body TEXT, replayed BOOLEAN)
LANGUAGE plpgsql
AS $save_ask$
DECLARE
  existing_id TEXT;
  new_id TEXT;
BEGIN
  SELECT id INTO existing_id
  FROM copilot_web_turns
  WHERE user_id = p_user
    AND conversation_id = p_conversation
    AND client_turn_id = p_client_turn;

  IF existing_id IS NOT NULL THEN
    RETURN QUERY
    SELECT t.id, t.body, true
    FROM copilot_web_turns t
    WHERE t.id = existing_id;
    RETURN;
  END IF;

  BEGIN
    new_id := gen_random_uuid()::text;
    INSERT INTO copilot_web_turns (
      id, company_id, user_id, conversation_id, client_turn_id, status, body
    )
    VALUES (new_id, p_company, p_user, p_conversation, p_client_turn, 'pending', p_text);
    RETURN QUERY SELECT new_id, p_text, false;
  EXCEPTION WHEN unique_violation THEN
    RETURN QUERY
    SELECT t.id, t.body, true
    FROM copilot_web_turns t
    WHERE t.user_id = p_user
      AND t.conversation_id = p_conversation
      AND t.client_turn_id = p_client_turn;
  END;
END;
$save_ask$;

-- ----- 042_contact_priority_context.sql -----

-- F04: cached CRM context per company, connection and contact. deal_id '' means no deal.

CREATE TABLE IF NOT EXISTS contact_priority_context (
  company_id UUID NOT NULL,
  connection_id TEXT NOT NULL,
  contact_id TEXT NOT NULL,
  deal_id TEXT NOT NULL DEFAULT '',
  owner_user_id UUID,
  owner_ambiguous BOOLEAN NOT NULL DEFAULT false,
  coverage TEXT NOT NULL,
  history_complete BOOLEAN NOT NULL DEFAULT false,
  observed_at TIMESTAMPTZ,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (company_id, connection_id, contact_id, deal_id)
);

-- ----- 043_action_signals.sql -----

-- F05: one Hoy signal per company, user, connection and dedupe key.
-- Action metadata is reserved for F06 undo. A daily run is one row per company and local date.

CREATE TABLE IF NOT EXISTS action_signals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL,
  user_id UUID NOT NULL,
  connection_id TEXT NOT NULL DEFAULT '',
  contact_id TEXT,
  deal_id TEXT,
  memo_id TEXT,
  type TEXT NOT NULL,
  dedupe_key TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL CHECK (status IN ('pending', 'done', 'dismissed', 'snoozed', 'resolved')),
  version INTEGER NOT NULL DEFAULT 1,
  snoozed_until TIMESTAMPTZ,
  previous_status TEXT,
  last_action_request_id TEXT,
  last_action_at TIMESTAMPTZ,
  undo_deadline TIMESTAMPTZ,
  coverage TEXT NOT NULL DEFAULT 'complete',
  observed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (company_id, user_id, connection_id, dedupe_key)
);

CREATE TABLE IF NOT EXISTS hoy_daily_runs (
  company_id UUID NOT NULL,
  local_date DATE NOT NULL,
  status TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (company_id, local_date)
);

-- ----- 044_interaction_annotations_patterns.sql -----

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

-- ----- 045_memo_scores.sql -----

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

-- ----- 046_meeting_proposals.sql -----

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

CREATE TABLE IF NOT EXISTS meeting_writes (
  operation_key TEXT PRIMARY KEY,
  memo_id UUID NOT NULL,
  proposal_id TEXT NOT NULL,
  remote_id TEXT,
  crm_status TEXT NOT NULL,
  stage_changed BOOLEAN NOT NULL DEFAULT false
);

-- ----- 047_post_interaction_briefs.sql -----

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

-- ----- 048_reports_notifications.sql -----

-- F13: one report per recipient, scope and period. Delivery retries share one idempotency key.

CREATE TABLE IF NOT EXISTS reports (
  id TEXT NOT NULL,
  company_id UUID NOT NULL,
  user_id UUID NOT NULL,
  scope TEXT NOT NULL,
  period_start TIMESTAMPTZ NOT NULL,
  report_type TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  snapshot JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (id),
  UNIQUE (company_id, user_id, scope, period_start, report_type)
);

CREATE TABLE IF NOT EXISTS report_deliveries (
  idempotency_key TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  channel TEXT NOT NULL,
  delivery_status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS report_notifications (
  id TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  user_id UUID NOT NULL,
  read_at TIMESTAMPTZ
);

-- ----- 049_team_outcomes.sql -----

-- F15: one observation per company, connection, deal and time seen. History is appended, not rewritten.

CREATE TABLE IF NOT EXISTS team_outcome_observations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL,
  connection_id TEXT NOT NULL,
  deal_id TEXT NOT NULL,
  status TEXT NOT NULL,
  owner_user_id UUID,
  attribution TEXT NOT NULL,
  amount NUMERIC,
  currency TEXT,
  closed_at TIMESTAMPTZ,
  observed_at TIMESTAMPTZ NOT NULL,
  UNIQUE (company_id, connection_id, deal_id, observed_at)
);

COMMIT;
