import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Mail, RefreshCw, Trash2, Users } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/features/auth";
import { authKeys } from "@/features/auth/api";
import { companyApi, companyKeys } from "@/features/company/api";
import { HUBSPOT_INVITE_EMAIL_HINT } from "@/lib/identity-hints";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { Button } from "@/components/ui/button";
import { ConfirmAction } from "@/components/ui/confirm-action";
import { IconAction } from "@/components/ui/icon-action";
import { Input } from "@/components/ui/input";
import { VocifyLoader, VocifySpinner } from "@/components/ui/vocify-loader";

const ROLE_OPTIONS = [
  {
    value: "member" as const,
    label: "Member",
    hint: "Shared CRM and glossary. Calls stay theirs; owners and admins see every teammate’s labeled activity.",
  },
  {
    value: "admin" as const,
    label: "Admin",
    hint: "Invite the team, and edit CRM fields and offer context.",
  },
];

function apiErrorMessage(error: unknown, fallback: string) {
  if (error && typeof error === "object" && "data" in error) {
    const detail = (error as { data?: { detail?: unknown } }).data?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

const TeamPage = () => {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"member" | "admin">("member");
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<
    | { kind: "remove"; id: string; name: string }
    | { kind: "revoke"; id: string; email: string }
    | null
  >(null);

  const canManage = user?.company?.role === "owner" || user?.company?.role === "admin";

  const { data: company, isLoading: companyLoading } = useQuery({
    queryKey: companyKeys.detail(),
    queryFn: () => companyApi.get(),
  });

  const { data: roster, isLoading: rosterLoading } = useQuery({
    queryKey: companyKeys.members(),
    queryFn: () => companyApi.listMembers(),
  });

  const seatLimit = company?.seatLimit ?? user?.company?.seatLimit ?? 1;
  const seatsUsed = company?.seatsUsed ?? user?.company?.seatsUsed ?? 1;
  const seatsAvailable =
    company?.seatsAvailable ?? Math.max(0, seatLimit - seatsUsed);
  const seatsFull = seatsAvailable <= 0;
  const selectedRole = ROLE_OPTIONS.find((option) => option.value === inviteRole);

  const refreshWorkspace = () => {
    queryClient.invalidateQueries({ queryKey: companyKeys.all });
    queryClient.invalidateQueries({ queryKey: authKeys.me() });
  };

  const inviteMutation = useMutation({
    mutationFn: () => companyApi.invite(inviteEmail.trim(), inviteRole),
    onSuccess: (res) => {
      setInviteEmail("");
      setInviteUrl(res.inviteUrl ?? null);
      refreshWorkspace();
      if (res.emailSent) {
        toast.success("Email has been sent");
      } else if (res.inviteUrl) {
        toast.success("Invite created. Share the link below.");
      } else {
        toast.success("Invite created");
      }
    },
    onError: (error) => {
      toast.error(apiErrorMessage(error, "Could not send invite"));
    },
  });

  const revokeMutation = useMutation({
    mutationFn: (id: string) => companyApi.revokeInvite(id),
    onSuccess: () => {
      refreshWorkspace();
      setConfirm(null);
      toast.success("Invite revoked");
    },
    onError: (error) => {
      toast.error(apiErrorMessage(error, "Could not revoke invite"));
    },
  });

  const resendMutation = useMutation({
    mutationFn: (id: string) => companyApi.resendInvite(id),
    onSuccess: () => {
      refreshWorkspace();
      toast.success("Email has been sent");
    },
    onError: (error) => {
      toast.error(apiErrorMessage(error, "Could not resend invite"));
    },
  });

  const removeMutation = useMutation({
    mutationFn: (id: string) => companyApi.removeMember(id),
    onSuccess: () => {
      refreshWorkspace();
      setConfirm(null);
      toast.success("Member removed");
    },
    onError: (error) => {
      toast.error(apiErrorMessage(error, "Could not remove member"));
    },
  });

  const handleInvite = (event: React.FormEvent) => {
    event.preventDefault();
    const email = inviteEmail.trim();
    if (!email) {
      toast.error("Enter an email address");
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      toast.error("Enter a valid email address");
      return;
    }
    if (seatsFull) {
      toast.error("No seats available. Remove a member or revoke a pending invite first.");
      return;
    }
    inviteMutation.mutate();
  };

  const copyInviteLink = async () => {
    if (!inviteUrl) return;
    try {
      await navigator.clipboard.writeText(inviteUrl);
      toast.success("Invite link copied");
    } catch {
      toast.error("Could not copy the link");
    }
  };

  if (companyLoading || rosterLoading) {
    return (
      <div className={THEME_TOKENS.interaction.pageLoad}>
        <VocifyLoader size="lg" label="Loading team..." />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 md:p-8`}>
        <div className="flex items-start justify-between gap-4 mb-8">
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-beige" />
            <h2 className={THEME_TOKENS.typography.sectionTitle}>Members</h2>
          </div>
          <p className={THEME_TOKENS.typography.capsLabel}>
            {seatsUsed} of {seatLimit} seats
          </p>
        </div>
        <div className="divide-y divide-border/40">
          {(roster?.members ?? []).map((m) => (
            <div key={m.id} className="py-4 first:pt-0 last:pb-0 flex items-center justify-between gap-4">
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground truncate">
                  {m.fullName || m.email}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5 truncate">{m.email}</p>
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <span className="rounded-full border border-border/40 bg-secondary/5 px-3 h-7 inline-flex items-center text-[11px] capitalize text-muted-foreground">
                  {m.role}
                </span>
                {canManage && m.userId !== user?.id && m.role !== "owner" && (
                  <IconAction
                    label={`Remove ${m.fullName || m.email}`}
                    tone="danger"
                    onClick={() =>
                      setConfirm({ kind: "remove", id: m.id, name: m.fullName || m.email })
                    }
                  >
                    <Trash2 className="h-4 w-4" />
                  </IconAction>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {(roster?.pendingInvites?.length ?? 0) > 0 && (
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8`}>
          <h2 className={`${THEME_TOKENS.typography.sectionTitle} mb-6`}>Pending invites</h2>
          <div className="divide-y divide-border/40">
            {roster!.pendingInvites.map((inv) => (
              <div key={inv.id} className="py-4 first:pt-0 last:pb-0 flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-sm text-foreground truncate">{inv.email}</p>
                  <p className="text-xs text-muted-foreground mt-0.5 capitalize">
                    {inv.role} · expires {new Date(inv.expiresAt).toLocaleDateString()}
                  </p>
                </div>
                {canManage && (
                  <div className="flex items-center gap-1 shrink-0">
                    <IconAction
                      label="Resend invite email"
                      pendingLabel="Sending…"
                      pending={resendMutation.isPending && resendMutation.variables === inv.id}
                      onClick={() => resendMutation.mutate(inv.id)}
                    >
                      <RefreshCw className="h-4 w-4" />
                    </IconAction>
                    <IconAction
                      label={`Revoke invite for ${inv.email}`}
                      tone="danger"
                      onClick={() => setConfirm({ kind: "revoke", id: inv.id, email: inv.email })}
                    >
                      <Trash2 className="h-4 w-4" />
                    </IconAction>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {canManage && (
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8`}>
          <div className="mb-5">
            <div className="flex items-center gap-2">
              <Mail className="h-4 w-4 text-beige" />
              <h2 className={THEME_TOKENS.typography.sectionTitle}>Invite teammate</h2>
            </div>
            <p className="text-xs text-muted-foreground mt-1.5">
              Each pending invite reserves a seat until it is accepted or revoked.
            </p>
          </div>

          {seatsFull ? (
            <div className="mb-5 rounded-2xl border border-border/70 bg-secondary/5 px-5 py-3.5">
              <p className="text-sm text-foreground">All seats are in use.</p>
              <p className="text-xs text-muted-foreground mt-1">
                {seatsUsed} of {seatLimit} seats taken. Remove a member to free one,
                or ask Vocify to raise the cap.
              </p>
            </div>
          ) : (
            <p className={`${THEME_TOKENS.typography.capsLabel} mb-5`}>
              {seatsAvailable} seat{seatsAvailable === 1 ? "" : "s"} available
            </p>
          )}

          <form onSubmit={handleInvite} className="space-y-4">
            <div className="space-y-2">
              <label htmlFor="invite-email" className={THEME_TOKENS.typography.capsLabel}>
                Email
              </label>
              <Input
                id="invite-email"
                type="email"
                autoComplete="email"
                placeholder="colleague@company.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold"
              />
              <p className="text-xs text-muted-foreground leading-relaxed">
                {HUBSPOT_INVITE_EMAIL_HINT}
              </p>
            </div>

            <div className="space-y-2">
              <p className={THEME_TOKENS.typography.capsLabel}>Role</p>
              <div className="flex flex-wrap items-center gap-3">
                <div className="inline-flex rounded-full border border-border/40 bg-secondary/5 p-1">
                  {ROLE_OPTIONS.map((option) => {
                    const selected = inviteRole === option.value;
                    return (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => setInviteRole(option.value)}
                        aria-pressed={selected}
                        className={`rounded-full px-4 h-8 text-xs font-medium transition-colors ${
                          selected
                            ? "bg-beige text-cream"
                            : "text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        {option.label}
                      </button>
                    );
                  })}
                </div>
                <Button
                  type="submit"
                  disabled={inviteMutation.isPending || seatsFull}
                  className="rounded-full bg-beige text-cream px-6 h-10"
                >
                  {inviteMutation.isPending ? (
                    <>
                      <VocifySpinner size={12} />
                      Sending…
                    </>
                  ) : (
                    "Send invite"
                  )}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">{selectedRole?.hint}</p>
            </div>
          </form>

          {inviteUrl && (
            <div className="mt-6 rounded-2xl border border-border/70 bg-secondary/5 px-5 py-4 space-y-3">
              <p className="text-xs text-muted-foreground">
                Email could not be sent. Share this link instead.
              </p>
              <p className="text-xs text-foreground break-all">{inviteUrl}</p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="rounded-full"
                onClick={() => void copyInviteLink()}
              >
                <Copy className="h-3.5 w-3.5" />
                Copy link
              </Button>
            </div>
          )}
        </div>
      )}

      <ConfirmAction
        open={confirm !== null}
        onOpenChange={(open) => !open && setConfirm(null)}
        title={confirm?.kind === "revoke" ? "Revoke this invite?" : "Remove this member?"}
        description={
          confirm?.kind === "revoke"
            ? `${confirm.email} will lose their reserved seat and the link will stop working.`
            : confirm
              ? `${confirm.name} will lose access to this workspace.`
              : ""
        }
        confirmLabel={confirm?.kind === "revoke" ? "Revoke invite" : "Remove member"}
        pending={removeMutation.isPending || revokeMutation.isPending}
        onConfirm={() => {
          if (!confirm) return;
          if (confirm.kind === "revoke") revokeMutation.mutate(confirm.id);
          else removeMutation.mutate(confirm.id);
        }}
      />
    </div>
  );
};

export default TeamPage;
