-- Add auto_create_contact_company to user_profiles
-- When false (default): only update deals, skip creating contacts/companies
-- When true: current behavior, create contact/company when extraction contains that data
ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS auto_create_contact_company BOOLEAN DEFAULT false;
