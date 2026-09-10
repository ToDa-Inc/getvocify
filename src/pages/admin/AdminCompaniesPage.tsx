import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { adminApi, adminKeys } from "@/features/admin/api";
import { LicenseCell } from "@/components/admin/LicenseCell";
import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const PAGE_SIZE = 20;
const th = `${THEME_TOKENS.typography.capsLabel} px-5 py-3 text-left`;
const td = "px-5 py-4 align-middle";

const AdminCompaniesPage = () => {
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

  const { data, isLoading } = useQuery({
    queryKey: adminKeys.companies(skip, debouncedSearch),
    queryFn: () => adminApi.listCompanies({ skip, limit: PAGE_SIZE, search: debouncedSearch || undefined }),
  });

  const companies = data?.companies ?? [];
  const total = data?.total ?? 0;
  const page = Math.floor(skip / PAGE_SIZE) + 1;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className={`space-y-8 ${THEME_TOKENS.motion.fadeIn}`}>
      <div className={V_PATTERNS.dashboardHeader}>
        <h1 className={THEME_TOKENS.typography.pageTitle}>
          Companies <span className={THEME_TOKENS.typography.accentTitle}>console</span>
        </h1>
        <p className={THEME_TOKENS.typography.body}>
          Change licenses in the row. Open a company for members, invites, and roles.
        </p>
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          className="pl-11 h-12 rounded-full bg-secondary/5 border-border/40"
          placeholder="Search companies…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} overflow-x-auto`}>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border/40">
              <th className={th}>Name</th>
              <th className={th}>Licenses</th>
              <th className={th}>Members</th>
              <th className={th}>Access</th>
              <th className={th}>CRM</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={5} className="px-5 py-8 text-muted-foreground">Loading…</td></tr>
            ) : companies.length === 0 ? (
              <tr><td colSpan={5} className="px-5 py-8 text-muted-foreground">No companies found.</td></tr>
            ) : (
              companies.map((c: Record<string, unknown>) => (
                <tr key={String(c.id)} className="border-b border-border/30 last:border-0 hover:bg-secondary/10">
                  <td className={td}>
                    <Link
                      to={`/admin/companies/${c.id}`}
                      className="text-foreground hover:text-beige transition-colors font-medium"
                    >
                      {String(c.name ?? "Untitled")}
                    </Link>
                  </td>
                  <td className={td}>
                    <LicenseCell
                      companyId={String(c.id)}
                      seatLimit={Number(c.seat_limit ?? 1)}
                      seatsUsed={Number(c.seats_used ?? 0)}
                    />
                  </td>
                  <td className={`${td} tabular-nums`}>{Number(c.member_count ?? 0)}</td>
                  <td className={`${td} capitalize text-muted-foreground`}>
                    {String(c.access_mode ?? "open")}
                    {c.billing_status && c.billing_status !== "none"
                      ? ` · ${String(c.billing_status)}`
                      : ""}
                  </td>
                  <td className={td}>
                    {Array.isArray(c.crm) && c.crm.length ? (
                      <div className="flex flex-wrap gap-1.5">
                        {(c.crm as Record<string, unknown>[]).map((x) => (
                          <span
                            key={String(x.provider)}
                            className="inline-flex items-center rounded-full border border-border/40 bg-secondary/5 px-2.5 h-6 text-[11px] capitalize text-muted-foreground"
                          >
                            {String(x.provider)}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center gap-3 text-sm">
          <Button
            size="sm"
            variant="outline"
            className="rounded-full"
            disabled={skip <= 0}
            onClick={() => setSkip(Math.max(0, skip - PAGE_SIZE))}
          >
            Previous
          </Button>
          <span className="text-muted-foreground">Page {page} of {totalPages}</span>
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
      )}
    </div>
  );
};

export default AdminCompaniesPage;
