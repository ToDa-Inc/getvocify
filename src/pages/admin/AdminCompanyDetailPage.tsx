import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Copy, Loader2, LogIn, Minus, Plus } from "lucide-react";
import { toast } from "sonner";
import { adminApi, adminKeys } from "@/features/admin/api";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { loginAsAccount } from "@/lib/admin-impersonation";

const ROLE_OPTIONS = ["owner", "admin", "member"] as const;
const INVITE_ROLES = [
  { value: "member" as const, label: "Member" },
  { value: "admin" as const, label: "Admin" },
];

function apiErrorMessage(error: unknown, fallback: string) {
  if (error && typeof error === "object" && "data" in error) {
    const detail = (error as { data?: { detail?: unknown } }).data?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

const AdminCompanyDetailPage = () => {
  const { companyId = "" } = useParams();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [licenseCount, setLicenseCount] = useState(1);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"member" | "admin">("member");
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [accessMode, setAccessMode] = useState<"open" | "paywalled" | "unlocked">("open");

  const { data, isLoading, isError } = useQuery({
    queryKey: adminKeys.company(companyId),
    queryFn: () => adminApi.getCompany(companyId),
    enabled: !!companyId,
  });

  const company = (data?.company as Record<string, unknown>) ?? {};
  const members = (data?.members as Record<string, unknown>[]) ?? [];
  const invites = (data?.pending_invites as Record<string, unknown>[]) ?? [];
  const currentLimit = Number(company.seat_limit ?? 1);
  const seatsUsed = Number(company.seats_used ?? 0);
  const seatsPending = Number(company.seats_pending ?? 0);

  useEffect(() => {
    if (!data) return;
    const next = (data.company as Record<string, unknown>) ?? {};
    setName(String(next.name ?? ""));
    setLicenseCount(Number(next.seat_limit ?? 1));
    const mode = String(next.access_mode ?? "open");
    setAccessMode(mode === "paywalled" || mode === "unlocked" ? mode : "open");
  }, [data]);

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: adminKeys.company(companyId) });
    queryClient.invalidateQueries({ queryKey: adminKeys.all });
  };

  const saveMutation = useMutation({
    mutationFn: () =>
      adminApi.updateCompany(companyId, {
        name: name.trim(),
        seat_limit: licenseCount,
        access_mode: accessMode,
      }),
    onSuccess: () => {
      refresh();
      toast.success("Workspace updated");
    },
    onError: (error) => {
      toast.error(apiErrorMessage(error, "Could not update workspace"));
    },
  });

  const inviteMutation = useMutation({
    mutationFn: () => adminApi.inviteToCompany(companyId, inviteEmail.trim(), inviteRole),
    onSuccess: (res) => {
      setInviteEmail("");
      setInviteUrl((res.invite_url as string) ?? null);
      refresh();
      toast.success(res.email_sent ? "Invite sent" : "Invite created");
    },
    onError: (error) => {
      toast.error(apiErrorMessage(error, "Could not send invite"));
    },
  });

  const roleMutation = useMutation({
    mutationFn: ({ memberId, role }: { memberId: string; role: string }) =>
      adminApi.updateCompanyMember(companyId, memberId, role),
    onSuccess: () => {
      refresh();
      toast.success("Role updated");
    },
    onError: (error) => {
      toast.error(apiErrorMessage(error, "Could not change role"));
    },
  });

  const removeMutation = useMutation({
    mutationFn: (memberId: string) => adminApi.removeCompanyMember(companyId, memberId),
    onSuccess: () => {
      refresh();
      toast.success("Member removed");
    },
    onError: (error) => {
      toast.error(apiErrorMessage(error, "Could not remove member"));
    },
  });

  const revokeMutation = useMutation({
    mutationFn: (inviteId: string) => adminApi.revokeCompanyInvite(companyId, inviteId),
    onSuccess: () => {
      refresh();
      toast.success("Invite revoked");
    },
    onError: (error) => {
      toast.error(apiErrorMessage(error, "Could not revoke invite"));
    },
  });

  const copyInviteLink = async () => {
    if (!inviteUrl) return;
    try {
      await navigator.clipboard.writeText(inviteUrl);
      toast.success("Invite link copied");
    } catch {
      toast.error("Could not copy the link");
    }
  };

  if (isLoading) {
    return <p className={THEME_TOKENS.typography.body}>Loading company…</p>;
  }
  if (isError || !data) {
    return <p className="text-destructive">Company not found</p>;
  }

  const nameDirty = name.trim() !== String(company.name ?? "").trim();
  const licensesDirty = licenseCount !== currentLimit;
  const accessDirty = accessMode !== String(company.access_mode ?? "open");
  const canSave = name.trim().length > 0 && licenseCount >= 1 && (nameDirty || licensesDirty || accessDirty);

  return (
    <div className="space-y-8 max-w-3xl">
      <div>
        <Link to="/admin/companies" className="inline-flex items-center gap-1.5 text-sm text-beige hover:underline">
          <ArrowLeft className="h-3.5 w-3.5" />
          Companies
        </Link>
        <h1 className={`${THEME_TOKENS.typography.pageTitle} mt-2`}>
          {String(company.name ?? "Workspace")}
        </h1>
        <p className={THEME_TOKENS.typography.body}>
          {seatsUsed} of {currentLimit} licenses used
          {seatsPending > 0 ? ` · ${seatsPending} pending` : ""}
        </p>
      </div>

      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8 space-y-6`}>
        <div>
          <h2 className={THEME_TOKENS.typography.sectionTitle}>Workspace</h2>
          <p className="text-xs text-muted-foreground mt-1">
            Change the name, licenses, and whether this workspace must pay.
          </p>
        </div>

        <div className="space-y-2">
          <label htmlFor="company-name" className={THEME_TOKENS.typography.capsLabel}>
            Name
          </label>
          <Input
            id="company-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold"
          />
        </div>

        <div className="space-y-2">
          <p className={THEME_TOKENS.typography.capsLabel}>Access</p>
          <div className="inline-flex rounded-full border border-border/40 bg-secondary/5 p-1">
            {(
              [
                { value: "open" as const, label: "Open" },
                { value: "paywalled" as const, label: "Require payment" },
                { value: "unlocked" as const, label: "Unlocked" },
              ]
            ).map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => setAccessMode(option.value)}
                className={`rounded-full px-4 h-8 text-xs font-medium transition-colors ${
                  accessMode === option.value
                    ? "bg-beige text-cream"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            Open is the default. Require payment locks the product until they subscribe.
            Unlocked ignores Stripe and uses the license slider.
          </p>
        </div>

        <div className="space-y-2">
          <p className={THEME_TOKENS.typography.capsLabel}>Licenses</p>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              aria-label="Decrease licenses"
              className="h-10 w-10 rounded-full border border-border/40 bg-secondary/5 text-foreground hover:bg-secondary/10 disabled:opacity-40"
              disabled={licenseCount <= Math.max(1, seatsUsed)}
              onClick={() => setLicenseCount((n) => Math.max(1, n - 1))}
            >
              <Minus className="h-4 w-4 mx-auto" />
            </button>
            <Input
              type="number"
              min={1}
              value={licenseCount}
              onChange={(e) => setLicenseCount(Math.max(1, Number(e.target.value) || 1))}
              className="w-24 text-center bg-secondary/5 border-border/40 rounded-full h-12 font-bold"
            />
            <button
              type="button"
              aria-label="Increase licenses"
              className="h-10 w-10 rounded-full border border-border/40 bg-secondary/5 text-foreground hover:bg-secondary/10"
              onClick={() => setLicenseCount((n) => n + 1)}
            >
              <Plus className="h-4 w-4 mx-auto" />
            </button>
            <p className="text-xs text-muted-foreground">
              {seatsUsed} used · cannot go below occupancy
            </p>
          </div>
        </div>

        <div className="flex justify-end">
          <Button
            disabled={saveMutation.isPending || !canSave}
            onClick={() => saveMutation.mutate()}
            className="rounded-full bg-beige text-cream px-6 h-11"
          >
            {saveMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Saving…
              </>
            ) : (
              "Save changes"
            )}
          </Button>
        </div>
      </div>

      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8`}>
        <div className="mb-5">
          <h2 className={THEME_TOKENS.typography.sectionTitle}>Invite teammate</h2>
          <p className="text-xs text-muted-foreground mt-1">
            Sends an email if Resend is configured. Otherwise you get a shareable link.
          </p>
        </div>
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (!inviteEmail.trim()) {
              toast.error("Enter an email address");
              return;
            }
            inviteMutation.mutate();
          }}
        >
          <div className="space-y-2">
            <label htmlFor="admin-invite-email" className={THEME_TOKENS.typography.capsLabel}>
              Email
            </label>
            <Input
              id="admin-invite-email"
              type="email"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              placeholder="colleague@company.com"
              className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold"
            />
          </div>
          <div className="space-y-2">
            <p className={THEME_TOKENS.typography.capsLabel}>Role</p>
            <div className="flex flex-wrap items-center gap-3">
              <div className="inline-flex rounded-full border border-border/40 bg-secondary/5 p-1">
                {INVITE_ROLES.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => setInviteRole(option.value)}
                    className={`rounded-full px-4 h-8 text-xs font-medium transition-colors ${
                      inviteRole === option.value
                        ? "bg-beige text-cream"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
              <Button
                type="submit"
                disabled={inviteMutation.isPending}
                className="rounded-full bg-beige text-cream px-6 h-10"
              >
                {inviteMutation.isPending ? "Sending…" : "Send invite"}
              </Button>
            </div>
          </div>
        </form>
        {inviteUrl && (
          <div className="mt-5 rounded-2xl border border-border/70 bg-secondary/5 px-5 py-4 space-y-3">
            <p className="text-xs text-muted-foreground">Share this link if email did not send.</p>
            <p className="text-xs break-all">{inviteUrl}</p>
            <Button type="button" variant="outline" size="sm" className="rounded-full" onClick={() => void copyInviteLink()}>
              <Copy className="h-3.5 w-3.5" />
              Copy link
            </Button>
          </div>
        )}
      </div>

      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8`}>
        <h2 className={`${THEME_TOKENS.typography.sectionTitle} mb-6`}>Members</h2>
        <div className="divide-y divide-border/40">
          {members.map((m) => {
            const memberId = String(m.id);
            const role = String(m.role);
            return (
              <div key={memberId} className="py-4 first:pt-0 last:pb-0 space-y-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">{String(m.full_name || m.email)}</p>
                    <p className="text-xs text-muted-foreground truncate">{String(m.email)}</p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      className="gap-1.5 rounded-full"
                      onClick={() =>
                        void loginAsAccount({
                          accountId: String(m.user_id),
                          email: String(m.email),
                          fullName: (m.full_name as string) ?? null,
                          impersonate: async (id) => {
                            const res = await adminApi.impersonate(id);
                            return { accessToken: res.accessToken, refreshToken: res.refreshToken };
                          },
                        })
                      }
                    >
                      <LogIn className="h-3.5 w-3.5" />
                      Login as
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-destructive hover:text-destructive rounded-full"
                      disabled={removeMutation.isPending}
                      onClick={() => removeMutation.mutate(memberId)}
                    >
                      Remove
                    </Button>
                  </div>
                </div>
                <div className="inline-flex rounded-full border border-border/40 bg-secondary/5 p-1">
                  {ROLE_OPTIONS.map((option) => (
                    <button
                      key={option}
                      type="button"
                      disabled={roleMutation.isPending}
                      onClick={() => {
                        if (option !== role) roleMutation.mutate({ memberId, role: option });
                      }}
                      className={`rounded-full px-3 h-7 text-[11px] font-medium capitalize transition-colors ${
                        role === option
                          ? "bg-beige text-cream"
                          : "text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      {option}
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {invites.length > 0 && (
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8`}>
          <h2 className={`${THEME_TOKENS.typography.sectionTitle} mb-6`}>Pending invites</h2>
          <div className="divide-y divide-border/40">
            {invites.map((inv) => (
              <div key={String(inv.id)} className="py-3 first:pt-0 last:pb-0 flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm">{String(inv.email)}</p>
                  <p className="text-xs text-muted-foreground capitalize">
                    {String(inv.role)}
                    {inv.expires_at ? ` · expires ${new Date(String(inv.expires_at)).toLocaleDateString()}` : ""}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-destructive hover:text-destructive rounded-full"
                  disabled={revokeMutation.isPending}
                  onClick={() => revokeMutation.mutate(String(inv.id))}
                >
                  Revoke
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminCompanyDetailPage;
