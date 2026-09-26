import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { Bell } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useLanguage } from "@/lib/i18n";
import { reportKeys, reportsApi } from "@/lib/api/reports";
import { bellActivityText, bellCount, reportTitleKey, type BellReportItem } from "@/lib/report-snapshot";

const POLL_MS = 60_000;

function periodLabel(iso: string, locale: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString(locale, { day: "numeric", month: "short" });
}

/** Polls only while the tab is visible; unmounts with the dashboard on logout, taking the interval with it. */
export function ReportBell() {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const query = useQuery({
    queryKey: reportKeys.notifications,
    queryFn: () => reportsApi.notifications(),
    refetchInterval: POLL_MS,
  });
  const count = bellCount(query.isSuccess ? query.data.unread : null);
  const items = query.data?.items ?? [];
  const activity = query.data?.activity ?? null;

  const openReport = (item: BellReportItem) => {
    setOpen(false);
    if (!item.read_at) {
      void reportsApi
        .markRead(item.id)
        .catch(() => undefined)
        .finally(() => queryClient.invalidateQueries({ queryKey: reportKeys.notifications }));
    }
    navigate(`/dashboard/reports/${item.report_id}`);
  };

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) void query.refetch();
      }}
    >
      <PopoverTrigger
        aria-label={count ? t.product.reportUnread.replace("{count}", String(count)) : t.product.reportsLabel}
        className="relative inline-flex h-9 w-9 items-center justify-center rounded-full text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
      >
        <Bell className="h-4 w-4" />
        {count ? (
          <span className="absolute -right-0.5 -top-0.5 min-w-4 rounded-full bg-beige px-1 text-center text-[10px] text-cream">
            {count}
          </span>
        ) : null}
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 max-h-[70vh] overflow-y-auto p-2">
        {items.length ? (
          <ul>
            {items.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => openReport(item)}
                  className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm hover:bg-secondary/60"
                >
                  <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${item.read_at ? "bg-transparent" : "bg-beige"}`} />
                  <span className={`flex-1 ${item.read_at ? "text-muted-foreground" : "text-foreground"}`}>
                    {t.product[reportTitleKey(item)]}
                  </span>
                  <span className="text-xs text-muted-foreground">{periodLabel(item.period_start, t.product.hourLocale)}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="px-2 py-2 text-sm text-muted-foreground">{t.product.bellEmpty}</p>
        )}
        {activity?.length ? (
          <div className="mt-1 border-t border-border/60 pt-2">
            <p className="px-2 pb-1 text-xs text-muted-foreground">{t.product.bellVocifyDid}</p>
            <ul>
              {activity.map((entry) => {
                const text = bellActivityText(entry, t.product);
                return (
                  <li key={`${entry.kind}:${entry.memo_id}:${entry.at}`}>
                    <Link
                      to={text.href}
                      onClick={() => setOpen(false)}
                      className="block rounded-md px-2 py-1.5 hover:bg-secondary/60"
                    >
                      <span className="block text-sm text-foreground">{text.title}</span>
                      <span className="block text-xs text-muted-foreground">{text.why}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}
