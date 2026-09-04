/**
 * Shared recording row logic (ported from chrome-extension/popup/popup.js).
 */

import type { ScreeningOutcome } from '@/features/memos/types';
import type {
  CrmCallRecording,
  RecordingAction,
  RecordingStatusPill,
} from '@/features/recordings/types';

const BUSY_STATUSES = new Set(['uploading', 'transcribing', 'extracting']);

export function memoBusyLabel(status: string | null | undefined): string | null {
  if (status === 'uploading') return 'Uploading';
  if (status === 'extracting') return 'Extracting';
  if (status === 'transcribing') return 'Transcribing';
  return null;
}

export function getMemoStatusPill(
  rec: CrmCallRecording,
  screeningOutcome?: ScreeningOutcome | string | null,
): RecordingStatusPill | null {
  const st = rec.memo_status;
  if (!rec.memo_id) return null;
  const busy = memoBusyLabel(st);
  if (busy) return { variant: 'processing', text: busy, busy: true };
  if (st === 'approved') return { variant: 'approved', text: 'Synced', busy: false };
  if (st === 'failed') return { variant: 'failed', text: 'Failed', busy: false };
  if (st === 'pending_review' || st === 'pending_transcript') {
    if (screeningOutcome === 'voicemail') {
      return { variant: 'pending', text: 'Buzón de voz', busy: false };
    }
    if (screeningOutcome === 'no_response') {
      return { variant: 'pending', text: 'Sin respuesta', busy: false };
    }
    return { variant: 'pending', text: 'Review', busy: false };
  }
  return {
    variant: 'processing',
    text: (st || 'processing').replace(/_/g, ' '),
    busy: false,
  };
}

export function getRecordingAction(rec: CrmCallRecording): RecordingAction | null {
  if (!rec.has_recording) return null;
  const st = rec.memo_status;
  if (memoBusyLabel(st)) return null;
  if (!rec.memo_id || st === 'failed' || st === 'rejected') {
    return { label: 'Transcribe', action: 'transcribe' };
  }
  if (st === 'pending_transcript' || st === 'pending_review') {
    return { label: 'Continue', action: 'continue', memoId: rec.memo_id };
  }
  if (st === 'approved') {
    return { label: 'View', action: 'view', memoId: rec.memo_id };
  }
  return { label: 'Transcribe', action: 'transcribe' };
}

export function recordingsNeedPoll(recordings: CrmCallRecording[]): boolean {
  return recordings.some((rec) => BUSY_STATUSES.has(rec.memo_status || ''));
}

export function recordingTimestamp(rec: CrmCallRecording): string | number | null {
  return rec.timestamp ?? rec.timestamp_ms ?? null;
}
