import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ContactBrief } from "@/components/dashboard/memos/ContactBrief";
import { Phone } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { itemKey, meetingEntry } from "@shared/ui/home.js";
import { meetingCardLine } from "@/lib/contact-panel";
import { IconAction } from "@/components/ui/icon-action";
import { api } from "@/shared/lib/api-client";
import { useOptionalDialerFocus } from "@/features/calling/DialerFocusProvider";
import { useLanguage } from "@/lib/i18n";
import { productText } from "@/lib/product-catalog";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import {
  canShowTodayCall,
  dealMeetingLine,
  signalLabelKey,
  todayConversationItems,
  todayItemHref,
  supportingKeys,
  type TodayItem,
} from "@/lib/today";
import { useLeaving, useSettleRow } from "../hooks/useHomeMotion";
import { handoffsApi, todayKeys } from "../api";
import { HandoffHistory } from "./HandoffHistory";
import { TodayCardActions } from "./TodayCardActions";
import { cardSelected, textAction, undoOpen } from "./home/shared";

/** Rep home only (flag on): cards select instead of carrying fixed buttons. */
export type HomeCards = {
  selectedKey: string | null;
  onSelect: (item: TodayItem) => void;
  canDial: boolean;
  now: number;
  locked?: boolean;
  inCallKey?: string | null;
  inCallElapsed?: string | null;
  rowNotes?: Record<string, string>;
  /** T5 (HOY_LEAD_TIERS_ENABLED): "Llamar ahora" shows for any contact, dialer or not. */
  leadTiersEnabled?: boolean;
};

type Props = {
  items: TodayItem[];
  onDismiss: (item: TodayItem) => void;
  onUndo: (item: TodayItem) => void;
  onConfirm?: (item: TodayItem) => void;
  onReview?: (memoId: string) => void;
  provider?: string | null;
  portalId?: string | null;
  compact?: boolean;
  home?: HomeCards;
  leadTiersEnabled?: boolean;
  /** T6: the company's connected CRM, used to read a deal card's meeting brief when the
   * item itself carries no connection_id (an "own" deal, never a handoff). */
  connectionId?: string | null;
};

/** T6: GET /briefs/meeting's shape - deterministic, no model call. */
type MeetingBrief = {
  company: { name: string | null; sector: string | null; size: string | null } | null;
  interactions: { date: string; author: string | null; text: string }[];
  open_items: {
    objections: { text: string }[];
    commitments: { text: string; due_at: string | null }[];
    missing_playbook_steps: string[];
  };
};

function meetingBriefRequest(contactId: string, connectionId: string | null): string {
  const params = new URLSearchParams({ contact_id: contactId, connection_id: connectionId || "" });
  return `/briefs/meeting?${params.toString()}`;
}

function DealBriefPanel({ contactId, connectionId }: { contactId: string; connectionId: string | null }) {
  const { t } = useLanguage();
  const query = useQuery({
    queryKey: ["meeting-brief", contactId, connectionId],
    queryFn: () => api.get<MeetingBrief>(meetingBriefRequest(contactId, connectionId)),
    staleTime: 30_000,
  });
  if (query.isLoading) return null;
  const brief = query.data;
  const hasAnything =
    Boolean(brief?.company) ||
    Boolean(brief?.interactions.length) ||
    Boolean(brief?.open_items.objections.length) ||
    Boolean(brief?.open_items.commitments.length) ||
    Boolean(brief?.open_items.missing_playbook_steps.length);
  if (!hasAnything) return <p className={THEME_TOKENS.typography.body}>{t.product.meeting_brief_empty}</p>;
  const company = brief?.company
    ? [brief.company.name, brief.company.sector, brief.company.size].filter(Boolean).join(" · ")
    : null;
  return (
    <div className="space-y-2">
      {company ? (
        <p className={THEME_TOKENS.typography.capsLabel}>{t.product.meeting_brief_company}: {company}</p>
      ) : null}
      {brief && brief.interactions.length > 0 ? (
        <div className="space-y-1">
          <p className={THEME_TOKENS.typography.capsLabel}>{t.product.meeting_brief_interactions}</p>
          {brief.interactions.map((line, index) => (
            <p key={index} className="text-[13px] leading-snug text-foreground">
              {line.author ? `${line.author}: ` : ""}{line.text}
            </p>
          ))}
        </div>
      ) : null}
      {brief && brief.open_items.objections.length > 0 ? (
        <p className="text-[13px] text-foreground">
          {t.product.meeting_brief_open_objections}: {brief.open_items.objections.map((row) => row.text).join(" · ")}
        </p>
      ) : null}
      {brief && brief.open_items.commitments.length > 0 ? (
        <p className="text-[13px] text-foreground">
          {t.product.meeting_brief_pending_commitments}: {brief.open_items.commitments.map((row) => row.text).join(" · ")}
        </p>
      ) : null}
      {brief && brief.open_items.missing_playbook_steps.length > 0 ? (
        <p className="text-[13px] text-foreground">
          {t.product.meeting_brief_missing_steps}: {brief.open_items.missing_playbook_steps.join(" · ")}
        </p>
      ) : null}
    </div>
  );
}

function DealCard({
  item,
  compact,
  connectionId,
  provider,
  portalId,
  onCall,
}: {
  item: TodayItem;
  compact?: boolean;
  connectionId: string | null;
  provider: string | null;
  portalId: string | null;
  onCall: (item: TodayItem) => void;
}) {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const dialer = useOptionalDialerFocus();
  const [open, setOpen] = useState(false);
  const href = todayItemHref(item, provider, portalId);
  // The meeting the SDR booked, when the handoff carries it; otherwise the plain reason.
  const meetingLine = dealMeetingLine(item, {
    locale: t.product.hourLocale,
    template: t.product.deal_meeting_line,
    timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  });
  return (
    <li className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.cards.hover} ${THEME_TOKENS.radius.card} ${compact ? "p-3" : "p-5"}`}>
      <div className="flex items-start gap-3">
        <button
          type="button"
          className="min-w-0 flex-1 text-left"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          <CardBody item={{ ...item, detail: meetingLine ?? item.detail }} compact={compact} quoted={false} />
        </button>
        <TodayCardActions
          onCall={dialer && item.contact_id ? () => onCall(item) : undefined}
          crmHref={href}
        />
      </div>
      {open && item.contact_id ? (
        <div className="mt-3 space-y-4 border-t border-border/60 pt-3">
          <DealBriefPanel contactId={item.contact_id} connectionId={item.connection_id ?? connectionId} />
          {item.handoff_id ? (
            <>
              <HandoffHistory contactId={item.contact_id} onOpenMemo={(memoId) => navigate(`/dashboard/memos/${memoId}`)} />
              <HandoffEndActions handoffId={item.handoff_id} />
            </>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

/** A handed-off deal the CRM cannot tell us is over (no deal, or a stage we cannot read)
 * would stay here forever: the AE can close it, or give it back to the SDR. */
function HandoffEndActions({ handoffId }: { handoffId: string }) {
  const { t } = useLanguage();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const end = async (reason: "closed" | "cancelled") => {
    setBusy(true);
    setFailed(false);
    try {
      await handoffsApi.close(handoffId, reason);
      await queryClient.invalidateQueries({ queryKey: todayKeys.view() });
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex flex-wrap items-center gap-1 text-[13px] text-muted-foreground">
      <button type="button" className="px-1 py-1.5 hover:text-foreground" disabled={busy} onClick={() => void end("closed")}>
        {t.product.deal_close_action}
      </button>
      <span aria-hidden="true">·</span>
      <button type="button" className="px-1 py-1.5 hover:text-foreground" disabled={busy} onClick={() => void end("cancelled")}>
        {t.product.deal_return_action}
      </button>
      {failed ? <span role="alert" className="ml-2">{t.product.deal_action_failed}</span> : null}
    </div>
  );
}

function openDialer(
  dialer: ReturnType<typeof useOptionalDialerFocus>,
  item: TodayItem,
) {
  if (!dialer || !item.contact_id) return;
  dialer.openForContact({ contactId: item.contact_id, name: item.contact_name ?? null });
}

function CardBody({
  item,
  compact,
  quoted = true,
  inCall,
  inCallElapsed,
  note,
}: {
  item: TodayItem;
  compact?: boolean;
  quoted?: boolean;
  inCall?: boolean;
  inCallElapsed?: string | null;
  note?: string | null;
}) {
  const { t } = useLanguage();
  const name = item.contact_name || t.product.today_unknown_contact;
  const label = inCall
    ? `● ${t.product.panel_in_call}${inCallElapsed ? ` · ${inCallElapsed}` : ""}`
    : note ?? productText(signalLabelKey(item.type), t.product);
  const extras = supportingKeys(item.supporting);
  return (
    <div className="min-w-0 flex-1">
      <div className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-3">
        <p className="truncate text-[15px] text-foreground">{name}</p>
        <span className={`max-w-[9rem] truncate text-right ${THEME_TOKENS.typography.capsLabel} ${inCall ? "text-beige" : ""}`}>{label}</span>
        {item.company_name ? (
          <p className={`col-span-2 truncate ${THEME_TOKENS.typography.capsLabel}`}>{item.company_name}</p>
        ) : null}
      </div>
      <p className={compact ? "mt-2 text-[13px] leading-snug text-foreground" : "mt-3 text-[15px] leading-relaxed text-foreground"}>{item.reason}</p>
      {item.detail ? (
        <p className={`mt-1 ${THEME_TOKENS.typography.body}`}>{quoted ? `“${item.detail}”` : item.detail}</p>
      ) : null}
      {extras.length > 0 ? (
        <p className={`mt-2 ${THEME_TOKENS.typography.capsLabel}`}>{extras.map((key) => productText(key, t.product)).join(" · ")}</p>
      ) : null}
    </div>
  );
}

function MeetingCard({ item, compact }: { item: TodayItem; compact?: boolean }) {
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);
  const line = meetingCardLine(meetingEntry(item, { locale: t.product.hourLocale, now: Date.now() }), t.product);
  return (
    <li className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.cards.hover} ${THEME_TOKENS.radius.card} ${compact ? "p-3" : "p-5"}`}>
      <button type="button" className="w-full text-left" onClick={() => setOpen((value) => !value)}>
        <CardBody item={{ ...item, reason: line }} compact={compact} quoted={false} />
      </button>
      {open && item.contact_id ? (
        <div className="mt-3 border-t border-border/60 pt-3">
          <ContactBrief contactId={item.contact_id} compact meetingPrep />
        </div>
      ) : null}
    </li>
  );
}

function ConfirmCard({
  item,
  compact,
  onConfirm,
  onReview,
  onUndo,
}: {
  item: TodayItem;
  compact?: boolean;
  onConfirm?: (item: TodayItem) => void;
  onReview?: (memoId: string) => void;
  onUndo: (item: TodayItem) => void;
}) {
  const { t } = useLanguage();
  const undoOpen = item.undo_deadline != null && Date.parse(item.undo_deadline) >= Date.now();
  return (
    <li className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.cards.hover} ${THEME_TOKENS.radius.card} ${compact ? "p-3" : "p-5"}`}>
      <div className="flex items-start gap-3">
        <CardBody item={item} compact={compact} quoted={false} />
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          {item.status === "pending" && onConfirm ? (
            <>
              <Button type="button" variant="outline" size="sm" className="h-8 px-3.5 text-[13.5px]" onClick={() => void onConfirm(item)}>
                {t.product.confirmAction}
              </Button>
              {item.memo_id && onReview ? (
                <button type="button" className={textAction} onClick={() => onReview(String(item.memo_id))}>
                  {t.product.home_review}
                </button>
              ) : null}
            </>
          ) : null}
          {undoOpen ? (
            <button type="button" className={textAction} onClick={() => void onUndo(item)}>{t.product.undo}</button>
          ) : null}
        </div>
      </div>
    </li>
  );
}

function CallCard({
  item,
  provider,
  portalId,
  compact,
  onDismiss,
  onUndo,
  onCall,
  callLabel,
}: {
  item: TodayItem;
  provider: string | null;
  portalId: string | null;
  compact?: boolean;
  onDismiss: (item: TodayItem) => void;
  onUndo: (item: TodayItem) => void;
  onCall: (item: TodayItem) => void;
  callLabel?: string;
}) {
  const href = todayItemHref(item, provider, portalId);
  const undoOpen = item.undo_deadline != null && Date.parse(item.undo_deadline) >= Date.now();

  return (
    <li className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.cards.hover} ${THEME_TOKENS.radius.card} ${compact ? "p-3" : "p-5"}`}>
      <div className="flex items-start gap-3">
        <CardBody item={item} compact={compact} />
        <TodayCardActions
          onCall={item.contact_id ? () => onCall(item) : undefined}
          callLabel={callLabel}
          crmHref={href}
          onDismiss={item.id && item.status !== "dismissed" ? () => void onDismiss(item) : undefined}
          onUndo={undoOpen ? () => void onUndo(item) : undefined}
        />
      </div>
    </li>
  );
}

function HomeCallCard({
  item,
  home,
  leaving,
  onUndo,
  onCall,
  canCall,
}: {
  item: TodayItem;
  home: HomeCards;
  leaving: boolean;
  onUndo: (item: TodayItem) => void;
  onCall: (item: TodayItem) => void;
  canCall: boolean;
}) {
  const { t } = useLanguage();
  const ref = useRef<HTMLLIElement>(null);
  const settled = item.status != null && item.status !== "pending";
  const selected = !settled && home.selectedKey === itemKey(item);
  useSettleRow(ref, settled);

  useEffect(() => {
    if (selected) ref.current?.scrollIntoView?.({ block: "nearest" });
  }, [selected]);

  const fade = `transition-[border-color,box-shadow,opacity] duration-150 ${leaving ? "opacity-0" : "opacity-100"}`;
  const key = itemKey(item);
  const inCall = home.inCallKey === key;
  const note = home.rowNotes?.[key] ?? null;
  const blocked = home.locked && !inCall;

  return (
    <li
      ref={ref}
      data-home-row={settled ? undefined : ""}
      tabIndex={settled ? undefined : 0}
      aria-current={selected || undefined}
      aria-hidden={leaving || undefined}
      title={blocked ? t.product.panel_in_call : undefined}
      onClick={settled || blocked ? undefined : () => home.onSelect(item)}
      onFocus={
        settled
          ? undefined
          : (event) => {
              if (event.target === event.currentTarget) home.onSelect(item);
            }
      }
      className={`group relative outline-none ${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} ${fade} ${
        settled
          ? "flex items-center justify-between gap-3 px-[18px] py-2.5"
          : `cursor-pointer p-4 animate-in fade-in-0 ${selected ? cardSelected : "hover:border-beige/25 focus-visible:border-beige/25"}`
      }`}
    >
      {settled ? (
        <>
          <span className={THEME_TOKENS.typography.capsLabel}>
            {item.status === "snoozed" ? t.product.home_card_snoozed : t.product.home_card_dismissed}
          </span>
          {undoOpen(item, home.now) ? (
            <button type="button" className={textAction} onClick={() => onUndo(item)}>{t.product.undo}</button>
          ) : null}
        </>
      ) : (
        <>
          <CardBody item={item} inCall={inCall} inCallElapsed={home.inCallElapsed} note={note} />
          {canCall ? (
            <span
              className={`absolute bottom-2.5 right-3 transition-opacity duration-150 xl:opacity-0 xl:group-hover:opacity-100 xl:group-focus-within:opacity-100 ${
                selected ? "xl:hidden" : ""
              }`}
            >
              <IconAction label={home.leadTiersEnabled ? t.product.today_call_now : t.product.today_call} onClick={() => onCall(item)}>
                <Phone size={16} weight="light" />
              </IconAction>
            </span>
          ) : null}
        </>
      )}
    </li>
  );
}

const cardKey = (item: TodayItem) => item.id ?? item.dedupe_key ?? item.reason;

function HomeCardList({
  items,
  home,
  onUndo,
  onCall,
  provider,
  portalId,
}: {
  items: TodayItem[];
  home: HomeCards;
  onUndo: (item: TodayItem) => void;
  onCall: (item: TodayItem) => void;
  provider: string | null;
  portalId: string | null;
}) {
  const rows = useLeaving(items, cardKey);
  if (rows.length === 0) return null;
  return (
    <ul className="space-y-2">
      {rows.map(({ entry, leaving }) => (
        <HomeCallCard
          key={cardKey(entry)}
          item={entry}
          home={home}
          leaving={leaving}
          onUndo={onUndo}
          onCall={onCall}
          canCall={canShowCall(entry, home, provider, portalId)}
        />
      ))}
    </ul>
  );
}

function canShowCall(item: TodayItem, home: HomeCards, provider: string | null, portalId: string | null): boolean {
  return canShowTodayCall(item, { canDial: home.canDial, leadTiersEnabled: home.leadTiersEnabled }, provider, portalId);
}

export function TodayItemList({
  items,
  onDismiss,
  onUndo,
  onConfirm,
  onReview,
  provider = null,
  portalId = null,
  compact,
  home,
  leadTiersEnabled,
  connectionId = null,
}: Props) {
  const { t } = useLanguage();
  const dialer = useOptionalDialerFocus();
  const calls = todayConversationItems(items);
  const leadTiers = home ? Boolean(home.leadTiersEnabled) : Boolean(leadTiersEnabled);
  // T5: a dialer always dials. Without one, "Llamar ahora" (lead tiers on) falls back to
  // opening the CRM record instead of doing nothing.
  const call = (item: TodayItem) => {
    if (dialer) {
      openDialer(dialer, item);
      return;
    }
    if (!leadTiers) return;
    const href = todayItemHref(item, provider, portalId);
    if (href) {
      window.open(href, "_blank", "noopener,noreferrer");
      return;
    }
    if (item.phone) window.location.href = `tel:${item.phone}`;
  };

  if (home) return <HomeCardList items={calls} home={home} onUndo={onUndo} onCall={call} provider={provider} portalId={portalId} />;

  if (calls.length === 0) return null;

  return (
    <ul className={compact ? "space-y-2" : "space-y-3"}>
      {calls.map((item) =>
        item.type === "confirm_pending" ? (
          <ConfirmCard
            key={item.id ?? item.dedupe_key ?? item.reason}
            item={item}
            compact={compact}
            onConfirm={onConfirm}
            onReview={onReview}
            onUndo={onUndo}
          />
        ) : item.type === "meeting_today" ? (
          <MeetingCard
            key={item.id ?? item.dedupe_key ?? item.reason}
            item={item}
            compact={compact}
          />
        ) : item.type === "deal_in_progress" ? (
          <DealCard
            key={item.id ?? item.dedupe_key ?? item.deal_id ?? item.contact_id ?? item.reason}
            item={item}
            compact={compact}
            connectionId={connectionId}
            provider={provider}
            portalId={portalId}
            onCall={call}
          />
        ) : (
          <CallCard
            key={item.id ?? item.dedupe_key ?? item.reason}
            item={item}
            provider={provider}
            portalId={portalId}
            compact={compact}
            onDismiss={onDismiss}
            onUndo={onUndo}
            onCall={call}
            callLabel={leadTiers ? t.product.today_call_now : undefined}
          />
        ),
      )}
    </ul>
  );
}
