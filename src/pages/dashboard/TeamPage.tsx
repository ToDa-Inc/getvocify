import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Info, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/features/auth";
import { authKeys } from "@/features/auth/api";
import { companyApi, companyKeys } from "@/features/company/api";
import type { SalesRole } from "@/features/company/types";
import { useLanguage } from "@/lib/i18n";
import { HUBSPOT_INVITE_EMAIL_HINT } from "@/lib/identity-hints";
import { SALES_ROLE_OPTIONS, salesRoleLabel } from "@/lib/sales-role";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ConfirmAction } from "@/components/ui/confirm-action";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { IconAction } from "@/components/ui/icon-action";
import { Input } from "@/components/ui/input";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { VocifyLoader, VocifySpinner } from "@/components/ui/vocify-loader";
import { AnimIcon } from "@/components/ui/anim-icon";

const CHIP = "inline-flex h-7 items-center gap-1 rounded-full px-3 text-xs";
const ROLES: SalesRole[] = ["sdr", "ae", "general"];

const pillSelected =
  "rounded-full px-4 h-8 text-xs font-medium transition-colors bg-beige text-cream";
const pillIdle =
  "rounded-full px-4 h-8 text-xs font-medium transition-colors text-muted-foreground hover:text-foreground";

function apiErrorMessage(error: unknown, fallback: string) {
  if (error && typeof error === "object" && "data" in error) {
    const detail = (error as { data?: { detail?: unknown } }).data?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return fallback;
}

/** The commercial type as a chip that is its own control, like the type chip in Interacciones. */
function RoleChip({
  value,
  label,
  options,
  disabled,
  onChange,
}: {
  value: SalesRole;
  label: string;
  options: Record<SalesRole, string>;
  disabled?: boolean;
  onChange: (next: SalesRole) => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={`${label}: ${options[value]}`}
          disabled={disabled}
          className={THEME_TOKENS.interaction.menuChip}
        >
          {options[value]}
          <ChevronDown aria-hidden className="h-3 w-3 opacity-60" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuRadioGroup value={value} onValueChange={(next) => next !== value && onChange(next as SalesRole)}>
          {ROLES.map((role) => (
            <DropdownMenuRadioItem key={role} value={role}>
              {options[role]}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

const TeamPage = () => {
  const { user } = useAuth();
  const { t } = useLanguage();
  const catalog = t.product;
  const queryClient = useQueryClient();
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"member" | "admin">("member");
  const [inviteSalesRole, setInviteSalesRole] = useState<SalesRole>("general");
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [linkCopied, setLinkCopied] = useState(false);
  const [crmOwnerMatch, setCrmOwnerMatch] = useState<boolean | null>(null);
  const [confirm, setConfirm] = useState<
    { kind: "remove"; id: string; name: string } | { kind: "revoke"; id: string; email: string } | null
  >(null);

  const canManage = user?.company?.role === "owner" || user?.company?.role === "admin";
  const salesRolesEnabled = Boolean(user?.company?.features?.includes("SALES_ROLES_ENABLED"));
  const roleNames: Record<SalesRole, string> = {
    sdr: p.teamMemberTypeSdr,
    ae: p.teamMemberTypeAe,
    general: p.teamMemberTypeGeneral,
  };

  const { data: company, isLoading: companyLoading } = useQuery({
    queryKey: companyKeys.detail(),
    queryFn: () => companyApi.get(),
  });
  const { data: roster, isLoading: rosterLoading, isError: rosterFailed, refetch: refetchRoster } = useQuery({
    queryKey: companyKeys.members(),
    queryFn: () => companyApi.listMembers(),
  });

  const salesRolesEnabled = roster?.salesRolesEnabled === true;
  const seatLimit = company?.seatLimit ?? user?.company?.seatLimit ?? 1;
  const seatsUsed = company?.seatsUsed ?? user?.company?.seatsUsed ?? 1;
  const seatsFull = (company?.seatsAvailable ?? Math.max(0, seatLimit - seatsUsed)) <= 0;

  const refreshWorkspace = () => {
    queryClient.invalidateQueries({ queryKey: companyKeys.all });
    queryClient.invalidateQueries({ queryKey: authKeys.me() });
  };

  const inviteMutation = useMutation({
    mutationFn: () =>
      companyApi.invite(
        inviteEmail.trim(),
        inviteRole,
        salesRolesEnabled ? inviteSalesRole : undefined,
      ),
    onSuccess: (res) => {
      setInviteEmail("");
      setInviteSalesRole("general");
      setInviteUrl(res.inviteUrl ?? null);
      refreshWorkspace();
      toast.success(res.emailSent ? copy.inviteSent : copy.inviteLinkReady);
    },
    onError: (error) => toast.error(apiErrorMessage(error, copy.inviteFailed)),
  });

  const salesRoleMutation = useMutation({
    mutationFn: ({ memberId, salesRole }: { memberId: string; salesRole: SalesRole }) =>
      companyApi.updateMemberSalesRole(memberId, salesRole),
    onSuccess: () => {
      refreshWorkspace();
    },
    onError: (error) => {
      toast.error(apiErrorMessage(error, "Could not update sales role"));
    },
  });

  const revokeMutation = useMutation({
    mutationFn: (id: string) => companyApi.revokeInvite(id),
    onSuccess: () => {
      refreshWorkspace();
      setConfirm(null);
      toast.success(copy.revoked);
    },
    onError: (error) => toast.error(apiErrorMessage(error, copy.revokeFailed)),
  });

  const resendMutation = useMutation({
    mutationFn: (id: string) => companyApi.resendInvite(id),
    onSuccess: () => {
      refreshWorkspace();
      toast.success(copy.resent);
    },
    onError: (error) => toast.error(apiErrorMessage(error, copy.resendFailed)),
  });

  const removeMutation = useMutation({
    mutationFn: (id: string) => companyApi.removeMember(id),
    onSuccess: () => {
      refreshWorkspace();
      setConfirm(null);
      toast.success(copy.removed);
    },
    onError: (error) => toast.error(apiErrorMessage(error, copy.removeFailed)),
  });

  const salesProfileMutation = useMutation({
    // "General" is stored as no commercial type.
    mutationFn: (vars: { memberId: string; salesRole: SalesRole }) =>
      companyApi.updateMemberSalesProfile(vars.memberId, {
        salesRole: vars.salesRole === "general" ? null : vars.salesRole,
      }),
    onSuccess: refreshWorkspace,
    onError: (error) => toast.error(apiErrorMessage(error, copy.updateFailed)),
  });

  const handleInvite = (event: React.FormEvent) => {
    event.preventDefault();
    const email = inviteEmail.trim();
    if (!email) return toast.error(copy.enterEmail);
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return toast.error(copy.invalidEmail);
    if (seatsFull) return;
    inviteMutation.mutate();
  };

  const copyInviteLink = async () => {
    if (!inviteUrl) return;
    try {
      await navigator.clipboard.writeText(inviteUrl);
      setLinkCopied(true);
      window.setTimeout(() => setLinkCopied(false), 1500);
    } catch {
      toast.error(copy.copyFailed);
    }
  };

  if (companyLoading || rosterLoading) {
    return (
      <div className={THEME_TOKENS.interaction.pageLoad}>
        <VocifyLoader size="lg" label={copy.loading} />
      </div>
    );
  }

  const dateFormat = new Intl.DateTimeFormat(language === "EN" ? "en-GB" : "es-ES", { day: "numeric", month: "short" });
  const members = roster?.members ?? [];
  const invites = roster?.pendingInvites ?? [];

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
        {!canManage && (
          <p className="text-xs text-muted-foreground mb-6 leading-relaxed">
            Your password and email are yours. Change the password from Profile. Memos and HubSpot recordings stay filtered to you unless an admin opens All.
          </p>
        )}
        <div className="divide-y divide-border/40">
          {(roster?.members ?? []).map((m) => {
            const currentSalesRole = m.salesRole ?? "general";
            return (
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
                  {salesRolesEnabled &&
                    (canManage ? (
                      <div
                        className="inline-flex rounded-full border border-border/40 bg-secondary/5 p-1"
                        role="group"
                        aria-label={catalog.salesRoleGroup}
                      >
                        {SALES_ROLE_OPTIONS.map((value) => {
                          const selected = currentSalesRole === value;
                          const pending =
                            salesRoleMutation.isPending &&
                            salesRoleMutation.variables?.memberId === m.id &&
                            salesRoleMutation.variables?.salesRole === value;
                          return (
                            <button
                              key={value}
                              type="button"
                              disabled={salesRoleMutation.isPending}
                              onClick={() => {
                                if (selected) return;
                                salesRoleMutation.mutate({ memberId: m.id, salesRole: value });
                              }}
                              aria-pressed={selected}
                              className={selected ? pillSelected : pillIdle}
                            >
                              {pending ? "…" : salesRoleLabel(value, catalog)}
                            </button>
                          );
                        })}
                      </div>
                    ) : (
                      <span className="rounded-full border border-border/40 bg-secondary/5 px-3 h-7 inline-flex items-center text-[11px] text-muted-foreground">
                        {salesRoleLabel(currentSalesRole, catalog)}
                      </span>
                    ))}
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
            );
          })}
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
                    {inv.role}
                    {salesRolesEnabled
                      ? ` · ${salesRoleLabel(inv.salesRole, catalog)}`
                      : ""}
                    {" · "}expires {new Date(inv.expiresAt).toLocaleDateString()}
                  </p>
                </div>
                {canManage && (
                  <div className="flex items-center gap-1 shrink-0">
                    <IconAction
                      label={copy.remove.replace("{name}", name)}
                      tone="danger"
                      onClick={() => setConfirm({ kind: "remove", id: member.id, name })}
                    >
                      <Trash2 className="h-4 w-4" />
                    </IconAction>
                  ) : null}
                </span>
              ) : null}
            </li>
          );
        })}
        {invites.map((invite) => (
          <li key={invite.id} className="flex items-center gap-3 py-3">
            <div className="flex min-w-0 flex-1 flex-col sm:flex-row sm:items-baseline sm:gap-3">
              <span className="truncate text-sm text-muted-foreground sm:w-48 sm:shrink-0">{invite.email}</span>
              <span className="truncate text-xs text-muted-foreground/80">
                {copy.pending.replace("{date}", dateFormat.format(new Date(invite.expiresAt)))}
              </span>
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
                        className={selected ? pillSelected : pillIdle}
                      >
                        {option.label}
                      </button>
                    );
                  })}
                </div>
                {salesRolesEnabled && (
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={THEME_TOKENS.typography.capsLabel}>
                      {catalog.salesRoleGroup}
                    </span>
                    <div
                      className="inline-flex rounded-full border border-border/40 bg-secondary/5 p-1"
                      role="group"
                      aria-label={catalog.salesRoleGroup}
                    >
                      {SALES_ROLE_OPTIONS.map((value) => {
                        const selected = inviteSalesRole === value;
                        return (
                          <button
                            key={value}
                            type="button"
                            onClick={() => setInviteSalesRole(value)}
                            aria-pressed={selected}
                            className={selected ? pillSelected : pillIdle}
                          >
                            {salesRoleLabel(value, catalog)}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
                <Button
                  type="submit"
                  disabled={inviteMutation.isPending || seatsFull}
                  className="rounded-full bg-beige text-cream px-6 h-10"
                >
                  <AnimIcon name="refresh" />
                </IconAction>
                <IconAction
                  label={copy.revoke}
                  tone="danger"
                  onClick={() => setConfirm({ kind: "revoke", id: invite.id, email: invite.email })}
                >
                  <Trash2 className="h-4 w-4" />
                </IconAction>
              </span>
            ) : null}
          </li>
        ))}
      </ul>

      <ConfirmAction
        open={confirm !== null}
        onOpenChange={(open) => !open && setConfirm(null)}
        title={confirm?.kind === "revoke" ? copy.revokeTitle : copy.removeTitle}
        description={
          confirm?.kind === "revoke"
            ? copy.revokeBody.replace("{email}", confirm.email)
            : confirm
              ? copy.removeBody.replace("{name}", confirm.name)
              : ""
        }
        confirmLabel={confirm?.kind === "revoke" ? copy.revokeConfirm : copy.removeConfirm}
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
