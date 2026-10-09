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
  ApproveMemoPayload,
  UsageResponse,
  FollowupView,
  FollowupActionPayload,
  FollowupSendPayload,
} from './types';
import type { AfterCallContext, AfterCallHint, OutcomePayload } from '@/lib/after-call-flow';
import type { Channel } from '@/lib/interactions';

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
  usage: () => [...memoKeys.all, 'usage'] as const,
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
    if (filters?.scope) params.set('scope', filters.scope);
    if (filters?.authorUserId) params.set('author_user_id', filters.authorUserId);
    if (filters?.interactionKind) params.set('interaction_kind', filters.interactionKind);
    if (filters?.salesMotionKey) params.set('sales_motion_key', filters.salesMotionKey);
    
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
   * Retag a memo with another type; it is scored again against that type's live playbook.
   */
  setType: (id: string, key: string): Promise<{ sales_motion_key: string; playbook_version_id: string | null; status: string }> => {
    return api.post(`/memos/${encodeURIComponent(id)}/playbook`, { sales_motion_key: key });
  },

  /**
   * Types by channel: move a memo to the other channel. A type that does not belong to it is cleared.
   */
  setChannel: (id: string, kind: 'call' | 'meeting'): Promise<{ sales_motion_key: string | null; interaction_kind: string; status: string }> => {
    return api.post(`/memos/${encodeURIComponent(id)}/playbook`, { interaction_kind: kind });
  },

  /**
   * Get usage analytics (real stats from memos)
   */
  getUsage: (): Promise<UsageResponse> => {
    return api.get<UsageResponse>('/memos/usage');
  },

  /**
   * Upload transcript only (no audio storage).
   * Creates memo and starts CRM field extraction immediately.
   */
  uploadTranscript: (
    transcript: string,
    sourceType?: 'voice_memo' | 'meeting_transcript',
  ): Promise<UploadMemoResponse> => {
    return api.post<UploadMemoResponse>('/memos/upload-transcript', {
      transcript,
      ...(sourceType && { source_type: sourceType }),
    });
  },

  /**
   * Upload transcript and start AI extraction in one call.
   * Use when recording stops with live STT text.
   * Returns memo ID with status "extracting". `interactionKind` is stored on the memo
   * (the web recorder sends voice_note); absent, the backend derives it as before.
   */
  uploadTranscriptAndExtract: (
    transcript: string,
    options: {
      interactionKind?: Channel;
      sourceType?: 'voice_memo' | 'meeting_transcript';
      /** Speakers come from separate audio channels (desktop: mic = rep, meeting audio = them). */
      speakersVerified?: boolean;
      /** What the rep typed while recording; steers the summary. */
      notes?: string;
      /** The HubSpot contact the call was with, known live (desktop). */
      hubspotContactId?: string;
      /** The app the call happened in (desktop), e.g. "Google Meet". */
      callSource?: string;
      /** The call type when the call ended (desktop), and who chose it. */
      salesMotionKey?: string;
      typeSource?: 'rep' | 'vocify';
      /** Names the meeting app showed speaking on the other side (desktop, Zoom). */
      participants?: string[];
      /** A Vocify call (desktop): the memo is that call's, from its live transcript. */
      callSid?: string;
      callDurationSeconds?: number;
      /** When the desktop recording began: links the memo to its calendar meeting. */
      recordingStartedAt?: string;
    } = {},
  ): Promise<UploadMemoResponse> => {
    return api.post<UploadMemoResponse>('/memos/upload-and-extract', {
      transcript,
      source_type: options.sourceType ?? 'voice_memo',
      ...(options.interactionKind && { interaction_kind: options.interactionKind }),
      speakers_verified: Boolean(options.speakersVerified),
      notes: options.notes?.trim() || undefined,
      hubspot_contact_id: options.hubspotContactId || undefined,
      call_source: options.callSource || undefined,
      sales_motion_key: options.salesMotionKey || undefined,
      type_source: options.salesMotionKey ? options.typeSource ?? 'rep' : undefined,
      participants: options.participants?.length ? options.participants : undefined,
      call_sid: options.callSid || undefined,
      call_duration_seconds: options.callDurationSeconds,
      recording_started_at: options.recordingStartedAt || undefined,
    });
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
   * @param transcript - Optional pre-transcribed text (from real-time) - starts extraction when set
   * @param interactionKind - Optional channel stored on the memo (voice_note from the web recorder)
   */
  uploadWithProgress: (
    audioBlob: Blob,
    onProgress: (progress: number) => void,
    transcript?: string,
    interactionKind?: Channel,
  ): Promise<UploadMemoResponse> => {
    if (transcript?.trim()) {
      onProgress(100);
      return memosApi.uploadTranscriptAndExtract(transcript.trim(), { interactionKind });
    }
    return api.uploadWithProgress<UploadMemoResponse>(
      '/memos/upload',
      audioBlob,
      'audio',
      onProgress,
      interactionKind ? { interaction_kind: interactionKind } : undefined,
    );
  },

  /**
   * Approve a memo and update CRM
   * 
   * Optionally accepts edited extraction data.
   * Backend will push the data to the connected CRM.
   */
  /**
   * One click right after a call (Mac notch island): exactly what auto-approve sends, for a
   * memo that knows its contact. Anything that needs a choice is refused: use review.
   */
  approveForContact: (id: string, extraction?: Record<string, unknown>): Promise<Memo> => {
    return api.post<Memo>(`/memos/${id}/approve-contact`, extraction ? { extraction } : {});
  },

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
   * Confirm transcript (user reviewed) and trigger AI extraction.
   * Use when memo is pending_transcript; extraction runs after this.
   */
  confirmTranscript: (id: string, transcript?: string): Promise<{ status: string; message: string }> => {
    return api.post<{ status: string; message: string }>(`/memos/${id}/confirm-transcript`, { transcript });
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
   * Re-transcribe a HubSpot call memo from the recording URL.
   * Uses current call-language settings from the user profile.
   */
  reTranscribe: (id: string): Promise<Memo> => {
    return api.post<Memo>(`/memos/${id}/re-transcribe`);
  },

  /**
   * Delete a memo
   * 
   * Removes the memo and its audio file permanently.
   */
  delete: (id: string): Promise<void> => {
    return api.delete<void>(`/memos/${id}`);
  },

  /**
   * Follow-up draft for a memo (polled while it is being written)
   */
  getFollowup: (id: string): Promise<FollowupView> => {
    return api.get<FollowupView>(`/memos/${id}/followup`);
  },

  /**
   * Record the hand-off (sent or copied) with the rep's final text
   */
  /** The rep won't send this draft (undo: they will after all). Author only. */
  skipFollowup: (id: string, undo = false): Promise<FollowupView> => {
    return api.post<FollowupView>(`/memos/${id}/followup/skip`, { undo });
  },

  /** Whether Vocify drafts follow-up emails for this rep at all. */
  followupPreference: (): Promise<{ suggest: boolean }> => api.get<{ suggest: boolean }>(`/followup-preference`),
  setFollowupPreference: (suggest: boolean): Promise<{ suggest: boolean }> =>
    api.put<{ suggest: boolean }>(`/followup-preference`, { suggest }),

  followupAction: (id: string, payload: FollowupActionPayload): Promise<FollowupView> => {
    return api.post<FollowupView>(`/memos/${id}/followup`, payload);
  },

  /**
   * D9: send the reviewed follow-up from Vocify (FOLLOWUP_SEND_ENABLED). 404s when the
   * company does not have the flag on.
   */
  sendFollowup: (id: string, payload: FollowupSendPayload): Promise<FollowupView> => {
    return api.post<FollowupView>(`/memos/${id}/followup/send`, payload);
  },

  /**
   * Lista 4 T4 (AFTER_CALL_FLOW_ENABLED): what Hoy's after-call panel prefills. 404 with the
   * flag off; 403 on someone else's memo.
   */
  afterCall: (id: string): Promise<AfterCallContext> => {
    return api.get<AfterCallContext>(`/memos/${id}/after-call`);
  },

  /**
   * Lista 4 T4: the outcome of a call whose memo is already approved (auto-approve). A memo
   * still in review takes the same fields on approve instead.
   */
  recordOutcome: (id: string, payload: OutcomePayload): Promise<{ after_call: AfterCallHint }> => {
    return api.post<{ after_call: AfterCallHint }>(`/memos/${id}/outcome`, payload);
  },
};


