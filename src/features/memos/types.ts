/**
 * Types for the Memos feature
 * 
 * Core entities for voice memo recording, processing, and approval.
 */

import type { ID, ISODateString, Nullable } from '@/shared/types/common';

// ============================================
// STATUS TYPES
// ============================================

/**
 * Memo status through its lifecycle
 * 
 * Flow: uploading → transcribing → extracting → pending_review → approved/rejected
 * Any stage can transition to 'failed' on error
 */
export type MemoStatus =
  | 'uploading'       // Audio being uploaded to storage
  | 'transcribing'    // Deepgram processing audio
  | 'extracting'      // LLM extracting structured data
  | 'pending_review'  // Waiting for user to approve
  | 'approved'        // User approved, CRM updated
  | 'rejected'        // User rejected the extraction
  | 'failed';         // Processing error occurred

/**
 * Check if memo is in a processing state (not actionable by user)
 */
export function isProcessing(status: MemoStatus): boolean {
  return ['uploading', 'transcribing', 'extracting'].includes(status);
}

/**
 * Check if memo is in a final state (no more transitions)
 */
export function isFinalState(status: MemoStatus): boolean {
  return ['approved', 'rejected', 'failed'].includes(status);
}

// ============================================
// EXTRACTION TYPES
// ============================================

/**
 * Confidence scores for extracted fields
 */
export interface ExtractionConfidence {
  /** Overall extraction confidence (0-1) */
  overall: number;
  /** Per-field confidence scores */
  fields: Record<string, number>;
}

/**
 * Extracted CRM data from voice memo transcript
 * 
 * All fields are nullable because they may not be mentioned in the memo.
 * The LLM will set fields to null if not present/unclear.
 */
export interface MemoExtraction {
  // ---- Deal Information ----
  /** Company or organization name */
  companyName: Nullable<string>;
  /** Deal value/amount */
  dealAmount: Nullable<number>;
  /** Currency code (EUR, USD, etc.) */
  dealCurrency: string;
  /** Pipeline stage (Discovery, Proposal, etc.) */
  dealStage: Nullable<string>;
  /** Expected close date (ISO format) */
  closeDate: Nullable<ISODateString>;

  // ---- Contact Information ----
  /** Primary contact name */
  contactName: Nullable<string>;
  /** Contact's job title/role */
  contactRole: Nullable<string>;
  /** Contact's email address */
  contactEmail: Nullable<string>;
  /** Contact's phone number */
  contactPhone: Nullable<string>;

  // ---- Meeting Intelligence ----
  /** Brief summary of the meeting (2-3 sentences) */
  summary: string;
  /** Pain points or problems mentioned */
  painPoints: string[];
  /** Action items and next steps */
  nextSteps: string[];
  /** Competitors mentioned */
  competitors: string[];
  /** Objections or concerns raised */
  objections: string[];
  /** Decision makers identified */
  decisionMakers: string[];

  // ---- Confidence ----
  /** Confidence scores for the extraction */
  confidence: ExtractionConfidence;

  /** Raw LLM extraction with dynamic CRM fields (deal_ftes_active, price_per_fte_eur, etc.) */
  raw_extraction?: Record<string, unknown>;
}

/**
 * Create an empty extraction (for form initialization)
 */
export function createEmptyExtraction(): MemoExtraction {
  return {
    companyName: null,
    dealAmount: null,
    dealCurrency: 'EUR',
    dealStage: null,
    closeDate: null,
    contactName: null,
    contactRole: null,
    contactEmail: null,
    contactPhone: null,
    summary: '',
    painPoints: [],
    nextSteps: [],
    competitors: [],
    objections: [],
    decisionMakers: [],
    confidence: {
      overall: 0,
      fields: {},
    },
  };
}

// ============================================
// MEMO ENTITY
// ============================================

/**
 * Voice memo entity
 * 
 * Represents a single voice memo through its entire lifecycle:
 * recording → transcription → extraction → approval → CRM update
 */
export interface Memo {
  /** Unique identifier */
  id: ID;
  /** Owner user ID */
  userId: ID;
  /** Current status in the pipeline */
  status: MemoStatus;

  // ---- Audio ----
  /** URL to the audio file in storage */
  audioUrl: string;
  /** Duration of the audio in seconds */
  audioDuration: number;

  // ---- Transcription ----
  /** Full transcript text from Deepgram */
  transcript: Nullable<string>;
  /** Transcription confidence (0-1) */
  transcriptConfidence: Nullable<number>;

  // ---- Extraction ----
  /** Extracted structured data */
  extraction: Nullable<MemoExtraction>;

  // ---- Error ----
  /** Error message if status is 'failed' */
  errorMessage: Nullable<string>;

  // ---- Timestamps ----
  /** When the memo was created */
  createdAt: ISODateString;
  /** When processing completed (transcription + extraction) */
  processedAt: Nullable<ISODateString>;
  /** When the user approved the memo */
  approvedAt: Nullable<ISODateString>;
}

// ============================================
// API TYPES
// ============================================

/**
 * Filters for listing memos
 */
export interface MemoFilters {
  /** Filter by status */
  status?: MemoStatus;
  /** Start date for createdAt range */
  startDate?: ISODateString;
  /** End date for createdAt range */
  endDate?: ISODateString;
  /** Number of items to return */
  limit?: number;
  /** Number of items to skip */
  offset?: number;
}

/**
 * Response from memo upload endpoint
 */
export interface UploadMemoResponse {
  /** Created memo ID */
  id: ID;
  /** Initial status (uploading) */
  status: MemoStatus;
  /** URL to poll for status updates */
  statusUrl: string;
}

/**
 * Payload for approving a memo
 */
export interface ApproveMemoPayload {
  /** Edited extraction data (only changed fields) */
  extraction?: Partial<MemoExtraction>;
}

/**
 * Usage analytics (real data from memos)
 */
export interface UsageWeeklyDay {
  day: string;
  memos: number;
}

export interface UsageActivity {
  action: string;
  company: string;
  time: string;
  type: 'memo' | 'sync';
}

export interface UsageResponse {
  total_memos: number;
  approved_count: number;
  this_week_memos: number;
  this_week_approved: number;
  time_saved_hours: number;
  this_week_time_saved_hours: number;
  accuracy_pct: number | null;
  weekly: UsageWeeklyDay[];
  recent_activity: UsageActivity[];
}

// ============================================
// UI TYPES
// ============================================

/**
 * Field edit state for the approval form
 */
export interface FieldEditState {
  /** Original value from extraction */
  original: unknown;
  /** Current edited value */
  current: unknown;
  /** Whether the field has been modified */
  isDirty: boolean;
  /** Confidence score for this field */
  confidence: number;
}


