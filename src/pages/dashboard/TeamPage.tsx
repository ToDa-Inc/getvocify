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
import { commercialRoleLabel } from "@/lib/role-labels";
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
  const { t, language } = useLanguage();
  const p = t.product;
  const copy = p.team;
  const queryClient = useQueryClient();
  const [inviteEmail, setInviteEmail] = useState("");
  // An invite from here is always a rep; SDR is the default commercial type.
  const [inviteSalesRole, setInviteSalesRole] = useState<SalesRole>("sdr");
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

  const seatLimit = company?.seatLimit ?? user?.company?.seatLimit ?? 1;
  const seatsUsed = company?.seatsUsed ?? user?.company?.seatsUsed ?? 1;
  const seatsFull = (company?.seatsAvailable ?? Math.max(0, seatLimit - seatsUsed)) <= 0;

  const refreshWorkspace = () => {
    queryClient.invalidateQueries({ queryKey: companyKeys.all });
    queryClient.invalidateQueries({ queryKey: authKeys.me() });
  };

  const inviteMutation = useMutation({
    mutationFn: () => companyApi.invite(inviteEmail.trim(), "member", salesRolesEnabled ? inviteSalesRole : undefined),
    onSuccess: (res) => {
      setInviteEmail("");
      setInviteSalesRole("sdr");
      setInviteUrl(res.emailSent ? null : (res.inviteUrl ?? null));
      setCrmOwnerMatch(res.crmOwnerMatch);
      refreshWorkspace();
      toast.success(res.emailSent ? copy.inviteSent : copy.inviteLinkReady);
    },
    onError: (error) => toast.error(apiErrorMessage(error, copy.inviteFailed)),
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
    <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-5 md:p-6`}>
      <div className="mb-4 flex items-baseline justify-between gap-4">
        <h2 className={THEME_TOKENS.typography.sectionTitle}>{copy.title}</h2>
        <p className={THEME_TOKENS.typography.capsLabel}>
          {copy.seats.replace("{used}", String(seatsUsed)).replace("{limit}", String(seatLimit))}
        </p>
      </div>

      {canManage ? (
        <form onSubmit={handleInvite} className="flex flex-wrap items-center gap-2 border-b border-border/40 pb-4">
          <label htmlFor="invite-email" className="sr-only">
            {copy.emailLabel}
          </label>
          <Input
            id="invite-email"
            type="email"
            autoComplete="email"
            placeholder={copy.emailPlaceholder}
            value={inviteEmail}
            disabled={seatsFull}
            onChange={(event) => setInviteEmail(event.target.value)}
            className="h-9 min-w-[12rem] flex-1 rounded-full px-4"
          />
          {salesRolesEnabled ? (
            <RoleChip value={inviteSalesRole} label={p.inviteSalesRoleLabel} options={roleNames} disabled={seatsFull} onChange={setInviteSalesRole} />
          ) : null}
          <Button type="submit" size="sm" className="rounded-full px-5" disabled={inviteMutation.isPending || seatsFull}>
            {inviteMutation.isPending ? (
              <>
                <VocifySpinner size={12} />
                <span className="ml-1.5">{copy.sending}</span>
              </>
            ) : (
              copy.invite
            )}
          </Button>
          <Tooltip>
            <TooltipTrigger asChild>
              <span tabIndex={0} aria-label={p.inviteEmailMatchHint} className="inline-flex text-muted-foreground">
                <Info className="h-4 w-4" aria-hidden />
              </span>
            </TooltipTrigger>
            <TooltipContent side="top" className="max-w-xs">
              {p.inviteEmailMatchHint}
            </TooltipContent>
          </Tooltip>
          {seatsFull ? (
            <p className="basis-full pt-1 text-xs text-muted-foreground">
              {copy.noSeats} ·{" "}
              <Link to="/dashboard/settings/billing" className="text-beige hover:underline">
                {copy.addSeats}
              </Link>
            </p>
          ) : null}
          {crmOwnerMatch === false ? (
            <p className="basis-full pt-1 text-xs text-warning">{p.inviteCrmMatchWarning}</p>
          ) : null}
          {inviteUrl ? (
            <div className="flex basis-full flex-wrap items-center gap-2 pt-1 text-xs text-muted-foreground">
              <span>{copy.linkFallback}</span>
              <span className="min-w-0 truncate text-foreground">{inviteUrl}</span>
              <Button type="button" variant="ghost" size="sm" className="h-7 rounded-full" onClick={() => void copyInviteLink()}>
                <AnimIcon name="copy" size={14} state={linkCopied && "done"} />
                {linkCopied ? copy.copied : copy.copyLink}
              </Button>
            </div>
          ) : null}
        </form>
      ) : null}

      {rosterFailed ? (
        <div role="alert" className="flex items-center justify-between gap-3 py-4">
          <p className={THEME_TOKENS.typography.body}>{copy.loadFailed}</p>
          <Button variant="outline" size="sm" onClick={() => void refetchRoster()}>
            {copy.retry}
          </Button>
        </div>
      ) : null}
      {/* A long team scrolls inside the card, not the page. */}
      <ul className="app-scroll max-h-[60vh] divide-y divide-border/40 overflow-y-auto">
        {members.map((member) => {
          const name = member.fullName || member.email;
          const editable = salesRolesEnabled && canManage && member.role === "member";
          return (
            <li key={member.id} className="flex items-center gap-3 py-3">
              <div className="flex min-w-0 flex-1 flex-col sm:flex-row sm:items-baseline sm:gap-3">
                <span className="truncate text-sm text-foreground sm:w-48 sm:shrink-0">{name}</span>
                <span className="truncate text-xs text-muted-foreground">{member.email}</span>
              </div>
              {editable ? (
                <RoleChip
                  value={member.salesRole ?? "general"}
                  label={copy.changeType}
                  options={roleNames}
                  disabled={salesProfileMutation.isPending && salesProfileMutation.variables?.memberId === member.id}
                  onChange={(salesRole) => salesProfileMutation.mutate({ memberId: member.id, salesRole })}
                />
              ) : (
                <span className={cn(CHIP, "bg-secondary/60 text-muted-foreground")}>{commercialRoleLabel(member.role, p)}</span>
              )}
              {canManage ? (
                <span className="inline-flex w-8 justify-center">
                  {member.userId !== user?.id && member.role !== "owner" ? (
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
            {salesRolesEnabled && invite.salesRole ? (
              <span className={cn(CHIP, "bg-secondary/60 text-muted-foreground")}>{roleNames[invite.salesRole]}</span>
            ) : null}
            {canManage ? (
              <span className="inline-flex items-center">
                <IconAction
                  label={copy.resend}
                  pendingLabel={copy.sending}
                  pending={resendMutation.isPending && resendMutation.variables === invite.id}
                  pendingIcon={<AnimIcon name="refresh" state="busy" />}
                  onClick={() => resendMutation.mutate(invite.id)}
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
