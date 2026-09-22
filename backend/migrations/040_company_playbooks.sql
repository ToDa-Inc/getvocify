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
