import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { adminApi, adminKeys } from "@/features/admin/api";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { Input } from "@/components/ui/input";

const PAGE_SIZE = 20;

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
    <div className="space-y-8">
      <div>
        <h1 className={THEME_TOKENS.typography.pageTitle}>
          Companies <span className={THEME_TOKENS.typography.accentTitle}>console</span>
        </h1>
        <p className={THEME_TOKENS.typography.body}>Manage workspaces, seat caps, and members.</p>
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input className="pl-9" placeholder="Search companies…" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>

      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} overflow-hidden`}>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-muted-foreground">
              <th className="p-4 font-medium">Name</th>
              <th className="p-4 font-medium">Seats</th>
              <th className="p-4 font-medium">Members</th>
              <th className="p-4 font-medium">CRM</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={4} className="p-6 text-muted-foreground">Loading…</td></tr>
            ) : companies.length === 0 ? (
              <tr><td colSpan={4} className="p-6 text-muted-foreground">No companies found.</td></tr>
            ) : (
              companies.map((c: Record<string, unknown>) => (
                <tr key={String(c.id)} className="border-b border-border/60 last:border-0">
                  <td className="p-4">
                    <Link to={`/admin/companies/${c.id}`} className="text-beige hover:underline font-medium">
                      {String(c.name ?? "Untitled")}
                    </Link>
                  </td>
                  <td className="p-4">{Number(c.seats_used ?? 0)} / {Number(c.seat_limit ?? 1)}</td>
                  <td className="p-4">{Number(c.member_count ?? 0)}</td>
                  <td className="p-4 text-xs text-muted-foreground">
                    {Array.isArray(c.crm) && c.crm.length
                      ? (c.crm as Record<string, unknown>[]).map((x) => x.provider).join(", ")
                      : "—"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center gap-3 text-sm">
          <button type="button" disabled={skip <= 0} onClick={() => setSkip(Math.max(0, skip - PAGE_SIZE))} className="text-beige disabled:opacity-40">Previous</button>
          <span className="text-muted-foreground">Page {page} of {totalPages}</span>
          <button type="button" disabled={skip + PAGE_SIZE >= total} onClick={() => setSkip(skip + PAGE_SIZE)} className="text-beige disabled:opacity-40">Next</button>
        </div>
      )}
    </div>
  );
};

export default AdminCompaniesPage;
