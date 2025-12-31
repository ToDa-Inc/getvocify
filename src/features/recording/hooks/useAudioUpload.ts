/**
 * useAudioUpload Hook
 * 
 * Handles uploading recorded audio to the backend.
 * Provides progress tracking and error handling.
 */

import { useState, useCallback } from 'react';
import { memosApi } from '@/features/memos/api';
import type { RecordedAudio, UploadProgress, UseAudioUploadReturn } from '../types';

/**
 * Hook for uploading audio to the backend
 */
export function useAudioUpload(): UseAudioUploadReturn {
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Upload the recorded audio
   * Returns the created memo ID
   * 
   * @param audio - Recorded audio data
   * @param transcript - Optional pre-transcribed text (from real-time WebSocket)
   */
  const upload = useCallback(async (
    audio: RecordedAudio,
    transcript?: string
  ): Promise<string> => {
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
        },
        transcript
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
  }, []);

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
    progress,
    isUploading,
    error,
    reset,
  };
}


