import { api } from "@/shared/lib/api-client";

/** Settings → AI agents: the MCP server's URL, the workspace switches and each user's API key. */

export type McpKeyStatus = { has_key: boolean; prefix: string | null; created_at: string | null };

export type McpMemberKey = McpKeyStatus & { user_id: string; name: string; email: string | null };

export type McpSettings = {
  server_url: string;
  enabled: boolean;
  transcripts_enabled: boolean;
  can_manage: boolean;
  key: McpKeyStatus;
  members?: McpMemberKey[];
};

export type McpCreatedKey = McpKeyStatus & { key: string };

/** An app the user connected by signing in. `client_id` is the id to disconnect it with; `client_uri` its host. */
export type OAuthGrant = {
  client: { client_id: string; client_name?: string | null; client_uri?: string | null };
  granted_at?: string | null;
};

/** The app asking to sign in. `known` is false for any app that is not Claude, ChatGPT, Cursor or VS Code. */
export type OAuthAuthorization = {
  authorization_id: string;
  redirect_uri: string;
  known: boolean;
  client: { client_id: string; client_name?: string | null };
};

export const mcpKeys = {
  all: ["mcp"] as const,
  settings: () => [...mcpKeys.all, "settings"] as const,
  grants: () => [...mcpKeys.all, "grants"] as const,
};

export const mcpApi = {
  settings: () => api.get<McpSettings>("/mcp/settings"),
  update: (body: { enabled?: boolean; transcripts_enabled?: boolean }) => api.patch<McpSettings>("/mcp/settings", body),
  createKey: () => api.post<McpCreatedKey>("/mcp/key"),
  revokeKey: () => api.delete("/mcp/key"),
  revokeMemberKey: (userId: string) => api.delete(`/mcp/members/${encodeURIComponent(userId)}/key`),
  grants: () => api.get<{ grants: OAuthGrant[] }>("/oauth/grants"),
  revokeGrant: (clientId: string) => api.delete(`/oauth/grants?client_id=${encodeURIComponent(clientId)}`),
  authorization: (id: string) => api.get<OAuthAuthorization>(`/oauth/authorizations/${encodeURIComponent(id)}`),
  consent: (id: string, action: "approve" | "deny") =>
    api.post<{ redirect_url: string }>(`/oauth/authorizations/${encodeURIComponent(id)}/consent`, { action }),
};
