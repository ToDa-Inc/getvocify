import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { LogIn, Search } from "lucide-react";
import { adminApi, adminKeys } from "@/features/admin/api";
import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { loginAsAccount } from "@/lib/admin-impersonation";
import { LicenseCell } from "@/components/admin/LicenseCell";

const PAGE_SIZE = 20;
const th = `${THEME_TOKENS.typography.capsLabel} px-5 py-3 text-left`;
const td = "px-5 py-4 align-middle";

const AdminAccountsPage = () => {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [skip, setSkip] = useState(0);

  useEffect(() => {
    const id = setTimeout(() => {
      setDebouncedSearch(search.trim());
      setSkip(0);
    }, 300);
    return () => clearTimeout(id);
  }, [search]);

  const { data, isLoading, isError } = useQuery({
    queryKey: adminKeys.accounts(skip, debouncedSearch),
    queryFn: () => adminApi.listAccounts({ skip, limit: PAGE_SIZE, search: debouncedSearch || undefined }),
  });

  const { data: stuckMemos = [] } = useQuery({
    queryKey: adminKeys.stuckMemos(),
    queryFn: () => adminApi.stuckMemos(),
  });

  const recoverMutation = useMutation({
    mutationFn: () => adminApi.recoverStuckMemos(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminKeys.stuckMemos() });
    },
  });

  const handleLoginAs = (account: {
    id: string;
    email: string;
    fullName: string | null;
  }) => {
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

  const total = data?.total ?? 0;
  const accounts = data?.accounts ?? [];
  const page = Math.floor(skip / PAGE_SIZE) + 1;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className={`space-y-8 ${THEME_TOKENS.motion.fadeIn}`}>
      <div className={V_PATTERNS.dashboardHeader}>
        <h1 className={THEME_TOKENS.typography.pageTitle}>
          Accounts <span className={THEME_TOKENS.typography.accentTitle}>console</span>
        </h1>
        <p className={THEME_TOKENS.typography.body}>
          Change licenses in the row. Open an account or workspace for the rest.
        </p>
      </div>

      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="relative max-w-md w-full">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-11 h-12 rounded-full bg-secondary/5 border-border/40"
            placeholder="Search email, name, company, id…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="flex items-center gap-3">
          <p className={THEME_TOKENS.typography.capsLabel}>
            Stuck memos <span className="text-foreground">{stuckMemos.length}</span>
          </p>
          <Button
            size="sm"
            variant="outline"
            className="rounded-full"
            disabled={recoverMutation.isPending}
            onClick={() => recoverMutation.mutate()}
          >
            {recoverMutation.isPending ? "Recovering…" : "Recover stuck memos"}
          </Button>
        </div>
      </div>

      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} overflow-x-auto`}>
        {isLoading ? (
          <p className="p-8 text-center text-muted-foreground">Loading accounts…</p>
        ) : isError ? (
          <p className="p-8 text-center text-destructive">Failed to load accounts</p>
        ) : accounts.length === 0 ? (
          <p className="p-8 text-center text-muted-foreground">No accounts found</p>
        ) : (
          <table className="w-full min-w-[920px] text-sm">
            <thead>
              <tr className="border-b border-border/40">
                <th className={th}>Email</th>
                <th className={th}>Name</th>
                <th className={th}>Workspace</th>
                <th className={th}>Licenses</th>
                <th className={th}>CRM</th>
                <th className={th}>Memos</th>
                <th className={th}>Last memo</th>
                <th className={th} />
              </tr>
            </thead>
            <tbody>
              {accounts.map((account) => (
                <tr key={account.id} className="border-b border-border/30 last:border-0 hover:bg-secondary/10">
                  <td className={`${td} max-w-[220px]`}>
                    <Link
                      to={`/admin/accounts/${account.id}`}
                      className="text-foreground hover:text-beige transition-colors truncate block"
                    >
                      {account.email || account.id.slice(0, 8)}
                    </Link>
                  </td>
                  <td className={`${td} text-muted-foreground`}>{account.fullName || "—"}</td>
                  <td className={td}>
                    {account.companyId ? (
                      <Link
                        to={`/admin/companies/${account.companyId}`}
                        className="text-beige hover:underline"
                      >
                        {account.workspaceName || account.companyName || "Workspace"}
                      </Link>
                    ) : (
                      <span className="text-muted-foreground">{account.companyName || "—"}</span>
                    )}
                  </td>
                  <td className={td}>
                    {account.companyId && account.seatLimit != null ? (
                      <LicenseCell
                        companyId={account.companyId}
                        seatLimit={account.seatLimit}
                        seatsUsed={account.seatsUsed ?? 0}
                      />
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className={td}>
                    {account.crm.length === 0 ? (
                      <span className="text-muted-foreground">—</span>
                    ) : (
                      <div className="flex flex-wrap gap-1.5">
                        {account.crm.map((c) => (
                          <span
                            key={`${account.id}-${c.provider}`}
                            className="inline-flex items-center rounded-full border border-border/40 bg-secondary/5 px-2.5 h-6 text-[11px] capitalize text-muted-foreground"
                          >
                            {c.provider}
                          </span>
                        ))}
                      </div>
                    )}
                  </td>
                  <td className={`${td} tabular-nums`}>{account.memoCount}</td>
                  <td className={`${td} text-muted-foreground whitespace-nowrap`}>
                    {account.lastMemoAt
                      ? formatDistanceToNow(new Date(account.lastMemoAt), { addSuffix: true })
                      : "—"}
                  </td>
                  <td className={`${td} text-right`}>
                    <Button
                      size="sm"
                      variant="outline"
                      className="rounded-full h-8 px-3 gap-1.5"
                      onClick={() => handleLoginAs(account)}
                    >
                      <LogIn className="h-3.5 w-3.5" />
                      Login as
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">
            Page {page} of {totalPages} ({total} accounts)
          </span>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" className="rounded-full" disabled={skip === 0} onClick={() => setSkip(Math.max(0, skip - PAGE_SIZE))}>
              Previous
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="rounded-full"
              disabled={skip + PAGE_SIZE >= total}
              onClick={() => setSkip(skip + PAGE_SIZE)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminAccountsPage;
