import { Button } from "@/components/ui/button";
import { useLanguage } from "@/lib/i18n";
import { productText } from "@/lib/product-catalog";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { contactRecordUrl, signalLabelKey, splitTodayItems, supportingKeys, type TodayItem } from "@/lib/today";

type Props = {
  items: TodayItem[];
  onDismiss: (item: TodayItem) => void;
  onUndo: (item: TodayItem) => void;
  provider?: string | null;
  portalId?: string | null;
  compact?: boolean;
};

function openHref(item: TodayItem, provider: string | null, portalId: string | null) {
  return item.open_url || contactRecordUrl(provider, portalId, item.contact_id ?? null);
}

function CallCard({
  item,
  provider,
  portalId,
  compact,
  onDismiss,
  onUndo,
}: {
  item: TodayItem;
  provider: string | null;
  portalId: string | null;
  compact?: boolean;
  onDismiss: (item: TodayItem) => void;
  onUndo: (item: TodayItem) => void;
}) {
  const { t } = useLanguage();
  const href = openHref(item, provider, portalId);
  const undoOpen = item.undo_deadline != null && Date.parse(item.undo_deadline) >= Date.now();
  const name = item.contact_name || t.product.today_unknown_contact;
  const label = productText(signalLabelKey(item.type), t.product);
  const extras = supportingKeys(item.supporting);

  return (
    <li className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.cards.hover} ${THEME_TOKENS.radius.card} ${compact ? "p-3" : "p-5"}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-[15px] text-foreground">{name}</p>
          {item.company_name ? <p className={`mt-0.5 truncate ${THEME_TOKENS.typography.capsLabel}`}>{item.company_name}</p> : null}
        </div>
        <span className={`shrink-0 ${THEME_TOKENS.typography.capsLabel}`}>{label}</span>
      </div>
      <p className={compact ? "mt-2 text-[13px] leading-snug text-foreground" : "mt-3 text-[15px] leading-relaxed text-foreground"}>{item.reason}</p>
      {item.detail ? <p className={`mt-1 ${THEME_TOKENS.typography.body}`}>“{item.detail}”</p> : null}
      {extras.length > 0 ? (
        <p className={`mt-2 ${THEME_TOKENS.typography.capsLabel}`}>{extras.map((key) => productText(key, t.product)).join(" · ")}</p>
      ) : null}
      <div className="mt-3 flex flex-wrap items-center gap-3">
        {href ? (
          <a className="text-sm text-beige" href={href} target="_blank" rel="noreferrer">
            {t.product.today_open}
          </a>
        ) : null}
        {item.id && item.status !== "dismissed" ? (
          <Button type="button" variant="outline" size="sm" onClick={() => void onDismiss(item)}>
            {t.product.dismiss}
          </Button>
        ) : null}
        {undoOpen ? (
          <Button type="button" variant="outline" size="sm" onClick={() => void onUndo(item)}>
            {t.product.undo}
          </Button>
        ) : null}
      </div>
    </li>
  );
}

function TaskRow({
  item,
  provider,
  portalId,
}: {
  item: TodayItem;
  provider: string | null;
  portalId: string | null;
}) {
  const { t } = useLanguage();
  const href = openHref(item, provider, portalId);
  const titledByName = Boolean(item.contact_name);

  return (
    <li className="flex items-center justify-between gap-3 px-4 py-3">
      <div className="min-w-0">
        <p className="truncate text-[15px] text-foreground">{titledByName ? item.contact_name : item.reason}</p>
        {titledByName ? <p className={`truncate ${THEME_TOKENS.typography.body}`}>{item.reason}</p> : null}
        {item.company_name ? <p className={THEME_TOKENS.typography.capsLabel}>{item.company_name}</p> : null}
      </div>
      {href ? (
        <a className="shrink-0 text-sm text-beige" href={href} target="_blank" rel="noreferrer">
          {t.product.today_open}
        </a>
      ) : null}
    </li>
  );
}

export function TodayItemList({ items, onDismiss, onUndo, provider = null, portalId = null, compact }: Props) {
  const { t } = useLanguage();
  const { calls, tasks } = splitTodayItems(items);
  if (calls.length === 0 && tasks.length === 0) return null;

  return (
    <div className={compact ? "space-y-3" : "space-y-6"}>
      {calls.length > 0 ? (
        <div className="space-y-2">
          <h3 className={THEME_TOKENS.typography.capsLabel}>{t.product.today_calls}</h3>
          <ul className="space-y-2">
            {calls.map((item) => (
              <CallCard
                key={item.id ?? item.dedupe_key ?? item.reason}
                item={item}
                provider={provider}
                portalId={portalId}
                compact={compact}
                onDismiss={onDismiss}
                onUndo={onUndo}
              />
            ))}
          </ul>
        </div>
      ) : null}
      {tasks.length > 0 ? (
        <div className="space-y-2">
          <h3 className={THEME_TOKENS.typography.capsLabel}>{t.product.today_tasks}</h3>
          <ul className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} divide-y divide-border/60`}>
            {tasks.map((item) => (
              <TaskRow
                key={item.remote_id ?? item.reason}
                item={item}
                provider={provider}
                portalId={portalId}
              />
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
