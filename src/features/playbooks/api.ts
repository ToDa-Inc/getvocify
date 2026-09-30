/** Playbooks v2 API (plan §12). One place for every call the playbook screens make. */

import { api, ApiError } from "@/shared/lib/api-client";
import type { draftPayload, EditorSnapshot } from "@/lib/playbook-editor";
import type { MotionStatus } from "@/lib/playbook-setup";
import type { Knowledge, KnowledgeDoc } from "@/lib/playbook-knowledge";
import type {
  AppliesTo,
  CatalogType,
  PlaybookDetail,
  PlaybookInsights,
  PlaybookSource,
  SourceKind,
  StructureResult,
} from "@/lib/playbook-doc";

export type EditorDoc = EditorSnapshot & {
  updated_at?: string | null;
  has_live?: boolean;
  /** Switched off: this is the paused version, shown read-only until it is resumed. */
  paused?: boolean;
  /** What the playbook was structured from. `source` is the draft/published/empty state. */
  source_doc?: PlaybookSource | null;
};

/** POST /playbooks/structure: one source for the whole company, split by call type and saved as drafts. */
export type IntakeResult = {
  source: PlaybookSource | null;
  fallback: boolean;
  /** Why the AI path failed when `fallback` is true: shown under the question, not guessed. */
  error?: { kind: "timeout" | "invalid_answer" | "model_error"; detail: string } | null;
  reason: null | "no_process";
  candidates: { key: string; label: string }[];
  types: { sales_motion_key: string; reason: null | "grouped" | "too_short"; editor: EditorDoc }[];
  /** What went to "Vuestra empresa": merged into what was there, never overwriting it. */
  company: (KnowledgeDoc & { filled: string[] }) | null;
};

export type QualificationTemplate = {
  key: "bant" | "meddic" | "meddpicc";
  label: string;
  criteria: Record<"es" | "en", { criterion_id: string; label: string; why?: string; good?: string; bad?: string }[]>;
};

export type PlaybookList = {
  motions: Record<string, MotionStatus>;
  goals?: Record<string, string>;
  details?: Record<string, PlaybookDetail>;
};

const path = (key: string) => `/playbooks/${encodeURIComponent(key)}`;

/** The `detail.code` of a 4xx, when the API sent one. */
export function errorCode(error: unknown): string | null {
  if (!(error instanceof ApiError)) return null;
  const detail = (error.data as { detail?: unknown } | null | undefined)?.detail;
  if (detail && typeof detail === "object" && "code" in detail) return String((detail as { code: unknown }).code);
  return null;
}

export function blobBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const value = String(reader.result || "");
      const comma = value.indexOf(",");
      resolve(comma >= 0 ? value.slice(comma + 1) : value);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

export const playbooksApi = {
  list: () => api.get<PlaybookList>("/playbooks"),
  editor: (key: string) => api.get<EditorDoc>(`${path(key)}/editor`),
  saveDraft: (
    key: string,
    body: ReturnType<typeof draftPayload> & {
      base_updated_at?: string | null;
      source_id?: string | null;
    },
  ) => api.put<EditorDoc>(`${path(key)}/draft`, body),
  discardDraft: (key: string) => api.delete<EditorDoc>(`${path(key)}/draft`),
  publish: (key: string) => api.post<{ motions: Record<string, MotionStatus> }>(`${path(key)}/publish`),
  // Waits on transcription (audio) and up to two model calls, well past the default 20 s.
  structure: (key: string, kind: SourceKind, payload: string, name?: string) =>
    api.post<StructureResult>(
      `${path(key)}/structure`,
      { kind, payload, ...(name ? { name } : {}) },
      { timeoutMs: 120_000 },
    ),
  intake: (kind: SourceKind, payload: string, name?: string) =>
    api.post<IntakeResult>("/playbooks/structure", { kind, payload, ...(name ? { name } : {}) }, { timeoutMs: 120_000 }),
  // Plan §16: switch a playbook off and on, delete it, and undo the delete.
  pause: (key: string) => api.post<PlaybookList>(`${path(key)}/pause`),
  resume: (key: string) => api.post<PlaybookList>(`${path(key)}/resume`),
  remove: (key: string) => api.delete<PlaybookList>(path(key)),
  restore: (key: string) => api.post<PlaybookList>(`${path(key)}/restore`),
  catalog: () => api.get<{ types: CatalogType[] }>("/playbooks/catalog"),
  qualificationTemplates: () => api.get<{ templates: QualificationTemplate[] }>("/playbooks/qualification-templates"),
  company: () => api.get<KnowledgeDoc>("/playbooks/company"),
  saveCompany: (knowledge: Knowledge, baseUpdatedAt: string | null) =>
    api.put<KnowledgeDoc>("/playbooks/company", { knowledge, base_updated_at: baseUpdatedAt }),
  addType: (body: { type_key: string; name: string; applies_to?: AppliesTo }) =>
    api.post<{ motions: Record<string, MotionStatus>; details?: Record<string, PlaybookDetail> }>("/playbooks/types", body),
  saveRule: (key: string, appliesTo: AppliesTo) =>
    api.put<{ sales_motion_key: string; applies_to: AppliesTo }>(`${path(key)}/rule`, { applies_to: appliesTo }),
  dealStages: () => api.get<{ stages: { id: string; label: string }[] }>("/playbooks/deal-stages"),
  insights: (key: string, period: "week" | "month" = "month") =>
    api.get<PlaybookInsights>(`${path(key)}/insights?period=${period}`),
  changeMemoPlaybook: (memoId: string, key: string) =>
    api.post<{ sales_motion_key: string; playbook_version_id: string; status: string }>(
      `/memos/${encodeURIComponent(memoId)}/playbook`,
      { sales_motion_key: key },
    ),
  /** Dictation: the same transcription Ask uses. */
  transcribe: async (blob: Blob) => {
    // A few minutes of explaining the process takes longer to transcribe than an Ask question.
    const result = await api.post<{ text: string }>(
      "/ask/transcribe",
      { audio_base64: await blobBase64(blob) },
      { timeoutMs: 120_000 },
    );
    return result.text;
  },
};
