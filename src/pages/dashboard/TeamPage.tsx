import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Users, Mail, Trash2, RefreshCw } from "lucide-react";
import { useAuth } from "@/features/auth";
import { companyApi, companyKeys } from "@/features/company/api";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { VocifyLoader } from "@/components/ui/vocify-loader";

const TeamPage = () => {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"member" | "admin">("member");
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);

  const canManage = user?.company?.role === "owner" || user?.company?.role === "admin";

  const { data: company, isLoading: companyLoading } = useQuery({
    queryKey: companyKeys.detail(),
    queryFn: () => companyApi.get(),
  });

  const { data: roster, isLoading: rosterLoading } = useQuery({
    queryKey: companyKeys.members(),
    queryFn: () => companyApi.listMembers(),
  });

  const inviteMutation = useMutation({
    mutationFn: () => companyApi.invite(inviteEmail.trim(), inviteRole),
    onSuccess: (res) => {
      setInviteEmail("");
      setInviteUrl(res.inviteUrl ?? null);
      queryClient.invalidateQueries({ queryKey: companyKeys.all });
    },
  });

  const revokeMutation = useMutation({
    mutationFn: (id: string) => companyApi.revokeInvite(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: companyKeys.all }),
  });

  const resendMutation = useMutation({
    mutationFn: (id: string) => companyApi.resendInvite(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: companyKeys.all }),
  });

  const removeMutation = useMutation({
    mutationFn: (id: string) => companyApi.removeMember(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: companyKeys.all }),
  });

  if (companyLoading || rosterLoading) {
    return (
      <div className="flex justify-center min-h-[400px] items-center">
        <VocifyLoader size="lg" label="Loading team..." />
      </div>
    );
  }

  const seatsLabel = company
    ? `${company.seatsUsed} of ${company.seatLimit} seats used`
    : "";

  return (
    <div className={`max-w-3xl mx-auto space-y-8 ${THEME_TOKENS.motion.fadeIn}`}>
      <div className={THEME_TOKENS.dashboardHeader}>
        <h1 className={THEME_TOKENS.typography.pageTitle}>
          Team <span className={THEME_TOKENS.typography.accentTitle}>workspace</span>
        </h1>
        <p className={THEME_TOKENS.typography.body}>
          {company?.name ?? "Your workspace"} · {seatsLabel}. Members share CRM, glossary, and product context.
        </p>
      </div>

      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6`}>
        <div className="flex items-center gap-2 mb-4">
          <Users className="h-4 w-4 text-beige" />
          <h2 className={THEME_TOKENS.typography.sectionTitle}>Members</h2>
        </div>
        <div className="divide-y divide-border">
          {(roster?.members ?? []).map((m) => (
            <div key={m.id} className="py-3 flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-medium">{m.fullName || m.email}</p>
                <p className="text-xs text-muted-foreground">{m.email} · {m.role}</p>
              </div>
              {canManage && m.userId !== user?.id && m.role !== "owner" && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-destructive"
                  onClick={() => removeMutation.mutate(m.id)}
                >
                  Remove
                </Button>
              )}
            </div>
          ))}
        </div>
      </div>

      {(roster?.pendingInvites?.length ?? 0) > 0 && (
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6`}>
            <h2 className={`${THEME_TOKENS.typography.sectionTitle} mb-4`}>Pending invites</h2>
          <div className="space-y-2">
            {roster!.pendingInvites.map((inv) => (
              <div key={inv.id} className="flex items-center justify-between gap-3 py-2">
                <div>
                  <p className="text-sm">{inv.email}</p>
                  <p className="text-xs text-muted-foreground">{inv.role} · expires {new Date(inv.expiresAt).toLocaleDateString()}</p>
                </div>
                {canManage && (
                  <div className="flex gap-2">
                    <Button variant="ghost" size="icon" onClick={() => resendMutation.mutate(inv.id)}>
                      <RefreshCw className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="icon" onClick={() => revokeMutation.mutate(inv.id)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {canManage && (
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 space-y-4`}>
          <div className="flex items-center gap-2">
            <Mail className="h-4 w-4 text-beige" />
            <h2 className={THEME_TOKENS.typography.sectionTitle}>Invite teammate</h2>
          </div>
          <p className="text-xs text-muted-foreground">
            Each pending invite reserves a seat until accepted or revoked. Remove a member to free a seat for someone else.
          </p>
          <div className="flex flex-wrap gap-3">
            <Input
              type="email"
              placeholder="colleague@company.com"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              className="max-w-xs"
            />
            <select
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value as "member" | "admin")}
              className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="member">Member</option>
              <option value="admin">Admin</option>
            </select>
            <Button
              disabled={!inviteEmail.trim() || inviteMutation.isPending || (company?.seatsAvailable ?? 0) <= 0}
              onClick={() => inviteMutation.mutate()}
            >
              Send invite
            </Button>
          </div>
          {inviteUrl && (
            <p className="text-xs text-muted-foreground break-all">
              Email could not be sent. Share this link: {inviteUrl}
            </p>
          )}
        </div>
      )}
    </div>
  );
};

export default TeamPage;
