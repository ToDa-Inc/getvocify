import { useOptionalDialerFocus } from "@/features/calling/DialerFocusProvider";
import { useLanguage } from "@/lib/i18n";
import { productText } from "@/lib/product-catalog";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import {
  contactRecordUrl,
  signalLabelKey,
  todayConversationItems,
  supportingKeys,
  type TodayItem,
} from "@/lib/today";
import { TodayCardActions } from "./TodayCardActions";

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

function openDialer(
  dialer: ReturnType<typeof useOptionalDialerFocus>,
  item: TodayItem,
) {
  if (!dialer || !item.contact_id) return;
  dialer.openForContact({ contactId: item.contact_id, name: item.contact_name ?? null });
}

function CallCard({
  item,
  provider,
  portalId,
  compact,
  onDismiss,
  onUndo,
  onCall,
}: {
  item: TodayItem;
  provider: string | null;
  portalId: string | null;
  compact?: boolean;
  onDismiss: (item: TodayItem) => void;
  onUndo: (item: TodayItem) => void;
  onCall: (item: TodayItem) => void;
}) {
  const { t } = useLanguage();
  const href = openHref(item, provider, portalId);
  const undoOpen = item.undo_deadline != null && Date.parse(item.undo_deadline) >= Date.now();
  const name = item.contact_name || t.product.today_unknown_contact;
  const label = productText(signalLabelKey(item.type), t.product);
  const extras = supportingKeys(item.supporting);

  return (
    <li className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.cards.hover} ${THEME_TOKENS.radius.card} ${compact ? "p-3" : "p-5"}`}>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-3">
            <p className="truncate text-[15px] text-foreground">{name}</p>
            <span className={`max-w-[9rem] truncate text-right ${THEME_TOKENS.typography.capsLabel}`}>{label}</span>
            {item.company_name ? (
              <p className={`col-span-2 truncate ${THEME_TOKENS.typography.capsLabel}`}>{item.company_name}</p>
            ) : null}
          </div>
          <p className={compact ? "mt-2 text-[13px] leading-snug text-foreground" : "mt-3 text-[15px] leading-relaxed text-foreground"}>{item.reason}</p>
          {item.detail ? <p className={`mt-1 ${THEME_TOKENS.typography.body}`}>“{item.detail}”</p> : null}
          {extras.length > 0 ? (
            <p className={`mt-2 ${THEME_TOKENS.typography.capsLabel}`}>{extras.map((key) => productText(key, t.product)).join(" · ")}</p>
          ) : null}
        </div>
        <TodayCardActions
          onCall={item.contact_id ? () => onCall(item) : undefined}
          crmHref={href}
          onDismiss={item.id && item.status !== "dismissed" ? () => void onDismiss(item) : undefined}
          onUndo={undoOpen ? () => void onUndo(item) : undefined}
        />
      </div>
    </li>
  );
}

export function TodayItemList({
  items,
  onDismiss,
  onUndo,
  provider = null,
  portalId = null,
  compact,
}: Props) {
  const dialer = useOptionalDialerFocus();
  const calls = todayConversationItems(items);
  const call = (item: TodayItem) => openDialer(dialer, item);

  if (calls.length === 0) return null;

  return (
    <ul className={compact ? "space-y-2" : "space-y-3"}>
      {calls.map((item) => (
        <CallCard
          key={item.id ?? item.dedupe_key ?? item.reason}
          item={item}
          provider={provider}
          portalId={portalId}
          compact={compact}
          onDismiss={onDismiss}
          onUndo={onUndo}
          onCall={call}
        />
      ))}
    </ul>
  );
}
