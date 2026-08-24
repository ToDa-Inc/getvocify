import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { ArrowLeft, LogIn } from "lucide-react";
import { adminApi, adminKeys } from "@/features/admin/api";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { Button } from "@/components/ui/button";
import { loginAsAccount } from "@/lib/admin-impersonation";

const AdminAccountDetailPage = () => {
  const { userId = "" } = useParams();
  const { data: account, isLoading, isError } = useQuery({
    queryKey: adminKeys.account(userId),
    queryFn: () => adminApi.getAccount(userId),
    enabled: !!userId,
  });

  const handleLoginAs = () => {
    if (!account) return;
    void loginAsAccount({
      accountId: account.id,
      email: account.email,
      fullName: account.fullName,
      impersonate: async (id) => {
        const res = await adminApi.impersonate(id);
        return { accessToken: res.accessToken, refreshToken: res.refreshToken };
      },
    });
  };

  if (isLoading) {
    return <p className={THEME_TOKENS.typography.capsLabel}>Loading account…</p>;
  }
  if (isError || !account) {
    return <p className="text-destructive">Account not found</p>;
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link to="/admin" className="inline-flex items-center gap-1.5 text-sm text-beige hover:underline mb-3">
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to accounts
          </Link>
          <h1 className={THEME_TOKENS.typography.pageTitle}>
            {account.email || account.id}
          </h1>
          <p className={THEME_TOKENS.typography.body}>
            {account.fullName || "No name"} · {account.companyName || "No company"}
          </p>
        </div>
        <Button className="bg-beige text-cream hover:bg-beige-dark gap-1.5" onClick={handleLoginAs}>
          <LogIn className="h-4 w-4" />
          Login as
        </Button>
      </div>

      <section className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 space-y-3`}>
        <h2 className={THEME_TOKENS.typography.sectionTitle}>Profile</h2>
        <dl className="grid sm:grid-cols-2 gap-3 text-sm">
          <div><dt className="text-muted-foreground">Phone</dt><dd>{account.phone || "—"}</dd></div>
          <div><dt className="text-muted-foreground">Created</dt><dd>{account.createdAt ? formatDistanceToNow(new Date(account.createdAt), { addSuffix: true }) : "—"}</dd></div>
          <div><dt className="text-muted-foreground">Last sign-in</dt><dd>{account.lastSignInAt ? formatDistanceToNow(new Date(account.lastSignInAt), { addSuffix: true }) : "—"}</dd></div>
          <div><dt className="text-muted-foreground">STT languages</dt><dd>{account.sttLanguages.join(", ") || "—"}</dd></div>
          <div><dt className="text-muted-foreground">Glossary terms</dt><dd>{account.glossaryLength}</dd></div>
        </dl>
        {account.productContext && (
          <div>
            <p className="text-sm text-muted-foreground mb-1">Product context</p>
            <p className="text-sm whitespace-pre-wrap">{account.productContext}</p>
          </div>
        )}
      </section>

      <section className="space-y-4">
        <h2 className={THEME_TOKENS.typography.sectionTitle}>CRM configuration</h2>
        {account.connections.length === 0 ? (
          <p className="text-muted-foreground text-sm">No CRM connected</p>
        ) : (
          account.connections.map((conn) => (
            <div key={conn.id} className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 space-y-3`}>
              <div className="flex flex-wrap gap-3 text-sm">
                <span className="font-medium capitalize">{conn.provider}</span>
                <span className="text-muted-foreground">Status: {conn.status}</span>
                {conn.tokenExpiresAt && (
                  <span className="text-muted-foreground">
                    Token expires {formatDistanceToNow(new Date(conn.tokenExpiresAt), { addSuffix: true })}
                  </span>
                )}
              </div>
              {conn.configuration ? (
                <dl className="grid sm:grid-cols-2 gap-2 text-sm">
                  <div><dt className="text-muted-foreground">Pipeline</dt><dd>{conn.configuration.defaultPipelineName} → {conn.configuration.defaultStageName}</dd></div>
                  <div><dt className="text-muted-foreground">Deal fields</dt><dd>{conn.configuration.allowedDealFields.join(", ") || "—"}</dd></div>
                  <div><dt className="text-muted-foreground">Contact fields</dt><dd>{conn.configuration.allowedContactFields.join(", ") || "—"}</dd></div>
                  <div><dt className="text-muted-foreground">On hold status</dt><dd>{conn.configuration.onHoldLeadStatusValue || "—"}</dd></div>
                  <div><dt className="text-muted-foreground">Lost status</dt><dd>{conn.configuration.lostLeadStatusValue || "—"}</dd></div>
                </dl>
              ) : (
                <p className="text-sm text-muted-foreground">No configuration saved yet</p>
              )}
            </div>
          ))
        )}
      </section>

      <section className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 space-y-4`}>
        <h2 className={THEME_TOKENS.typography.sectionTitle}>Usage</h2>
        <div className="grid sm:grid-cols-4 gap-4 text-sm">
          <div><p className="text-muted-foreground">Total memos</p><p className="text-lg">{account.usage.totalMemos}</p></div>
          <div><p className="text-muted-foreground">Approved</p><p className="text-lg">{account.usage.approvedCount}</p></div>
          <div><p className="text-muted-foreground">Time saved</p><p className="text-lg">{account.usage.timeSavedHours}h</p></div>
          <div><p className="text-muted-foreground">Accuracy</p><p className="text-lg">{account.usage.accuracyPct != null ? `${account.usage.accuracyPct}%` : "—"}</p></div>
        </div>
      </section>

      <section className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} overflow-hidden`}>
        <h2 className={`${THEME_TOKENS.typography.sectionTitle} p-6 pb-0`}>Recent memos</h2>
        {account.recentMemos.length === 0 ? (
          <p className="p-6 text-muted-foreground text-sm">No memos</p>
        ) : (
          <table className="w-full text-sm mt-4">
            <thead className="border-t border-border/60 bg-muted/30">
              <tr className="text-left text-muted-foreground">
                <th className="px-4 py-3 font-normal">Company</th>
                <th className="px-4 py-3 font-normal">Status</th>
                <th className="px-4 py-3 font-normal">Source</th>
                <th className="px-4 py-3 font-normal">When</th>
              </tr>
            </thead>
            <tbody>
              {account.recentMemos.map((memo) => (
                <tr key={memo.id} className="border-t border-border/40">
                  <td className="px-4 py-3">{memo.company}</td>
                  <td className="px-4 py-3">{memo.status}</td>
                  <td className="px-4 py-3">{memo.source || "—"}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {memo.createdAt ? formatDistanceToNow(new Date(memo.createdAt), { addSuffix: true }) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
};

export default AdminAccountDetailPage;
