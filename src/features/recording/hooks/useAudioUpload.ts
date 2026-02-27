/**
 * useAudioUpload Hook
 *
 * Handles uploading to the backend. Supports:
 * - Transcript-only (from real-time transcription) - no audio sent
 * - Audio file (for file upload) - transcribed on server
 */

import { useState, useCallback } from 'react';
import { memosApi } from '@/features/memos/api';
import type { RecordedAudio, UploadProgress, UseAudioUploadReturn } from '../types';

/**
 * Hook for uploading to the backend
 */
export function useAudioUpload(): UseAudioUploadReturn {
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Upload transcript only (no audio). Use when real-time transcription or meeting transcript paste.
   * Returns the created memo ID.
   */
  const uploadTranscriptOnly = useCallback(
    async (
      transcript: string,
      options?: { sourceType?: 'voice_memo' | 'meeting_transcript' },
    ): Promise<string> => {
      setIsUploading(true);
      setError(null);
      setProgress({ percent: 0, loaded: 0, total: 100, complete: false });

      try {
        const response = await memosApi.uploadTranscript(
          transcript.trim(),
          options?.sourceType,
        );
        setProgress({ percent: 100, loaded: 100, total: 100, complete: true });
        return response.id;
      } catch (err) {
        console.error('Upload failed:', err);
        const message = err instanceof Error ? err.message : 'Upload failed';
        setError(message);
        throw err;
      } finally {
        setIsUploading(false);
      }
    },
    [],
  );

  /**
   * Upload audio (and optional transcript). Use for file upload or when no real-time transcript.
   * When transcript is provided, only transcript is sent (no audio).
   */
  const upload = useCallback(async (
    audio: RecordedAudio,
    transcript?: string
  ): Promise<string> => {
    if (transcript?.trim()) {
      return uploadTranscriptOnly(transcript);
    }

    setIsUploading(true);
    setError(null);
    setProgress({
      percent: 0,
      loaded: 0,
      total: audio.size,
      complete: false,
    });

    try {
      const response = await memosApi.uploadWithProgress(
        audio.blob,
        (percent) => {
          setProgress({
            percent,
            loaded: Math.round((percent / 100) * audio.size),
            total: audio.size,
            complete: percent >= 100,
          });
        }
      );

      setProgress(prev => prev ? { ...prev, complete: true } : null);
      return response.id;
    } catch (err) {
      console.error('Upload failed:', err);
      const message = err instanceof Error ? err.message : 'Upload failed';
      setError(message);
      throw err;
    } finally {
      setIsUploading(false);
    }
  }, [uploadTranscriptOnly]);

  /**
   * Reset upload state
   */
  const reset = useCallback(() => {
    setProgress(null);
    setIsUploading(false);
    setError(null);
  }, []);

  return {
    upload,
    uploadTranscriptOnly,
    progress,
    isUploading,
    error,
    reset,
  };
}


