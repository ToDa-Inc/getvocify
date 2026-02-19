/**
 * Memos API
 * 
 * All API calls related to voice memos.
 */

import { api } from '@/shared/lib/api-client';
import type { 
  Memo, 
  MemoFilters, 
  UploadMemoResponse, 
  ApproveMemoPayload 
} from './types';

/**
 * Query keys for TanStack Query
 * 
 * Usage:
 * ```ts
 * useQuery({ queryKey: memoKeys.detail(id), ... })
 * queryClient.invalidateQueries({ queryKey: memoKeys.lists() })
 * ```
 */
export const memoKeys = {
  all: ['memos'] as const,
  lists: () => [...memoKeys.all, 'list'] as const,
  list: (filters?: MemoFilters) => [...memoKeys.lists(), filters ?? {}] as const,
  details: () => [...memoKeys.all, 'detail'] as const,
  detail: (id: string) => [...memoKeys.details(), id] as const,
};

/**
 * Memos API methods
 */
export const memosApi = {
  /**
   * List all memos for the current user
   */
  list: (filters?: MemoFilters): Promise<Memo[]> => {
    const params = new URLSearchParams();
    if (filters?.status) params.set('status', filters.status);
    if (filters?.startDate) params.set('start_date', filters.startDate);
    if (filters?.endDate) params.set('end_date', filters.endDate);
    if (filters?.limit) params.set('limit', String(filters.limit));
    if (filters?.offset) params.set('offset', String(filters.offset));
    
    const query = params.toString();
    return api.get<Memo[]>(`/memos${query ? `?${query}` : ''}`);
  },

  /**
   * Get a single memo by ID
   */
  get: (id: string): Promise<Memo> => {
    return api.get<Memo>(`/memos/${id}`);
  },

  /**
   * Upload transcript only (no audio storage).
   * Use when real-time transcription already produced the transcript.
   */
  uploadTranscript: (transcript: string): Promise<UploadMemoResponse> => {
    return api.post<UploadMemoResponse>('/memos/upload-transcript', { transcript });
  },

  /**
   * Upload audio file for transcription (no storage - transcribe in memory).
   * Use when no real-time transcript available (e.g. file upload).
   */
  upload: (audioBlob: Blob): Promise<UploadMemoResponse> => {
    return api.upload<UploadMemoResponse>('/memos/upload', audioBlob, 'audio');
  },

  /**
   * Upload audio with progress tracking.
   * When transcript is provided, uses transcript-only endpoint (no audio sent).
   * 
   * @param audioBlob - Audio file (ignored when transcript provided)
   * @param onProgress - Progress callback (0-100)
   * @param transcript - Optional pre-transcribed text (from real-time) - uses transcript-only when set
   */
  uploadWithProgress: (
    audioBlob: Blob,
    onProgress: (progress: number) => void,
    transcript?: string
  ): Promise<UploadMemoResponse> => {
    if (transcript?.trim()) {
      onProgress(100);
      return api.post<UploadMemoResponse>('/memos/upload-transcript', { transcript });
    }
    return api.uploadWithProgress<UploadMemoResponse>(
      '/memos/upload',
      audioBlob,
      'audio',
      onProgress
    );
  },

  /**
   * Approve a memo and update CRM
   * 
   * Optionally accepts edited extraction data.
   * Backend will push the data to the connected CRM.
   */
  approve: (id: string, payload?: ApproveMemoPayload): Promise<Memo> => {
    return api.post<Memo>(`/memos/${id}/approve`, payload);
  },

  /**
   * Reject a memo
   * 
   * Marks the memo as rejected, no CRM update happens.
   */
  reject: (id: string): Promise<Memo> => {
    return api.post<Memo>(`/memos/${id}/reject`);
  },

  /**
   * Re-extract data from a memo
   * 
   * Re-runs the GPT-5-mini extraction on the existing transcript.
   * Useful when the initial extraction was wrong.
   */
  reExtract: (id: string): Promise<Memo> => {
    return api.post<Memo>(`/memos/${id}/re-extract`);
  },

  /**
   * Delete a memo
   * 
   * Removes the memo and its audio file permanently.
   */
  delete: (id: string): Promise<void> => {
    return api.delete<void>(`/memos/${id}`);
  },
};


