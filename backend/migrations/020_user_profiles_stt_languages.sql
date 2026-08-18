-- Call transcription languages for file STT (HubSpot, upload, WhatsApp).
-- First entry is the main language. Extra entries mean mixed calls (Deepgram `multi`).
ALTER TABLE user_profiles
  ADD COLUMN IF NOT EXISTS stt_languages TEXT[] NOT NULL DEFAULT ARRAY['es'];

COMMENT ON COLUMN user_profiles.stt_languages IS
  'ISO 639-1 codes for file STT. First is primary. Multiple → Deepgram language=multi.';
