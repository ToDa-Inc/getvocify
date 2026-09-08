-- Company workspaces: shared CRM, glossary, product context; seat-capped membership.

CREATE EXTENSION IF NOT EXISTS citext;

-- ---------------------------------------------------------------------------
-- Core tables
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS companies (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  seat_limit INT NOT NULL DEFAULT 1 CHECK (seat_limit >= 1),
  glossary JSONB NOT NULL DEFAULT '[]'::jsonb,
  product_context TEXT NOT NULL DEFAULT '',
  auto_create_contact_company BOOLEAN NOT NULL DEFAULT false,
  primary_crm_connection_id UUID,
  created_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS company_members (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'member')),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id),
  UNIQUE (company_id, user_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_members_one_owner
  ON company_members (company_id)
  WHERE role = 'owner' AND status = 'active';

CREATE TABLE IF NOT EXISTS company_invitations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  email CITEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('admin', 'member')),
  token_hash TEXT NOT NULL,
  invited_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  accepted_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_invitations_pending_email
  ON company_invitations (company_id, email)
  WHERE accepted_at IS NULL AND revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS password_reset_tokens (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user
  ON password_reset_tokens (user_id);

-- ---------------------------------------------------------------------------
-- CRM scoped to company
-- ---------------------------------------------------------------------------

ALTER TABLE crm_connections
  ADD COLUMN IF NOT EXISTS company_id UUID REFERENCES companies(id) ON DELETE CASCADE;

ALTER TABLE crm_configurations
  ADD COLUMN IF NOT EXISTS company_id UUID REFERENCES companies(id) ON DELETE CASCADE;

ALTER TABLE user_profiles
  ADD COLUMN IF NOT EXISTS company_id UUID REFERENCES companies(id) ON DELETE SET NULL;

-- ---------------------------------------------------------------------------
-- Backfill: one company per existing user (1 seat, owner)
-- ---------------------------------------------------------------------------

DO $$
DECLARE
  prof RECORD;
  new_company_id UUID;
  owner_email TEXT;
BEGIN
  FOR prof IN
    SELECT p.*, u.email AS auth_email
    FROM user_profiles p
    LEFT JOIN auth.users u ON u.id = p.id
    WHERE NOT EXISTS (
      SELECT 1 FROM company_members cm WHERE cm.user_id = p.id
    )
  LOOP
    new_company_id := uuid_generate_v4();
    owner_email := COALESCE(prof.auth_email, prof.id::text);

    INSERT INTO companies (
      id, name, seat_limit, glossary, product_context,
      auto_create_contact_company, primary_crm_connection_id, created_by
    ) VALUES (
      new_company_id,
      COALESCE(NULLIF(TRIM(prof.company_name), ''), split_part(owner_email, '@', 1) || '''s workspace'),
      1,
      COALESCE(prof.glossary, '[]'::jsonb),
      COALESCE(prof.product_context, ''),
      COALESCE(prof.auto_create_contact_company, false),
      prof.primary_crm_connection_id,
      prof.id
    );

    INSERT INTO company_members (company_id, user_id, role, status)
    VALUES (new_company_id, prof.id, 'owner', 'active');

    UPDATE user_profiles SET company_id = new_company_id WHERE id = prof.id;

    UPDATE crm_connections SET company_id = new_company_id WHERE user_id = prof.id;
    UPDATE crm_configurations SET company_id = new_company_id WHERE user_id = prof.id;
  END LOOP;
END $$;

-- FK from companies.primary_crm_connection_id (after backfill)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'companies_primary_crm_connection_id_fkey'
  ) THEN
    ALTER TABLE companies
      ADD CONSTRAINT companies_primary_crm_connection_id_fkey
      FOREIGN KEY (primary_crm_connection_id) REFERENCES crm_connections(id) ON DELETE SET NULL;
  END IF;
END $$;

-- Require company_id on CRM tables
ALTER TABLE crm_connections ALTER COLUMN company_id SET NOT NULL;
ALTER TABLE crm_configurations ALTER COLUMN company_id SET NOT NULL;

-- Replace per-user CRM uniqueness with per-company
ALTER TABLE crm_connections DROP CONSTRAINT IF EXISTS crm_connections_user_id_provider_key;
ALTER TABLE crm_connections
  ADD CONSTRAINT crm_connections_company_id_provider_key UNIQUE (company_id, provider);

CREATE INDEX IF NOT EXISTS idx_crm_connections_company ON crm_connections (company_id);
CREATE INDEX IF NOT EXISTS idx_crm_configurations_company ON crm_configurations (company_id);
CREATE INDEX IF NOT EXISTS idx_company_members_company ON company_members (company_id);
CREATE INDEX IF NOT EXISTS idx_company_invitations_company ON company_invitations (company_id);

-- ---------------------------------------------------------------------------
-- RLS (defense in depth; backend uses service role)
-- ---------------------------------------------------------------------------

ALTER TABLE companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_invitations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Members can view own company"
  ON companies FOR SELECT
  USING (
    id IN (SELECT company_id FROM company_members WHERE user_id = auth.uid() AND status = 'active')
  );

CREATE POLICY "Owner admin can update company"
  ON companies FOR UPDATE
  USING (
    id IN (
      SELECT company_id FROM company_members
      WHERE user_id = auth.uid() AND status = 'active' AND role IN ('owner', 'admin')
    )
  );

CREATE POLICY "Members can view company membership"
  ON company_members FOR SELECT
  USING (
    company_id IN (SELECT company_id FROM company_members cm WHERE cm.user_id = auth.uid() AND cm.status = 'active')
  );

CREATE POLICY "Members can view company invitations"
  ON company_invitations FOR SELECT
  USING (
    company_id IN (
      SELECT company_id FROM company_members
      WHERE user_id = auth.uid() AND status = 'active' AND role IN ('owner', 'admin')
    )
  );
