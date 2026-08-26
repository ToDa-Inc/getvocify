/**
 * CRM call recording summaries returned by the backend.
 * Shape matches GET /crm/hubspot/recordings (only CRM with recordings today).
 */

import type { MemoStatus } from '@/features/memos/types';

export interface CrmCallRecording {
  call_id: string;
  title: string;
  timestamp_ms?: number | null;
  timestamp?: string | null;
  duration_ms?: number;
  duration_seconds?: number;
  has_recording: boolean;
  memo_id?: string | null;
  memo_status?: MemoStatus | string | null;
}

export interface ProcessCallRecordingResponse {
  memo_id: string;
  status: string;
  created: boolean;
  processing_started: boolean;
}

export type RecordingActionKind = 'transcribe' | 'continue' | 'view';

export interface RecordingAction {
  label: string;
  action: RecordingActionKind;
  memoId?: string;
}

export interface RecordingStatusPill {
  text: string;
  busy: boolean;
  variant: 'processing' | 'approved' | 'failed' | 'pending';
}
