/**
 * Types for the Recording feature
 * 
 * Voice recording, audio capture, and upload handling.
 */

// ============================================
// RECORDING STATE
// ============================================

/**
 * Recording states
 */
export type RecordingState = 
  | 'idle'        // Ready to record
  | 'requesting'  // Requesting microphone permission
  | 'recording'   // Currently recording
  | 'paused'      // Recording paused (if supported)
  | 'stopped'     // Recording stopped, ready to upload
  | 'uploading'   // Uploading to server
  | 'error';      // Error occurred

/**
 * Recording error types
 */
export type RecordingError =
  | 'permission_denied'      // User denied microphone access
  | 'not_supported'          // Browser doesn't support MediaRecorder
  | 'no_audio_device'        // No microphone found
  | 'recording_failed'       // Error during recording
  | 'upload_failed'          // Error uploading audio
  | 'file_too_large'         // Audio file exceeds size limit
  | 'duration_too_short'     // Recording too short
  | 'duration_too_long'      // Recording too long
  | 'unknown';               // Unknown error

/**
 * Get user-friendly error message
 */
export function getRecordingErrorMessage(error: RecordingError): string {
  switch (error) {
    case 'permission_denied':
      return 'Microphone access was denied. Please allow microphone access in your browser settings.';
    case 'not_supported':
      return 'Your browser does not support audio recording. Please try Chrome, Firefox, or Safari.';
    case 'no_audio_device':
      return 'No microphone was found. Please connect a microphone and try again.';
    case 'recording_failed':
      return 'Recording failed. Please try again.';
    case 'upload_failed':
      return 'Failed to upload audio. Please check your connection and try again.';
    case 'file_too_large':
      return 'Recording is too large. Please record a shorter memo (max 3 minutes).';
    case 'duration_too_short':
      return 'Recording is too short. Please record at least 5 seconds.';
    case 'duration_too_long':
      return 'Recording is too long. Please keep your memo under 3 minutes.';
    default:
      return 'An unexpected error occurred. Please try again.';
  }
}

// ============================================
// AUDIO DATA
// ============================================

/**
 * Recorded audio data
 */
export interface RecordedAudio {
  /** Audio blob ready for upload */
  blob: Blob;
  /** Audio URL for playback preview */
  url: string;
  /** Duration in seconds */
  duration: number;
  /** MIME type */
  mimeType: string;
  /** File size in bytes */
  size: number;
}

/**
 * Audio visualization data
 */
export interface AudioVisualization {
  /** Current audio level (0-1) for waveform */
  level: number;
  /** Array of recent levels for waveform display */
  levels: number[];
  /** Whether there's audio activity */
  isActive: boolean;
}

// ============================================
// UPLOAD STATE
// ============================================

/**
 * Upload progress state
 */
export interface UploadProgress {
  /** Upload progress percentage (0-100) */
  percent: number;
  /** Bytes uploaded */
  loaded: number;
  /** Total bytes to upload */
  total: number;
  /** Whether upload is complete */
  complete: boolean;
}

// ============================================
// HOOK RETURN TYPES
// ============================================

/**
 * Return type for useMediaRecorder hook
 */
export interface UseMediaRecorderReturn {
  /** Current recording state */
  state: RecordingState;
  /** Current recording duration in seconds */
  duration: number;
  /** Error that occurred (if state is 'error') */
  error: RecordingError | null;
  /** Recorded audio data (if state is 'stopped') */
  audio: RecordedAudio | null;
  /** Audio visualization data for waveform */
  visualization: AudioVisualization;
  /** The active MediaStream (shared with transcription) */
  stream: MediaStream | null;
  /** Start recording */
  start: () => Promise<MediaStream | null>;
  /** Stop recording */
  stop: () => void;
  /** Cancel recording (discard audio) */
  cancel: () => void;
  /** Reset to idle state */
  reset: () => void;
}

/**
 * Return type for useAudioUpload hook
 */
export interface UseAudioUploadReturn {
  /** Upload audio (or transcript when provided - transcript-only, no audio sent) */
  upload: (audio: RecordedAudio, transcript?: string) => Promise<string>;
  /** Upload transcript only - use when real-time transcription or meeting transcript paste */
  uploadTranscriptOnly: (
    transcript: string,
    options?: { sourceType?: 'voice_memo' | 'meeting_transcript' },
  ) => Promise<string>;
  /** Upload transcript and start extraction in one call - use when user already reviewed */
  uploadTranscriptAndExtract: (transcript: string) => Promise<string>;
  /** Current upload progress */
  progress: UploadProgress | null;
  /** Whether upload is in progress */
  isUploading: boolean;
  /** Upload error */
  error: string | null;
  /** Reset upload state */
  reset: () => void;
}

/**
 * Transcript data for a specific provider
 */
export interface ProviderTranscript {
  interim: string;
  final: string;
  full: string;
}

/**
 * Return type for useRealtimeTranscription hook
 */
export interface UseRealtimeTranscriptionReturn {
  /** Whether WebSocket is connected */
  isConnected: boolean;
  /** Whether transcription is active */
  isTranscribing: boolean;
  /** Error message if any */
  error: string | null;
  /** Primary interim transcript (Deepgram) */
  interimTranscript: string;
  /** Primary final transcript (Deepgram) */
  finalTranscript: string;
  /** Primary full transcript (Deepgram) */
  fullTranscript: string;
  /** Multi-provider transcripts (deepgram, speechmatics, etc.) */
  providerTranscripts: Record<string, ProviderTranscript>;
  /** Start real-time transcription */
  start: (stream?: MediaStream) => Promise<void>;
  /** Stop real-time transcription */
  stop: () => void;
  /** Reset transcription state */
  reset: () => void;
}

// ============================================
// FILE UPLOAD
// ============================================

/**
 * Supported audio file types for upload
 */
export const SUPPORTED_AUDIO_TYPES = [
  'audio/webm',
  'audio/mp3',
  'audio/mpeg',
  'audio/wav',
  'audio/wave',
  'audio/x-wav',
  'audio/m4a',
  'audio/mp4',
  'audio/x-m4a',
] as const;

/**
 * Check if a file is a supported audio type
 */
export function isSupportedAudioType(file: File): boolean {
  return SUPPORTED_AUDIO_TYPES.includes(file.type as typeof SUPPORTED_AUDIO_TYPES[number]);
}

/**
 * Get human-readable file size
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}


