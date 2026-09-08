import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LogIn } from "lucide-react";
import { adminApi, adminKeys } from "@/features/admin/api";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { loginAsAccount } from "@/lib/admin-impersonation";

const AdminCompanyDetailPage = () => {
  const { companyId = "" } = useParams();
  const queryClient = useQueryClient();
  const [seatLimit, setSeatLimit] = useState<number | "">("");

  const { data, isLoading } = useQuery({
    queryKey: adminKeys.company(companyId),
    queryFn: () => adminApi.getCompany(companyId),
    enabled: !!companyId,
  });

  const updateMutation = useMutation({
    mutationFn: (body: { seat_limit?: number }) => adminApi.updateCompany(companyId, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: adminKeys.company(companyId) }),
  });

  if (isLoading || !data) {
    return <p className={THEME_TOKENS.typography.body}>Loading company…</p>;
  }

  const company = (data.company as Record<string, unknown>) ?? {};
  const members = (data.members as Record<string, unknown>[]) ?? [];
  const invites = (data.pending_invites as Record<string, unknown>[]) ?? [];

  const currentLimit = Number(company.seat_limit ?? 1);
  const displayLimit = seatLimit === "" ? currentLimit : seatLimit;

  return (
    <div className="space-y-8">
      <div>
        <Link to="/admin/companies" className="text-sm text-beige hover:underline">← Companies</Link>
        <h1 className={`${THEME_TOKENS.typography.pageTitle} mt-2`}>
          {String(company.name ?? "Workspace")}
        </h1>
        <p className={THEME_TOKENS.typography.body}>
          {Number(company.seats_used ?? 0)} of {currentLimit} seats used
        </p>
      </div>

      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 space-y-4 max-w-md`}>
        <h2 className={THEME_TOKENS.typography.sectionTitle}>Seat limit</h2>
        <div className="flex gap-3 items-center">
          <Input
            type="number"
            min={1}
            value={displayLimit}
            onChange={(e) => setSeatLimit(Number(e.target.value))}
          />
          <Button
            size="sm"
            disabled={updateMutation.isPending || displayLimit < 1}
            onClick={() => updateMutation.mutate({ seat_limit: Number(displayLimit) })}
          >
            Save
          </Button>
        </div>
      </div>

      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6`}>
        <h2 className={`${THEME_TOKENS.typography.sectionTitle} mb-4`}>Members</h2>
        <div className="space-y-3">
          {members.map((m) => (
            <div key={String(m.id)} className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-medium">{String(m.full_name || m.email)}</p>
                <p className="text-xs text-muted-foreground">{String(m.email)} · {String(m.role)}</p>
              </div>
              <Button
                size="sm"
                variant="outline"
                className="gap-1.5"
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
            </div>
          ))}
        </div>
      </div>

      {invites.length > 0 && (
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6`}>
          <h2 className={`${THEME_TOKENS.typography.sectionTitle} mb-4`}>Pending invites</h2>
          <ul className="text-sm space-y-2">
            {invites.map((i) => (
              <li key={String(i.id)}>{String(i.email)} · {String(i.role)}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export default AdminCompanyDetailPage;
