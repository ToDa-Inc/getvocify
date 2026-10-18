/** The sales process API (/sales-process): the company's own interaction types, and which ones each member runs. */

import { api, ApiError } from "@/shared/lib/api-client";
import type { SavedType, Stage } from "@/lib/sales-process";

const BASE = "/sales-process";

export type ProcessType = SavedType & { position: number; status: string | null };
export type MemberTypes = { members: Record<string, string[] | null>; invitations: Record<string, string[] | null> };

/** The API says the tables are not in the database yet: a calm "come back soon", not a failure. */
export function isNotActivated(error: unknown): boolean {
  if (!(error instanceof ApiError) || error.status !== 503) return false;
  return (error.data as { detail?: { code?: string } } | null | undefined)?.detail?.code === "not_activated";
}

export const salesProcessApi = {
  get: () => api.get<{ types: ProcessType[] }>(BASE),
  put: (body: { types: { key?: string; label: string; stage: Stage; goal?: string; recognize?: string }[] }) => api.put<{ types: ProcessType[] }>(BASE, body),
  members: () => api.get<MemberTypes>(`${BASE}/members`),
  setMember: (memberId: string, types: string[] | null) =>
    api.put<{ types: string[] | null; sales_role: string }>(`${BASE}/members/${encodeURIComponent(memberId)}`, { types }),
};
