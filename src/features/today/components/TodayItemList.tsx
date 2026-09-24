import { Button } from "@/components/ui/button";
import { useLanguage } from "@/lib/i18n";
import { productText } from "@/lib/product-catalog";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { contactRecordUrl, originKey, supportingKeys, type TodayItem } from "@/lib/today";

type Props = {
  items: TodayItem[];
  onDismiss: (item: TodayItem) => void;
  onUndo: (item: TodayItem) => void;
  provider?: string | null;
  portalId?: string | null;
  compact?: boolean;
};

export function TodayItemList({ items, onDismiss, onUndo, provider = null, portalId = null, compact }: Props) {
  const { t } = useLanguage();
  if (items.length === 0) return null;

  return (
    <ul className={compact ? "space-y-2" : "space-y-3"}>
      {items.map((item) => {
        const undoOpen = item.undo_deadline != null && Date.parse(item.undo_deadline) >= Date.now();
        const details = supportingKeys(item.supporting);
        return (
          <li
            key={item.id ?? item.dedupe_key ?? item.remote_id ?? item.reason}
            className={compact
              ? `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-3 text-sm`
              : `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-5`}
          >
            <p className={THEME_TOKENS.typography.capsLabel}>{productText(originKey(item.origins), t.product)}</p>
            <p className={compact ? "mt-1 text-[13px] leading-snug text-foreground" : "mt-1 text-[15px] leading-relaxed text-foreground"}>{item.reason}</p>
            {item.open_url || contactRecordUrl(provider, portalId, item.contact_id ?? null) ? (
              <a
                className="mt-2 inline-block text-sm text-beige"
                href={item.open_url || contactRecordUrl(provider, portalId, item.contact_id ?? null) || undefined}
                target="_blank"
                rel="noreferrer"
              >
                {t.product.today_open}
              </a>
            ) : null}
            {details.length > 0 ? (
              <details className="mt-2">
                <summary className={THEME_TOKENS.typography.capsLabel}>{t.product.today_details}</summary>
                <ul className="mt-1 space-y-1">
                  {details.map((key) => (
                    <li key={key} className={THEME_TOKENS.typography.body}>{productText(key, t.product)}</li>
                  ))}
                </ul>
              </details>
            ) : null}
            <div className="mt-3 flex flex-wrap gap-2">
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
      })}
    </ul>
  );
}
