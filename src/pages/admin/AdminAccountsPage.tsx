import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { Search, LogIn } from "lucide-react";
import { adminApi, adminKeys } from "@/features/admin/api";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { loginAsAccount } from "@/lib/admin-impersonation";

const PAGE_SIZE = 20;

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

  const { data: runtime } = useQuery({
    queryKey: adminKeys.runtime(),
    queryFn: () => adminApi.runtime(),
  });

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
    <div className="space-y-8">
      <div>
        <h1 className={THEME_TOKENS.typography.pageTitle}>
          Accounts <span className={THEME_TOKENS.typography.accentTitle}>console</span>
        </h1>
        <p className={THEME_TOKENS.typography.body}>Cross-tenant account preview and Login as.</p>
      </div>

      {runtime && (
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-4 text-sm text-muted-foreground flex flex-wrap gap-x-6 gap-y-1`}>
          <span>STT: {runtime.sttProvider}</span>
          <span>LLM: {runtime.llmProvider}</span>
          <span>Extract: {runtime.extractionModel}</span>
          <span>Copilot: {runtime.copilotModel}</span>
          <span>Env: {runtime.environment}</span>
        </div>
      )}

      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-4 flex flex-wrap items-center justify-between gap-3`}>
        <p className="text-sm">
          Stuck memos: <span className="font-medium text-foreground">{stuckMemos.length}</span>
        </p>
        <Button
          size="sm"
          variant="outline"
          disabled={recoverMutation.isPending}
          onClick={() => recoverMutation.mutate()}
        >
          {recoverMutation.isPending ? "Recovering…" : "Recover stuck memos"}
        </Button>
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          className="pl-9"
          placeholder="Search email, name, company, id…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} overflow-hidden`}>
        {isLoading ? (
          <p className="p-8 text-center text-muted-foreground">Loading accounts…</p>
        ) : isError ? (
          <p className="p-8 text-center text-destructive">Failed to load accounts</p>
        ) : accounts.length === 0 ? (
          <p className="p-8 text-center text-muted-foreground">No accounts found</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="border-b border-border/60 bg-muted/30">
              <tr className="text-left text-muted-foreground">
                <th className="px-4 py-3 font-normal">Email</th>
                <th className="px-4 py-3 font-normal">Name</th>
                <th className="px-4 py-3 font-normal">CRM</th>
                <th className="px-4 py-3 font-normal">Memos</th>
                <th className="px-4 py-3 font-normal">Last memo</th>
                <th className="px-4 py-3 font-normal" />
              </tr>
            </thead>
            <tbody>
              {accounts.map((account) => (
                <tr key={account.id} className="border-b border-border/40 hover:bg-muted/20">
                  <td className="px-4 py-3">
                    <Link to={`/admin/accounts/${account.id}`} className="text-beige hover:underline">
                      {account.email || account.id.slice(0, 8)}
                    </Link>
                  </td>
                  <td className="px-4 py-3">{account.fullName || "—"}</td>
                  <td className="px-4 py-3">
                    {account.crm.length === 0
                      ? "—"
                      : account.crm.map((c) => `${c.provider} (${c.status})`).join(", ")}
                  </td>
                  <td className="px-4 py-3">{account.memoCount}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {account.lastMemoAt
                      ? formatDistanceToNow(new Date(account.lastMemoAt), { addSuffix: true })
                      : "—"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Button
                      size="sm"
                      variant="ghost"
                      className="gap-1.5"
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
            <Button size="sm" variant="outline" disabled={skip === 0} onClick={() => setSkip(Math.max(0, skip - PAGE_SIZE))}>
              Previous
            </Button>
            <Button
              size="sm"
              variant="outline"
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
