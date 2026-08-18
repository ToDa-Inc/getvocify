-- Seller offer / product context used as reference-only input for call extraction.
ALTER TABLE user_profiles
  ADD COLUMN IF NOT EXISTS product_context TEXT DEFAULT '';
