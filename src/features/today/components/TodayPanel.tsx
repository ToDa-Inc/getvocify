import { Link } from "react-router-dom";
import { Phone } from "lucide-react";
import { afterActionError, composeHome } from "@shared/ui/home.js";
import { Button } from "@/components/ui/button";
import { IconAction } from "@/components/ui/icon-action";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { useAuth } from "@/features/auth";
import { useContactPriorities } from "@/features/today/hooks/useContactPriorities";
import { useHomeReads } from "@/features/today/hooks/useHomeReads";
import { forgetActed, useTodayCardActions } from "@/features/today/hooks/useTodayCardActions";
import { CRM_PROVIDER_CONFIGS, type CRMProvider } from "@/features/integrations/types";
import { useOptionalDialerFocus } from "@/features/calling/DialerFocusProvider";
import { useLanguage } from "@/lib/i18n";
import type { ProductTranslations } from "@/lib/product-catalog";
import { productText } from "@/lib/product-catalog";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import type { TodayItem } from "@/lib/today";

/** `undefined` while the first read is in flight, `null` once it failed without data. */
function settled<T>(query: { data: T | undefined; isError: boolean }): T | null | undefined {
  return query.data ?? (query.isError ? null : undefined);
}

/** A compact row for a today item in the panel. */
function PanelItemRow({
  item,
  copy,
  onCall,
  onConfirm,
}: {
  item: TodayItem;
  copy: ProductTranslations;
  onCall?: (item: TodayItem) => void;
  onConfirm?: (item: TodayItem) => void;
}) {
  const name = item.contact_name || copy.today_unknown_contact;
  const reason = item.reason || "";

  return (
    <li className={`flex items-center justify-between gap-3 rounded-lg px-3 py-2.5 ${THEME_TOKENS.interaction.rowHover}`}>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[14px] font-medium text-foreground">{name}</p>
        {reason && <p className={`mt-px truncate text-[13px] ${THEME_TOKENS.typography.capsLabel}`}>{reason}</p>}
        {item.company_name && <p className={`mt-px truncate text-[13px] ${THEME_TOKENS.typography.capsLabel}`}>{item.company_name}</p>}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {onCall ? (
          <IconAction label={copy.today_call} onClick={() => onCall(item)}>
            <Phone size={16} strokeWidth={1.5} />
          </IconAction>
        ) : null}
        {onConfirm ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 px-2.5 text-[12px]"
            onClick={() => onConfirm(item)}
          >
            {copy.confirmAction}
          </Button>
        ) : null}
      </div>
    </li>
  );
}

/** A section with a title and items, only shown if it has content. */
function PanelSection({
  title,
  count,
  items,
  copy,
  onCall,
  onConfirm,
  focus,
}: {
  title: string;
  count: number;
  items: TodayItem[];
  copy: ProductTranslations;
  onCall?: (item: TodayItem) => void;
  onConfirm?: (item: TodayItem) => void;
  focus: string;
}) {
  if (items.length === 0) return null;

  return (
    <div>
      <Link
        to={`/dashboard/today?focus=${focus}`}
        className={`flex items-center justify-between px-3 py-2 ${THEME_TOKENS.typography.capsLabel} transition-colors hover:text-foreground`}
      >
        <span>{title}</span>
        <span className="text-muted-foreground">{count}</span>
      </Link>
      <ul className="space-y-0.5 border-t border-border/60">
        {items.map((item, idx) => (
          <PanelItemRow key={item.id ?? item.dedupe_key ?? `${item.type}-${idx}`} item={item} copy={copy} onCall={onCall} onConfirm={onConfirm} />
        ))}
      </ul>
    </div>
  );
}

/**
 * The "Hoy" right-hand panel on Inicio: today's items organized by section with their main actions,
 * and a link to the full /dashboard/today page. Scrolls inside its container (a full-height flex column).
 */
export function TodayPanel() {
  const { t } = useLanguage();
  const copy = t.product;
  const { user } = useAuth();
  const dialer = useOptionalDialerFocus();

  const { query, acted, confirm, connected, provider } = useTodayCardActions({ fresh: true });
  const priorities = useContactPriorities({ fresh: true });
  const reads = useHomeReads();

  const view = composeHome({
    today: settled(query),
    todayStale: query.isError && Boolean(query.data),
    acted,
    priorities: settled(priorities),
    followups: settled(reads.followups),
    reviews: reads.reviews.isError ? null : reads.reviews.data,
    upcoming: settled(reads.upcoming),
    done: settled(reads.done),
    connected: connected ?? undefined,
    role: user?.company?.role ?? "member",
    crm: provider ? CRM_PROVIDER_CONFIGS[provider as CRMProvider]?.name ?? null : null,
    now: Date.now(),
    locale: copy.hourLocale,
    sdrSections: Boolean(user?.company?.features?.includes("HOY_SDR_SECTIONS_ENABLED")),
  });

  // Determine state
  const isLoading = query.isLoading;
  const isFailed = query.isError;
  const sections = view.sections;

  // Extract items from HomeView, handling the { source, item } wrapper
  const extractItems = (entries: { source: "today" | "priority"; item: TodayItem }[] | undefined): TodayItem[] => {
    if (!entries) return [];
    return entries.map(({ source, item }) =>
      source === "priority" ? { ...item, reason: productText(item.reason, copy) } : item,
    );
  };

  // Collect items by section
  const needsOkItems: TodayItem[] = [];
  const tasksItems: TodayItem[] = [];
  const followupsItems: TodayItem[] = [];
  const newItems: TodayItem[] = [];
  const callsItems: TodayItem[] = [];

  for (const section of sections) {
    if (section.id === "needs_ok" && "rows" in section) {
      // Extract items from needs_ok rows (which may be confirm/confirm_group/followup/review)
      for (const row of section.rows) {
        if (row.kind === "confirm" && "item" in row) {
          needsOkItems.push(row.item);
        } else if (row.kind === "confirm_group" && "items" in row) {
          needsOkItems.push(...row.items);
        }
      }
    } else if (section.id === "tasks" && "items" in section) {
      tasksItems.push(...extractItems(section.items));
    } else if (section.id === "followups" && "items" in section) {
      followupsItems.push(...extractItems(section.items));
    } else if (section.id === "new" && "items" in section) {
      newItems.push(...extractItems(section.items));
    } else if (section.id === "calls" && "items" in section) {
      callsItems.push(...extractItems(section.items));
    }
  }

  const { refetch } = query;
  // A confirm that fails after the item changed elsewhere is forgotten and the list reloads, as on Hoy.
  const onConfirm = (item: TodayItem) => {
    void (async () => {
      try {
        await confirm(item);
      } catch (error) {
        const outcome = afterActionError(error);
        if (!outcome) throw error;
        if (outcome.forget) forgetActed(outcome.forget);
        await refetch();
      }
    })();
  };

  const onCall = (item: TodayItem) => {
    if (!dialer || !item.contact_id) return;
    dialer.openForContact({ contactId: item.contact_id, name: item.contact_name ?? null });
  };

  // Loading state
  if (isLoading && !query.data) {
    return (
      <div className="flex items-center justify-center py-8">
        <VocifySpinner size={20} />
      </div>
    );
  }

  // Error state
  if (isFailed && !query.data) {
    return (
      <div className="space-y-3 p-4 text-center">
        <p className={THEME_TOKENS.typography.body}>{copy.today_prepare_failed}</p>
        <Button type="button" variant="outline" size="sm" onClick={() => void query.refetch()}>
          {copy.retry}
        </Button>
      </div>
    );
  }

  // Empty state (all sections have no items)
  const hasAny = needsOkItems.length > 0 || tasksItems.length > 0 || followupsItems.length > 0 || newItems.length > 0 || callsItems.length > 0;

  if (!hasAny) {
    return (
      <div className="space-y-4 p-4">
        <p className={`text-center ${THEME_TOKENS.typography.body}`}>{copy.today_focus_empty}</p>
        <div className="flex justify-center">
          <Button type="button" variant="outline" size="sm" asChild>
            <Link to="/dashboard/today">
              {copy.todayTitle}
            </Link>
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Scrollable content */}
      <div className="app-scroll min-w-0 flex-1 overflow-y-auto">
        <div className="space-y-4 p-4">
          {/* Falta tu OK */}
          <PanelSection
            title={copy.home_needs_ok}
            count={needsOkItems.length}
            items={needsOkItems}
            copy={copy}
            onConfirm={onConfirm}
            focus="needs_ok"
          />

          {/* Tareas */}
          <PanelSection
            title={copy.home_tasks}
            count={tasksItems.length}
            items={tasksItems}
            copy={copy}
            onCall={onCall}
            focus="tasks"
          />

          {/* Seguimientos */}
          <PanelSection
            title={copy.home_followups}
            count={followupsItems.length}
            items={followupsItems}
            copy={copy}
            onCall={onCall}
            focus="followups"
          />

          {/* Nuevos */}
          <PanelSection
            title={copy.home_new}
            count={newItems.length}
            items={newItems}
            copy={copy}
            onCall={onCall}
            focus="new"
          />

          {/* Llamadas */}
          <PanelSection
            title={copy.home_calls}
            count={callsItems.length}
            items={callsItems}
            copy={copy}
            onCall={onCall}
            focus="calls"
          />
        </div>
      </div>

      {/* Fixed footer with link to full Hoy page */}
      <div className="shrink-0 border-t border-border/60 bg-card p-3">
        <Button type="button" variant="quiet" size="text" className="w-full justify-center" asChild>
          <Link to="/dashboard/today">
            {copy.today_focus_see_all}
          </Link>
        </Button>
      </div>
    </div>
  );
}
