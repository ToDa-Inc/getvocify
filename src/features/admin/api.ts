import { api } from "@/shared/lib/api-client";
import { getStoredAdminMasterKey } from "@/lib/admin-auth";
import type {
  AdminAccountDetail,
  AdminAccountListItem,
  AdminAccountListResponse,
  AdminImpersonateResponse,
  AdminRuntime,
  AdminStuckMemo,
} from "./types";

export const adminKeys = {
  all: ["admin"] as const,
  accounts: (skip: number, search: string) => [...adminKeys.all, "accounts", skip, search] as const,
  account: (id: string) => [...adminKeys.all, "account", id] as const,
  runtime: () => [...adminKeys.all, "runtime"] as const,
  stuckMemos: () => [...adminKeys.all, "stuck-memos"] as const,
};

function masterHeaders(): HeadersInit {
  const key = getStoredAdminMasterKey();
  return key ? { "X-Master-Key": key } : {};
}

function mapCrm(raw: Record<string, unknown>) {
  return {
    provider: String(raw.provider ?? ""),
    status: String(raw.status ?? ""),
    tokenExpiresAt: (raw.token_expires_at as string) ?? null,
  };
}

function mapListItem(raw: Record<string, unknown>): AdminAccountListItem {
  return {
    id: String(raw.id ?? ""),
    email: String(raw.email ?? ""),
    fullName: (raw.full_name as string) ?? null,
    companyName: (raw.company_name as string) ?? null,
    phone: (raw.phone as string) ?? null,
    createdAt: String(raw.created_at ?? ""),
    lastSignInAt: (raw.last_sign_in_at as string) ?? null,
    crm: Array.isArray(raw.crm) ? raw.crm.map((c) => mapCrm(c as Record<string, unknown>)) : [],
    memoCount: Number(raw.memo_count ?? 0),
    approvedCount: Number(raw.approved_count ?? 0),
    failedCount: Number(raw.failed_count ?? 0),
    lastMemoAt: (raw.last_memo_at as string) ?? null,
  };
}

function mapConfiguration(raw: Record<string, unknown>) {
  return {
    defaultPipelineName: (raw.default_pipeline_name as string) ?? null,
    defaultStageName: (raw.default_stage_name as string) ?? null,
    allowedDealFields: (raw.allowed_deal_fields as string[]) ?? [],
    allowedContactFields: (raw.allowed_contact_fields as string[]) ?? [],
    allowedCompanyFields: (raw.allowed_company_fields as string[]) ?? [],
    allowedLineItemFields: (raw.allowed_line_item_fields as string[]) ?? [],
    autoCreateContacts: raw.auto_create_contacts as boolean | null,
    autoCreateCompanies: raw.auto_create_companies as boolean | null,
    lostLeadStatusValue: (raw.lost_lead_status_value as string) ?? null,
    onHoldLeadStatusValue: (raw.on_hold_lead_status_value as string) ?? null,
  };
}

function mapUsage(raw: Record<string, unknown>) {
  return {
    totalMemos: Number(raw.total_memos ?? 0),
    approvedCount: Number(raw.approved_count ?? 0),
    thisWeekMemos: Number(raw.this_week_memos ?? 0),
    thisWeekApproved: Number(raw.this_week_approved ?? 0),
    timeSavedHours: Number(raw.time_saved_hours ?? 0),
    thisWeekTimeSavedHours: Number(raw.this_week_time_saved_hours ?? 0),
    accuracyPct: raw.accuracy_pct != null ? Number(raw.accuracy_pct) : null,
    weekly: Array.isArray(raw.weekly)
      ? raw.weekly.map((d) => ({
          day: String((d as Record<string, unknown>).day ?? ""),
          memos: Number((d as Record<string, unknown>).memos ?? 0),
        }))
      : [],
    recentActivity: Array.isArray(raw.recent_activity)
      ? raw.recent_activity.map((a) => ({
          action: String((a as Record<string, unknown>).action ?? ""),
          company: String((a as Record<string, unknown>).company ?? ""),
          time: String((a as Record<string, unknown>).time ?? ""),
          type: String((a as Record<string, unknown>).type ?? ""),
        }))
      : [],
  };
}

function mapDetail(raw: Record<string, unknown>): AdminAccountDetail {
  return {
    id: String(raw.id ?? ""),
    email: String(raw.email ?? ""),
    fullName: (raw.full_name as string) ?? null,
    companyName: (raw.company_name as string) ?? null,
    phone: (raw.phone as string) ?? null,
    createdAt: String(raw.created_at ?? ""),
    lastSignInAt: (raw.last_sign_in_at as string) ?? null,
    productContext: String(raw.product_context ?? ""),
    sttLanguages: Array.isArray(raw.stt_languages) ? (raw.stt_languages as string[]) : [],
    glossaryLength: Number(raw.glossary_length ?? 0),
    primaryCrmConnectionId: (raw.primary_crm_connection_id as string) ?? null,
    connections: Array.isArray(raw.connections)
      ? raw.connections.map((c) => {
          const conn = c as Record<string, unknown>;
          const cfg = conn.configuration as Record<string, unknown> | null;
          return {
            id: String(conn.id ?? ""),
            provider: String(conn.provider ?? ""),
            status: String(conn.status ?? ""),
            tokenExpiresAt: (conn.token_expires_at as string) ?? null,
            lastSyncedAt: (conn.last_synced_at as string) ?? null,
            configuration: cfg ? mapConfiguration(cfg) : null,
          };
        })
      : [],
    recentMemos: Array.isArray(raw.recent_memos)
      ? raw.recent_memos.map((m) => {
          const memo = m as Record<string, unknown>;
          return {
            id: String(memo.id ?? ""),
            status: String(memo.status ?? ""),
            source: (memo.source as string) ?? null,
            createdAt: String(memo.created_at ?? ""),
            company: String(memo.company ?? ""),
            errorMessage: (memo.error_message as string) ?? null,
          };
        })
      : [],
    usage: mapUsage((raw.usage as Record<string, unknown>) ?? {}),
  };
}

function mapRuntime(raw: Record<string, unknown>): AdminRuntime {
  return {
    sttProvider: String(raw.stt_provider ?? ""),
    llmProvider: String(raw.llm_provider ?? ""),
    extractionModel: String(raw.extraction_model ?? ""),
    copilotModel: String(raw.copilot_model ?? ""),
    environment: String(raw.environment ?? ""),
  };
}

export const adminApi = {
  listAccounts: async (args: { skip?: number; limit?: number; search?: string }): Promise<AdminAccountListResponse> => {
    const params = new URLSearchParams();
    if (args.skip) params.set("skip", String(args.skip));
    if (args.limit) params.set("limit", String(args.limit));
    if (args.search) params.set("search", args.search);
    const q = params.toString();
    const raw = await api.get<Record<string, unknown>>(`/admin/accounts${q ? `?${q}` : ""}`, {
      headers: masterHeaders(),
    });
    return {
      accounts: Array.isArray(raw.accounts)
        ? raw.accounts.map((a) => mapListItem(a as Record<string, unknown>))
        : [],
      total: Number(raw.total ?? 0),
      skip: Number(raw.skip ?? 0),
      limit: Number(raw.limit ?? 20),
    };
  },

  getAccount: async (id: string): Promise<AdminAccountDetail> => {
    const raw = await api.get<Record<string, unknown>>(`/admin/accounts/${id}`, {
      headers: masterHeaders(),
    });
    return mapDetail(raw);
  },

  impersonate: async (id: string): Promise<AdminImpersonateResponse> => {
    const raw = await api.post<Record<string, unknown>>(`/admin/accounts/${id}/impersonate`, undefined, {
      headers: masterHeaders(),
    });
    const user = (raw.user as Record<string, unknown>) ?? {};
    return {
      user: {
        id: String(user.id ?? ""),
        email: String(user.email ?? ""),
        fullName: (user.full_name as string) ?? null,
        companyName: (user.company_name as string) ?? null,
      },
      accessToken: String(raw.access_token ?? ""),
      refreshToken: String(raw.refresh_token ?? ""),
    };
  },

  stuckMemos: async (): Promise<AdminStuckMemo[]> => {
    const raw = await api.get<Record<string, unknown>>("/admin/stuck-memos", {
      headers: masterHeaders(),
    });
    return Array.isArray(raw.memos)
      ? raw.memos.map((m) => {
          const memo = m as Record<string, unknown>;
          return {
            id: String(memo.id ?? ""),
            userId: String(memo.user_id ?? ""),
            status: String(memo.status ?? ""),
            processingStartedAt: (memo.processing_started_at as string) ?? null,
            errorMessage: (memo.error_message as string) ?? null,
          };
        })
      : [];
  },

  recoverStuckMemos: () =>
    api.post<Record<string, unknown>>("/admin/recover-stuck-memos", undefined, {
      headers: masterHeaders(),
    }),

  runtime: async (): Promise<AdminRuntime> => {
    const raw = await api.get<Record<string, unknown>>("/admin/runtime", {
      headers: masterHeaders(),
    });
    return mapRuntime(raw);
  },
};
