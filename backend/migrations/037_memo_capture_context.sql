-- F01.02: capture identity on memos. capture_id is memos.id; no Interaction table.
-- Capture lifecycle stays off the memos.status enum:
--   recording      → memos.status = uploading
--   upload_pending → memos.status = uploading
--   processing     → memos.status = extracting
--   complete       → memos.status = pending_review
--   failed         → memos.status = failed
-- company_id and author (user_id) are taken from the session, never from a client company_id.

BEGIN;

ALTER TABLE memos
  ADD COLUMN IF NOT EXISTS client_capture_id TEXT,
  ADD COLUMN IF NOT EXISTS capture_started_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS interaction_kind TEXT,
  ADD COLUMN IF NOT EXISTS sales_motion_key TEXT,
  ADD COLUMN IF NOT EXISTS playbook_version_id TEXT,
  ADD COLUMN IF NOT EXISTS company_id UUID REFERENCES companies(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS capture_status TEXT,
  ADD COLUMN IF NOT EXISTS capture_content_fingerprint TEXT,
  ADD COLUMN IF NOT EXISTS capture_input_revision INTEGER NOT NULL DEFAULT 0;

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

COMMIT;
