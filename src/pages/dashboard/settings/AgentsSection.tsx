import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, KeyRound, Link2, LogIn, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ConfirmAction } from "@/components/ui/confirm-action";
import { IconAction } from "@/components/ui/icon-action";
import { SettingsRow, SettingsSection } from "@/components/ui/settings-card";
import { Segmented } from "@/components/ui/segmented";
import { Switch } from "@/components/ui/switch";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { mcpApi, mcpKeys, type McpSettings } from "@/lib/api/mcp";
import { useLanguage } from "@/lib/i18n";

const codeBox = "rounded-lg bg-muted/60 px-3 py-2 font-mono text-xs text-foreground break-all";
const KEY_PLACEHOLDER = "YOUR_VOCIFY_API_KEY";

type Client = "claude-code" | "cursor" | "desktop";

const CLIENTS: { value: Client; label: string }[] = [
  { value: "claude-code", label: "Claude Code" },
  { value: "cursor", label: "Cursor" },
  { value: "desktop", label: "Claude Desktop" },
];

/** What each client needs, filled with the server URL and (right after creating it) the key itself. */
function snippet(client: Client, url: string, key: string): string {
  if (client === "claude-code") {
    return `claude mcp add --transport http vocify ${url} --header "Authorization: Bearer ${key}"`;
  }
  if (client === "cursor") {
    return JSON.stringify({ mcpServers: { vocify: { url, headers: { Authorization: `Bearer ${key}` } } } }, null, 2);
  }
  // Claude Desktop's config file, through mcp-remote. No space after the colon: its README notes a bug with
  // spaces in args on some clients, so the value travels in an env var.
  return JSON.stringify(
    {
      mcpServers: {
        vocify: {
          command: "npx",
          args: ["-y", "mcp-remote", url, "--header", "Authorization:${VOCIFY_AUTH}"],
          env: { VOCIFY_AUTH: `Bearer ${key}` },
        },
      },
    },
    null,
    2,
  );
}

function useCopy() {
  const { t } = useLanguage();
  return async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success(t.product.agentsCopied);
    } catch {
      toast.error(t.product.agentsSaveFailed);
    }
  };
}

function CopyRow({ value, label }: { value: string; label: string }) {
  const copy = useCopy();
  return (
    <div className="flex items-start gap-2">
      <pre className={`${codeBox} min-w-0 flex-1 whitespace-pre-wrap`}>{value}</pre>
      <IconAction label={label} onClick={() => void copy(value)}>
        <Copy className="h-4 w-4" strokeWidth={1.5} />
      </IconAction>
    </div>
  );
}

function formatDate(value: string | null | undefined, language: string): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString(language === "ES" ? "es" : "en", { dateStyle: "medium" });
}

/** Settings → AI agents: connect an agent to Vocify's MCP server, by signing in or with an API key. */
const AgentsSection = () => {
  const { t, language } = useLanguage();
  const queryClient = useQueryClient();
  const [client, setClient] = useState<Client>("claude-code");
  const [newKey, setNewKey] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<"revoke" | "regenerate" | null>(null);
  const [memberToRevoke, setMemberToRevoke] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery({ queryKey: mcpKeys.settings(), queryFn: () => mcpApi.settings() });
  const grants = useQuery({
    queryKey: mcpKeys.grants(),
    queryFn: () => mcpApi.grants(),
    enabled: Boolean(data?.enabled),
  });

  const setSettings = (next: McpSettings) => queryClient.setQueryData(mcpKeys.settings(), next);
  const refresh = () => queryClient.invalidateQueries({ queryKey: mcpKeys.settings() });
  const failed = () => toast.error(t.product.agentsSaveFailed);

  const update = useMutation({ mutationFn: mcpApi.update, onSuccess: setSettings, onError: failed });
  const createKey = useMutation({
    mutationFn: mcpApi.createKey,
    onSuccess: (created) => {
      setNewKey(created.key);
      setConfirm(null);
      void refresh();
    },
    onError: failed,
  });
  const revokeKey = useMutation({
    mutationFn: mcpApi.revokeKey,
    onSuccess: () => {
      setNewKey(null);
      setConfirm(null);
      void refresh();
    },
    onError: failed,
  });
  const revokeMember = useMutation({
    mutationFn: (userId: string) => mcpApi.revokeMemberKey(userId),
    onSuccess: () => {
      setMemberToRevoke(null);
      void refresh();
    },
    onError: failed,
  });
  const revokeGrant = useMutation({
    mutationFn: (clientId: string) => mcpApi.revokeGrant(clientId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: mcpKeys.grants() }),
    onError: failed,
  });

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <VocifySpinner size={24} />
      </div>
    );
  }
  if (isError || !data) {
    return <p className="text-sm text-muted-foreground">{t.product.agentsLoadFailed}</p>;
  }

  const connected = grants.data?.grants ?? [];
  const membersWithKey = (data.members ?? []).filter((m) => m.has_key);
  const memberName = membersWithKey.find((m) => m.user_id === memberToRevoke)?.name ?? "";

  return (
    <div className="mx-auto max-w-[680px] space-y-8">
      <SettingsSection label={t.product.agentsTitle}>
        <SettingsRow
          icon={Link2}
          title={t.product.agentsServerUrl}
          description={t.product.agentsHelper}
          below={
            data.enabled ? (
              <CopyRow value={data.server_url} label={t.product.agentsCopy} />
            ) : (
              <p className="text-sm text-muted-foreground">
                {t.product.agentsOff} {data.can_manage ? null : t.product.agentsOffMember}
              </p>
            )
          }
        />
        {data.enabled && (
          <>
            <SettingsRow
              icon={LogIn}
              title={t.product.agentsAppsTitle}
              description={t.product.agentsSignInHelper}
              below={
                connected.length === 0 ? (
                  <p className="text-xs text-muted-foreground">{t.product.agentsAppsEmpty}</p>
                ) : (
                  <ul className="divide-y divide-dashed divide-border/60">
                    {connected.map((grant) => (
                      <li key={grant.client.client_id} className="flex items-center justify-between gap-4 py-2">
                        <div className="min-w-0">
                          <p className="truncate text-sm text-foreground">{grant.client.client_name || grant.client.client_uri}</p>
                          <p className="text-xs text-muted-foreground">
                            {t.product.agentsAppsConnectedOn} {formatDate(grant.granted_at, language)}
                          </p>
                        </div>
                        <Button
                          type="button"
                          variant="dangerGhost"
                          size="text"
                          disabled={revokeGrant.isPending}
                          onClick={() => revokeGrant.mutate(grant.client.client_id)}
                        >
                          {t.product.agentsAppsDisconnect}
                        </Button>
                      </li>
                    ))}
                  </ul>
                )
              }
            />
            <SettingsRow
              icon={KeyRound}
              title={t.product.agentsKeyTitle}
              description={
                data.key.has_key ? (
                  <>
                    <span className="font-mono">{data.key.prefix}…</span> · {t.product.agentsKeyCreatedOn}{" "}
                    {formatDate(data.key.created_at, language)}
                  </>
                ) : (
                  t.product.agentsKeyHelper
                )
              }
              below={
                newKey || data.key.has_key ? (
                  <div className="space-y-3">
                    {newKey ? (
                      <div className="space-y-1.5">
                        <CopyRow value={newKey} label={t.product.agentsCopy} />
                        <p className="text-xs text-warning" role="status">{t.product.agentsKeyShownOnce}</p>
                      </div>
                    ) : null}
                    <Segmented<Client> value={client} onValueChange={setClient} options={CLIENTS} aria-label={t.product.agentsSetupTitle} />
                    <CopyRow value={snippet(client, data.server_url, newKey ?? KEY_PLACEHOLDER)} label={t.product.agentsCopy} />
                  </div>
                ) : null
              }
            >
              {data.key.has_key ? (
                <>
                  <Button type="button" variant="quiet" size="text" onClick={() => setConfirm("regenerate")}>
                    {t.product.agentsKeyRegenerate}
                  </Button>
                  <Button type="button" variant="dangerGhost" size="text" onClick={() => setConfirm("revoke")}>
                    {t.product.agentsKeyRevoke}
                  </Button>
                </>
              ) : (
                <Button type="button" size="sm" className="rounded-full" disabled={createKey.isPending} onClick={() => createKey.mutate()}>
                  {createKey.isPending ? <VocifySpinner size={14} tone="onFill" /> : t.product.agentsKeyCreate}
                </Button>
              )}
            </SettingsRow>
          </>
        )}
      </SettingsSection>

      {data.can_manage && (
        <SettingsSection label={t.product.agentsWorkspaceTitle}>
          <SettingsRow title={t.product.agentsWorkspaceEnable} description={t.product.agentsWorkspaceEnableHelper}>
            <Switch
              checked={data.enabled}
              disabled={update.isPending}
              onCheckedChange={(enabled) => update.mutate({ enabled })}
              aria-label={t.product.agentsWorkspaceEnable}
            />
          </SettingsRow>
          <SettingsRow title={t.product.agentsWorkspaceTranscripts} description={t.product.agentsWorkspaceTranscriptsHelper}>
            <Switch
              checked={data.transcripts_enabled}
              disabled={update.isPending || !data.enabled}
              onCheckedChange={(transcripts_enabled) => update.mutate({ transcripts_enabled })}
              aria-label={t.product.agentsWorkspaceTranscripts}
            />
          </SettingsRow>
          {membersWithKey.length > 0 && (
            <SettingsRow
              title={t.product.agentsMembersTitle}
              below={
                <ul className="max-h-80 divide-y divide-dashed divide-border/60 overflow-y-auto">
                  {membersWithKey.map((member) => (
                    <li key={member.user_id} className="flex items-center justify-between gap-4 py-2">
                      <div className="min-w-0">
                        <p className="truncate text-sm text-foreground">{member.name}</p>
                        <p className="text-xs text-muted-foreground">
                          <span className="font-mono">{member.prefix}…</span> · {formatDate(member.created_at, language)}
                        </p>
                      </div>
                      <IconAction
                        label={t.product.agentsMemberRevoke}
                        tone="danger"
                        pending={revokeMember.isPending && memberToRevoke === member.user_id}
                        onClick={() => setMemberToRevoke(member.user_id)}
                      >
                        <Trash2 className="h-4 w-4" strokeWidth={1.5} />
                      </IconAction>
                    </li>
                  ))}
                </ul>
              }
            />
          )}
        </SettingsSection>
      )}

      <ConfirmAction
        open={confirm !== null}
        onOpenChange={(open) => !open && setConfirm(null)}
        title={confirm === "regenerate" ? t.product.agentsKeyRegenerateTitle : t.product.agentsKeyRevokeTitle}
        description={confirm === "regenerate" ? t.product.agentsKeyRegenerateBody : t.product.agentsKeyRevokeBody}
        confirmLabel={confirm === "regenerate" ? t.product.agentsKeyRegenerate : t.product.agentsKeyRevoke}
        pending={createKey.isPending || revokeKey.isPending}
        onConfirm={() => (confirm === "regenerate" ? createKey.mutate() : revokeKey.mutate())}
      />
      <ConfirmAction
        open={memberToRevoke !== null}
        onOpenChange={(open) => !open && setMemberToRevoke(null)}
        title={`${t.product.agentsMemberRevoke}: ${memberName}`}
        description={t.product.agentsKeyRevokeBody}
        confirmLabel={t.product.agentsKeyRevoke}
        pending={revokeMember.isPending}
        onConfirm={() => memberToRevoke && revokeMember.mutate(memberToRevoke)}
      />
    </div>
  );
};

export default AgentsSection;
