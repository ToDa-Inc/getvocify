-- Migration: Add processing_started_at column to memos table
-- Purpose: Track when processing started to enable recovery of stuck tasks
-- Date: 2025-01-XX

-- Add column (nullable, defaults to NULL)
ALTER TABLE memos 
ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMPTZ;

-- Add comment
COMMENT ON COLUMN memos.processing_started_at IS 
'Timestamp when processing started. Used to identify stuck memos for recovery. Cleared on success or failure.';
