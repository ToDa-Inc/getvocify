-- Canonical phone lookup for WhatsApp sender authorization.
-- Store the normalized E.164-ish value directly in user_profiles.phone.

ALTER TABLE user_profiles
  ADD COLUMN IF NOT EXISTS phone TEXT;

UPDATE user_profiles
SET phone = '+' || regexp_replace(phone, '\D', '', 'g')
WHERE phone IS NOT NULL
  AND regexp_replace(phone, '\D', '', 'g') <> '';

ALTER TABLE user_profiles
  DROP COLUMN IF EXISTS phone_normalized;

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_profiles_phone_unique
  ON user_profiles (phone)
  WHERE phone IS NOT NULL;
