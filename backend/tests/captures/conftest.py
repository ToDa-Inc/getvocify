"""Dummy settings so captures tests never read production credentials."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-captures-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-captures-32b+")
