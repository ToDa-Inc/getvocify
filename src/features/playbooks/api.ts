/** Playbooks v2 API (plan §12). One place for every call the playbook screens make. */

import { api, ApiError } from "@/shared/lib/api-client";
import type { draftPayload, EditorSnapshot } from "@/lib/playbook-editor";
import type { MotionStatus } from "@/lib/playbook-setup";
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
  /** What the playbook was structured from. `source` is the draft/published/empty state. */
  source_doc?: PlaybookSource | null;
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
  structure: (key: string, kind: SourceKind, payload: string, name?: string) =>
    api.post<StructureResult>(`${path(key)}/structure`, { kind, payload, ...(name ? { name } : {}) }),
  catalog: () => api.get<{ types: CatalogType[] }>("/playbooks/catalog"),
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
    const result = await api.post<{ text: string }>("/ask/transcribe", { audio_base64: await blobBase64(blob) });
    return result.text;
  },
};
