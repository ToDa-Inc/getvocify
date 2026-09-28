import { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import * as SheetPrimitive from "@radix-ui/react-dialog";
import { ArrowSquareOut, X } from "@phosphor-icons/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BRIEF_LOADING, briefRequest, panelBrief, type BriefPayload } from "@shared/ui/brief.js";
import { snoozeUntil, type HomeRow } from "@shared/ui/home.js";
import { Button } from "@/components/ui/button";
import { IconAction } from "@/components/ui/icon-action";
import { Sheet, SheetPortal } from "@/components/ui/sheet";
import { FollowupCard } from "@/components/dashboard/FollowupCard";
import { BriefLines } from "@/components/dashboard/memos/ContactBrief";
import { useHomeColumn } from "@/components/dashboard/HomeColumn";
import { useAuth } from "@/features/auth";
import { companyApi } from "@/features/company/api";
import type { Memo } from "@/features/memos/types";
import { api, ApiError } from "@/shared/lib/api-client";
import { handoffsApi, todayKeys } from "../api";
import { HandoffHistory } from "./HandoffHistory";
import { afterCallLine, type CallSummary } from "@/lib/after-call";
import {
  conversationLine,
  firstName,
  historyRequest,
  initials,
  panelHeaderSubtitle,
  panelFilledPill,
  panelMeetingLine,
  showsHistory,
} from "@/lib/contact-panel";
import { useLanguage } from "@/lib/i18n";
import { productText, type ProductTranslations } from "@/lib/product-catalog";
import { plainSummary } from "@/lib/summary-line";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import type { FollowupRow, TodayItem } from "@/lib/today";
import type { usePanelPrimary } from "../hooks/usePanelPrimary";
import { panelRowKind } from "../hooks/usePanelPrimary";

type PanelState = ReturnType<typeof usePanelPrimary>;

/** The call as the panel sees it: in flight, just failed, or after hanging up (review). */
export type PanelCall = {
  onCall: boolean;
  inReview: boolean;
  failed: boolean;
  summary: CallSummary | undefined;
  memoId: string | null;
  crmName: string | null;
  nextRow: HomeRow | null;
  onNext: () => void;
};

type PanelActions = {
  onConfirm: (item: TodayItem) => void;
  onDismiss: (item: TodayItem) => void;
  onSnooze: (item: TodayItem, until: string) => void;
  onDisqualify?: (item: TodayItem) => void;
  onOpenMemo: (memoId: string) => void;
  provider: string | null;
  connectionId: string | null;
  followups: FollowupRow[] | null | undefined;
};

function panelName(row: HomeRow, copy: ProductTranslations) {
  return row.name || copy.today_unknown_contact;
}

function panelTitle(row: HomeRow, copy: ProductTranslations) {
  const name = panelName(row, copy);
  if (row.kind === "meeting") return name;
  if (row.kind === "confirm") return row.item.reason;
  if (row.kind === "followup") return copy.home_followup_row.replace("{name}", name);
  if (row.kind === "review") return copy.home_review_row.replace("{name}", name);
  return name;
}

function followupForContact(followups: FollowupRow[] | null | undefined, contactId: string | null) {
  if (!contactId || !followups) return null;
  return followups.find((row) => row.contact_id === contactId) ?? null;
}

function briefFailed(error: unknown): boolean {
  if (typeof error !== "object" || !error || !("status" in error)) return true;
  const status = Number((error as { status?: unknown }).status);
  return status === 401 || status >= 500;
}

/** T3/D2/D6: "Reunión agendada" on a call the SDR (or General) is working. A 409 needs_ae
 * opens an inline picker instead of failing - the transfer waits for that answer, it never
 * silently drops the contact from Hoy. */
function HandoffAction({
  contactId,
  connectionId,
  dealId,
  memoId,
}: {
  contactId: string;
  connectionId: string | null;
  dealId?: string | null;
  memoId?: string | null;
}) {
  const { t } = useLanguage();
  const copy = t.product;
  const queryClient = useQueryClient();
  const [state, setState] = useState<"idle" | "sending" | "done" | "needs_ae" | "error">("idle");
  const [aeId, setAeId] = useState<string>("");

  const aeQuery = useQuery({
    queryKey: ["handoff-ae-candidates"],
    queryFn: () => companyApi.listMembers(),
    enabled: state === "needs_ae",
    staleTime: 60_000,
  });

  const send = async (chosenAe?: string) => {
    setState("sending");
    try {
      await handoffsApi.create({
        contact_id: contactId,
        // Never send "": no connection means "let the server resolve the company's
        // connected CRM", same as F14's accept.py - an empty string would 404 instead.
        ...(connectionId ? { connection_id: connectionId } : {}),
        ...(dealId ? { deal_id: dealId } : {}),
        ...(memoId ? { memo_id: memoId } : {}),
        ae_user_id: chosenAe ?? null,
      });
      setState("done");
      void queryClient.invalidateQueries({ queryKey: todayKeys.view() });
    } catch (error) {
      const code = error instanceof ApiError
        ? (error.data as { detail?: { code?: string } } | null | undefined)?.detail?.code
        : null;
      setState(code === "needs_ae" ? "needs_ae" : "error");
    }
  };

  if (state === "done") return <p className="text-[13px] text-muted-foreground">{copy.panel_handoff_done}</p>;

  if (state === "needs_ae") {
    const candidates = (aeQuery.data?.members ?? []).filter(
      (member) => member.salesRole == null || member.salesRole === "ae" || member.salesRole === "general",
    );
    return (
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <select
          className="h-8 rounded-md border border-border bg-background px-2 text-[13px]"
          value={aeId}
          onChange={(event) => setAeId(event.target.value)}
        >
          <option value="">{copy.panel_handoff_pick_ae}</option>
          {candidates.map((member) => (
            <option key={member.userId} value={member.userId}>
              {member.fullName || member.email}
            </option>
          ))}
        </select>
        <Button type="button" variant="outline" size="sm" className="h-8 px-3 text-[13px]" disabled={!aeId} onClick={() => void send(aeId)}>
          {copy.panel_handoff_confirm}
        </Button>
      </div>
    );
  }

  return (
    <button
      type="button"
      className="px-1 py-1.5 text-[13px] text-muted-foreground hover:text-foreground disabled:opacity-60"
      disabled={state === "sending"}
      onClick={() => void send()}
    >
      {copy.panel_handoff_action}
    </button>
  );
}

function PanelBody({
  row,
  sheet,
  onClose,
  actions,
  panel,
  call,
}: {
  row: HomeRow;
  sheet: boolean;
  onClose?: () => void;
  actions: PanelActions;
  panel: PanelState;
  call: PanelCall;
}) {
  const { t } = useLanguage();
  const copy = t.product;
  const kind = panelRowKind(row);
  const contactId = row.contactId;
  const name = panelName(row, copy);
  const { primary, phone, contact, crmHref, registerSend } = panel;
  const { inReview, onCall } = call;
  const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const companyName = row.kind === "call" || row.kind === "meeting" ? row.item.company_name : null;
  const subtitle = panelHeaderSubtitle(
    contact,
    companyName,
    row.kind === "confirm" ? row.item.detail : null,
  );

  const briefQuery = useQuery({
    queryKey: ["home-panel-brief", contactId, actions.connectionId],
    queryFn: () =>
      api.get<BriefPayload>(briefRequest(contactId as string, actions.connectionId ?? undefined)),
    enabled: Boolean(contactId && kind !== "confirm"),
    staleTime: 30_000,
    retry: false,
  });

  const brief = useMemo(() => {
    const cache = contactId && briefQuery.data ? { contactId, brief: briefQuery.data } : null;
    const flightContactId = briefQuery.isPending && contactId ? contactId : null;
    const failedContactId = briefQuery.isError && contactId && briefFailed(briefQuery.error) ? contactId : null;
    const view = panelBrief({ contactId, cache, flightContactId, failedContactId });
    return {
      ...view,
      notice: view.notice ?? (view.state === "failed" ? copy.panel_brief_failed : null),
    };
  }, [briefQuery.data, briefQuery.error, briefQuery.isError, briefQuery.isPending, contactId, copy.panel_brief_failed]);

  const historyQuery = useQuery({
    queryKey: ["home-panel-history", contactId],
    queryFn: () => api.get<Memo[]>(historyRequest(contactId as string)),
    enabled: Boolean(contactId && showsHistory(actions.provider)),
    staleTime: 30_000,
  });

  const { user } = useAuth();
  const handoffEnabled = Boolean(user?.company?.features?.includes("HANDOFF_ENABLED"));

  const followup = row.kind === "followup"
    ? row.entry
    : followupForContact(actions.followups, contactId);
  const followupMemoId = followup ? ("memoId" in followup ? followup.memoId : followup.memo_id) : null;
  const memoIdForFollowup = inReview ? call.memoId : followupMemoId;
  const line = inReview ? afterCallLine(call.summary, call.crmName) : null;
  const filled = panelFilledPill({ primary, inReview, reviewSave: line?.kind === "review" });

  const onPrimary = () => {
    void panel.runPrimary({
      confirm: async (item) => actions.onConfirm(item),
      openMemo: actions.onOpenMemo,
    }, row);
  };

  const openCrm = () => {
    if (crmHref) window.open(crmHref, "_blank", "noopener,noreferrer");
  };

  const showCardActions = row.kind === "call" && row.source === "today" && row.item.id && row.item.status === "pending";
  const first = firstName(name);
  const canHandOff = handoffEnabled && user?.company?.salesRole !== "ae" && Boolean(contactId);

  return (
    <div className={`flex h-full flex-col p-6 ${THEME_TOKENS.motion.fadeIn}`}>
      <header className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-cream-dark/70 text-[13px] text-beige">
          {initials(name)}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[17px] leading-snug tracking-tight text-foreground">{panelTitle(row, copy)}</p>
          {subtitle ? <p className={`mt-0.5 ${THEME_TOKENS.typography.capsLabel}`}>{subtitle}</p> : null}
        </div>
        {crmHref && primary !== "open" ? (
          <IconAction label={copy.today_open} onClick={openCrm}>
            <ArrowSquareOut size={16} weight="light" />
          </IconAction>
        ) : null}
        {sheet && onClose ? (
          <IconAction label={copy.cancelAction} onClick={onClose}>
            <X size={16} weight="light" />
          </IconAction>
        ) : null}
      </header>

      {row.kind === "meeting" ? (
        <div className={`mt-6 space-y-2 ${THEME_TOKENS.typography.capsLabel}`}>
          <p>{panelMeetingLine(row.time, copy)}</p>
          {row.item.detail ? <p className={THEME_TOKENS.typography.body}>{row.item.detail}</p> : null}
        </div>
      ) : null}

      {row.kind === "confirm" ? (
        <div className="mt-6 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" className="h-9 gap-2 px-4 text-[14px]" onClick={() => actions.onConfirm(row.item)}>
              {copy.confirmAction}
              <span className="text-[13px] text-muted-foreground">↵</span>
            </Button>
            {row.item.memo_id ? (
              <button type="button" className="px-1 py-1.5 text-[13px] text-muted-foreground hover:text-foreground" onClick={() => actions.onOpenMemo(row.item.memo_id as string)}>
                {copy.home_review}
              </button>
            ) : null}
          </div>
        </div>
      ) : null}

      {row.kind === "review" && !inReview ? (
        <div className="mt-6">
          <button type="button" className="px-1 py-1.5 text-[13px] text-muted-foreground hover:text-foreground" onClick={() => actions.onOpenMemo(row.entry.memoId)}>
            {copy.home_review}
          </button>
        </div>
      ) : null}

      {line ? (
        <div className="mt-6">
          {line.kind === "processing" ? (
            <p className={THEME_TOKENS.typography.body}>{copy.panel_processing}</p>
          ) : line.kind === "review" ? (
            filled === "review_save" ? (
              <Button
                type="button"
                className="h-11 w-full rounded-full bg-beige px-[18px] text-[15px] font-normal text-cream hover:bg-beige-dark"
                onClick={() => actions.onOpenMemo(line.memoId)}
              >
                {copy.panel_review_save}
              </Button>
            ) : (
              <button type="button" className="px-1 py-1.5 text-[13px] text-muted-foreground hover:text-foreground" onClick={() => actions.onOpenMemo(line.memoId)}>
                {copy.panel_review_save}
              </button>
            )
          ) : (
            <p className={THEME_TOKENS.typography.body}>
              {line.kind === "saved"
                ? line.minutes
                  ? copy.panel_call_duration_saved.replace("{minutes}", String(line.minutes)).replace("{crm}", call.crmName ?? "")
                  : copy.panel_saved.replace("{crm}", call.crmName ?? "")
                : copy.panel_call_duration.replace("{minutes}", String(line.minutes))}
            </p>
          )}
        </div>
      ) : null}

      {kind !== "confirm" && contactId && !inReview ? (
        <section className="mt-6" aria-label={copy.panel_before_call}>
          <p className={`mb-2.5 ${THEME_TOKENS.typography.capsLabel}`}>{copy.panel_before_call}</p>
          <BriefLines brief={brief} loadingText={copy.teamLoading || BRIEF_LOADING} />
        </section>
      ) : null}

      {filled === "primary" && !onCall ? (
        <div className="mt-5">
          {call.failed ? <p className="mb-2 text-[12px] text-destructive">{copy.panel_call_failed}</p> : null}
          <Button
            type="button"
            className="h-11 w-full justify-between rounded-full bg-beige px-[18px] text-[15px] font-normal text-cream hover:bg-beige-dark"
            onClick={onPrimary}
          >
            <span>{primary === "call" ? copy.panel_call.replace("{name}", first || name) : copy.today_open}</span>
            <span className="text-[13px] opacity-70">↵</span>
          </Button>
          {primary === "call" && phone ? (
            <p className="mt-2 text-[12px] text-muted-foreground">{phone}</p>
          ) : null}
          {showCardActions ? (
            <div className="mt-2 flex flex-wrap items-center gap-1 text-[13px] text-muted-foreground">
              <button
                type="button"
                className="px-1 py-1.5 hover:text-foreground"
                onClick={() => actions.onSnooze(row.item, snoozeUntil(Date.now(), timeZone))}
              >
                {copy.panel_snooze}
              </button>
              <span aria-hidden="true">·</span>
              <button type="button" className="px-1 py-1.5 hover:text-foreground" onClick={() => actions.onDismiss(row.item)}>
                {copy.dismiss}
              </button>
              {actions.onDisqualify ? (
                <>
                  <span aria-hidden="true">·</span>
                  <button type="button" className="px-1 py-1.5 hover:text-foreground" onClick={() => actions.onDisqualify?.(row.item)}>
                    {copy.panel_disqualify_action}
                  </button>
                </>
              ) : null}
            </div>
          ) : null}
          {showCardActions && canHandOff && contactId ? (
            <div className="mt-1">
              <HandoffAction
                contactId={contactId}
                connectionId={row.item.connection_id ?? actions.connectionId}
                dealId={row.item.deal_id}
                memoId={row.item.memo_id}
              />
            </div>
          ) : null}
        </div>
      ) : null}

      {memoIdForFollowup && (row.kind === "followup" || inReview) ? (
        <>
          <hr className="my-5 border-0 border-t border-[hsl(var(--hairline))]" />
          <section aria-label={copy.panel_followup}>
            <p className={`mb-2 ${THEME_TOKENS.typography.capsLabel}`}>{copy.panel_followup}</p>
            <FollowupCard memoId={memoIdForFollowup} onSendReady={registerSend} />
          </section>
        </>
      ) : followup ? (
        <>
          <hr className="my-5 border-0 border-t border-[hsl(var(--hairline))]" />
          <section>
            <p className={`mb-2 ${THEME_TOKENS.typography.capsLabel}`}>{copy.panel_followup_pending}</p>
            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-[14px]">
              {followup.subject ? <span className="text-foreground">{followup.subject}</span> : null}
              {followup.status === "ready" ? (
                <>
                  <span className="text-muted-foreground">· {copy.panel_followup_ready}</span>
                  <button type="button" className="text-[13px] text-muted-foreground hover:text-foreground" onClick={() => followupMemoId && actions.onOpenMemo(followupMemoId)}>
                    {copy.home_open}
                  </button>
                </>
              ) : null}
              {followup.status === "generating" ? (
                <span className="text-muted-foreground">· {copy.home_followup_writing}</span>
              ) : null}
              {followup.status === "unavailable" ? (
                <>
                  <span className="text-muted-foreground">· {copy.home_followup_failed}</span>
                  <button type="button" className="text-[13px] text-muted-foreground hover:text-foreground" onClick={() => followupMemoId && actions.onOpenMemo(followupMemoId)}>
                    {copy.home_open}
                  </button>
                </>
              ) : null}
            </div>
          </section>
        </>
      ) : null}

      {inReview && call.nextRow ? (
        <div className="mt-5">
          <button
            type="button"
            className="px-1 py-1.5 text-[13px] text-muted-foreground hover:text-foreground"
            onClick={call.onNext}
          >
            {copy.panel_next.replace("{name}", panelName(call.nextRow, copy))}
            <span className="ml-2 opacity-70">n</span>
          </button>
        </div>
      ) : null}

      {showsHistory(actions.provider) && contactId && historyQuery.data && historyQuery.data.length > 0 ? (
        <>
          <hr className="my-5 border-0 border-t border-[hsl(var(--hairline))]" />
          <section aria-label={copy.panel_history}>
            <p className={`mb-3 ${THEME_TOKENS.typography.capsLabel}`}>{copy.panel_history}</p>
            <ul className="grid gap-3.5">
              {historyQuery.data.map((memo) => {
                const line = conversationLine(memo, { locale: copy.hourLocale, timeZone });
                const kindLabel = productText(line.kindKey, copy);
                const minutes = line.minutes != null ? copy.panel_minutes.replace("{count}", String(line.minutes)) : null;
                const meta = [line.date, kindLabel, minutes].filter(Boolean).join(" · ");
                const summary = plainSummary(memo.extraction?.summary);
                return (
                  <li key={memo.id}>
                    <button
                      type="button"
                      className="w-full text-left"
                      onClick={() => actions.onOpenMemo(String(memo.id))}
                    >
                      <p className={THEME_TOKENS.typography.capsLabel}>{meta}</p>
                      {summary ? (
                        <p className="mt-0.5 line-clamp-2 text-[14px] leading-snug text-foreground/90">{summary}</p>
                      ) : null}
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        </>
      ) : null}

      <HandoffHistory contactId={contactId} onOpenMemo={actions.onOpenMemo} divider />
    </div>
  );
}

export function ContactPanel({
  row,
  sheet,
  onClose,
  actions,
  panel,
  call,
}: {
  row: HomeRow | null;
  sheet: boolean;
  onClose?: () => void;
  actions: PanelActions;
  panel: PanelState;
  call: PanelCall;
}) {
  const column = useHomeColumn();
  const { t } = useLanguage();
  const target = column?.target;
  if (!row) return null;

  const body = (
    <PanelBody
      row={row}
      sheet={sheet}
      onClose={onClose}
      actions={actions}
      panel={panel}
      call={call}
      key={row.key}
    />
  );

  if (sheet) {
    return (
      <Sheet open modal={false} onOpenChange={(open) => !open && onClose?.()}>
        <SheetPortal>
          <SheetPrimitive.Content
            aria-label={t.product.panel_contact_sheet}
            className="fixed inset-y-0 right-0 z-30 flex h-full w-[400px] max-w-full flex-col border-l border-border/70 bg-card p-0 shadow-lg outline-none data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right data-[state=closed]:duration-300 data-[state=open]:duration-500 xl:hidden"
          >
            {body}
          </SheetPrimitive.Content>
        </SheetPortal>
      </Sheet>
    );
  }

  if (!target) return null;
  return createPortal(body, target);
}
