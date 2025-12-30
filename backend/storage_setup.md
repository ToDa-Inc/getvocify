# Supabase Storage Setup

After running `schema.sql`, you need to create the storage bucket for audio files.

## Steps

1. Go to your Supabase Dashboard
2. Navigate to **Storage** → **Buckets**
3. Click **New bucket**
4. Configure:
   - **Name**: `voice-memos`
   - **Public bucket**: ✅ Enable (for MVP - use signed URLs in production)
   - **File size limit**: 10 MB
   - **Allowed MIME types**: `audio/*`

5. Click **Create bucket**

## Storage Policies (Optional but Recommended)

After creating the bucket, set up RLS policies:

```sql
-- Allow authenticated users to upload their own files
CREATE POLICY "Users can upload own audio"
ON storage.objects FOR INSERT
TO authenticated
WITH CHECK (
  bucket_id = 'voice-memos' AND
  (storage.foldername(name))[1] = auth.uid()::text
);

-- Allow authenticated users to read their own files
CREATE POLICY "Users can read own audio"
ON storage.objects FOR SELECT
TO authenticated
USING (
  bucket_id = 'voice-memos' AND
  (storage.foldername(name))[1] = auth.uid()::text
);

-- Allow authenticated users to delete their own files
CREATE POLICY "Users can delete own audio"
ON storage.objects FOR DELETE
TO authenticated
USING (
  bucket_id = 'voice-memos' AND
  (storage.foldername(name))[1] = auth.uid()::text
);
```

## Test

You can test the bucket by uploading a file through the Supabase dashboard or via the API.


