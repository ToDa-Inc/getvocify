import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Microphone } from "@phosphor-icons/react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { afterActionError, composeHome, itemKey, type HomeRow, type HomeView } from "@shared/ui/home.js";
import { useHomeColumn } from "@/components/dashboard/HomeColumn";
import { useOptionalDialerFocus } from "@/features/calling/DialerFocusProvider";
import { CRM_PROVIDER_CONFIGS, type CRMProvider } from "@/features/integrations/types";
import { homeQueueNextRow } from "@/lib/today-queue";
import { Button } from "@/components/ui/button";
import { IconAction } from "@/components/ui/icon-action";
import { VoiceRecorderWidget } from "@/components/dashboard/VoiceRecorderWidget";
import { useAuth } from "@/features/auth";
import { useIntegrations } from "@/features/integrations/hooks/useIntegrations";
import { useLanguage } from "@/lib/i18n";
import { productText, type ProductTranslations } from "@/lib/product-catalog";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { dealItems, type TodayItem } from "@/lib/today";
import { focusCounts, focusShows, parseTodayFocus, type TodayFocus } from "@/lib/home-rail";
import { dayChipClass, focusLabel } from "@/features/home/day-chips";
import { useContactPriorities } from "../hooks/useContactPriorities";
import { useHomeReads } from "../hooks/useHomeReads";
import { useHomeSelection } from "../hooks/useHomeSelection";
import { useAfterCall } from "../hooks/useAfterCall";
import { usePanelPrimary } from "../hooks/usePanelPrimary";
import { forgetActed, useTodayCardActions } from "../hooks/useTodayCardActions";
import { ContactPanel } from "./ContactPanel";
import { HomeSection } from "./HomeSection";
import { TodayItemList, type HomeCards } from "./TodayItemList";
import { Done } from "./home/Done";
import { Meetings } from "./home/Meetings";
import { NeedsOk } from "./home/NeedsOk";
import { Upcoming } from "./home/Upcoming";
import { paper, textAction, undoOpen, type SectionOf } from "./home/shared";

/** `undefined` while the first read is in flight, `null` once it failed without data. */
function settled<T>(query: { data: T | undefined; isError: boolean }): T | null | undefined {
  return query.data ?? (query.isError ? null : undefined);
}

function longDate(now: number, locale: string) {
  return new Intl.DateTimeFormat(locale, { weekday: "long", day: "numeric", month: "long" }).format(new Date(now));
}

function pulseLine(pulse: HomeView["pulse"], copy: ProductTranslations) {
  if (!pulse) return null;
  if (pulse.calls === 1) {
    return pulse.savedTo ? copy.home_pulse_call_saved.replace("{crm}", pulse.savedTo) : copy.home_pulse_call;
  }
  const count = String(pulse.calls);
  return pulse.savedTo
    ? copy.home_pulse_calls_saved.replace("{count}", count).replace("{crm}", pulse.savedTo)
    : copy.home_pulse_calls.replace("{count}", count);
}

function StateCard({ title, detail, children }: { title: string; detail?: string | null; children: ReactNode }) {
  return (
    <div className={`${paper} space-y-3 p-5`}>
      <p className="text-[15px] text-foreground">{title}</p>
      {detail ? <p className={THEME_TOKENS.typography.body}>{detail}</p> : null}
      <div className="flex flex-wrap items-center gap-3">{children}</div>
    </div>
  );
}

export function RepHome() {
  const navigate = useNavigate();
  // Inicio's chips open Hoy on one part of the day (?focus=); the chips over Hoy switch it in place.
  const [searchParams, setSearchParams] = useSearchParams();
  const focus = parseTodayFocus(searchParams.get("focus"));
  const setFocus = (next: TodayFocus | null) => setSearchParams(next ? { focus: next } : {}, { replace: true });
  const { t } = useLanguage();
  const copy = t.product;
  const { user } = useAuth();
  const column = useHomeColumn();
  const dialer = useOptionalDialerFocus();
  const panelRef = useRef<ReturnType<typeof usePanelPrimary> | null>(null);
  const [rowNotes, setRowNotes] = useState<Record<string, string>>({});
  const {
    query,
    acted,
    dismiss,
    confirm,
    snooze,
    disqualify,
    undo,
    connected,
    provider,
    portalId,
  } = useTodayCardActions({ fresh: true });
  const priorities = useContactPriorities({ fresh: true });
  const reads = useHomeReads();
  const integrations = useIntegrations();
  const [captureOpen, setCaptureOpen] = useState(false);
  const [needsOkOpen, setNeedsOkOpen] = useState(false);
  const [confirmGroupOpen, setConfirmGroupOpen] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const ticking = acted.some((item) => undoOpen(item, now));
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), ticking ? 1000 : 60_000);
    return () => window.clearInterval(id);
  }, [ticking]);

  const { refetch } = query;
  const wasTicking = useRef(false);
  useEffect(() => {
    if (wasTicking.current && !ticking) void refetch();
    wasTicking.current = ticking;
  }, [ticking, refetch]);

  // Lista 4 T2/T8 (HOY_SDR_SECTIONS_ENABLED): Hoy por bloques instead of one "A quién llamar"
  // list, when GET /today sends them - SDR: Tareas / Seguimiento / Nuevos; AE: Demos de hoy /
  // Tareas / Seguimiento; General: all four.
  const sdrSections = Boolean(user?.company?.features?.includes("HOY_SDR_SECTIONS_ENABLED"));
  const homeRaw = composeHome({
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
    now,
    locale: copy.hourLocale,
    sdrSections,
  });

  const settle = useCallback(
    async (run: () => Promise<void>) => {
      try {
        await run();
      } catch (error) {
        const outcome = afterActionError(error);
        if (!outcome) throw error;
        if (outcome.forget) forgetActed(outcome.forget);
        await refetch();
      }
    },
    [refetch],
  );

  const openMemo = useCallback((memoId: string) => navigate(`/dashboard/memos/${memoId}`), [navigate]);

  const onPrimary = useCallback(
    (row: HomeRow) => {
      void panelRef.current?.runPrimary(
        {
          confirm: async (item) => settle(() => confirm(item)),
          openMemo,
        },
        row,
      );
    },
    [confirm, openMemo, settle],
  );

  const {
    view: home,
    rows,
    row: selectedRow,
    selectedKey,
    wide,
    sheetOpen,
    locked,
    select,
    clear,
    lockOnCall,
    onCallEnded,
    resolveCall,
    finishReview,
    selection,
  } = useHomeSelection(homeRaw, { needsOkOpen, groupOpen: confirmGroupOpen }, onPrimary);

  const callPhase = dialer?.phase ?? "idle";
  const onCall = callPhase === "dialing" || callPhase === "in_call";
  const callContactId = dialer?.activeContact?.contactId ?? null;
  useEffect(() => {
    if (!onCall || !callContactId || locked) return;
    const key =
      selectedRow?.contactId === callContactId
        ? selectedRow.key
        : (rows.find((row) => row.kind === "call" && row.contactId === callContactId) ??
            rows.find((row) => row.contactId === callContactId))?.key;
    if (key) lockOnCall(key);
  }, [onCall, callContactId, locked, rows, selectedRow, lockOnCall]);

  const lastEnded = dialer?.lastEnded ?? null;
  const clearEnded = dialer?.clearEnded;
  useEffect(() => {
    if (!lastEnded) return;
    onCallEnded(lastEnded);
    clearEnded?.();
  }, [lastEnded, clearEnded, onCallEnded]);

  // A dialer torn down mid-call goes idle without an end report; never leave the home locked.
  useEffect(() => {
    if (locked && callPhase === "idle") onCallEnded({ callSid: null, answered: false });
  }, [locked, callPhase, onCallEnded]);

  const lastCall = selection.lastCall;
  useEffect(() => {
    if (lastCall?.outcome !== "no_answer") return;
    const stamp = new Intl.DateTimeFormat(copy.hourLocale, { hour: "numeric", minute: "2-digit" }).format(new Date());
    setRowNotes((prev) => ({ ...prev, [lastCall.key]: copy.panel_no_answer.replace("{time}", stamp) }));
  }, [lastCall, copy.hourLocale, copy.panel_no_answer]);

  const inReview = selection.mode === "review";
  const callSummary = useAfterCall(selection.callSid ?? null, inReview, resolveCall);
  const nextRow = useMemo(() => (inReview ? homeQueueNextRow(selection, rows) : null), [inReview, selection, rows]);

  const panel = usePanelPrimary(selectedRow, {
    provider: provider ?? null,
    portalId: portalId ?? null,
    inReview,
  });

  panelRef.current = panel;
  const onDismiss = (item: TodayItem) => void settle(() => dismiss(item));
  const onConfirm = (item: TodayItem) => void settle(() => confirm(item));
  const onSnooze = (item: TodayItem, until: string) => void settle(() => snooze(item, until));
  const onDisqualify = (item: TodayItem) => void settle(() => disqualify(item));
  const onUndo = (item: TodayItem) => void settle(() => undo(item));
  const record = () => setCaptureOpen(true);
  const toIntegrations = () => navigate("/dashboard/settings/integrations");

  const pulse = pulseLine(home.pulse, copy);
  const section = <Id extends HomeView["sections"][number]["id"]>(id: Id) =>
    home.sections.find((entry) => entry.id === id) as SectionOf<Id> | undefined;
  const shows = (id: string) => focusShows(focus, id);
  const chips = focusCounts(home);
  const focusEmpty = focus !== null && home.state === "day" && !chips.some((chip) => chip.focus === focus);
  const meetings = section("meetings");
  const demos = section("demos");
  const needsOk = section("needs_ok");
  const calls = section("calls");
  const tasks = section("tasks");
  const followups = section("followups");
  const fresh = section("new");
  const upcoming = section("upcoming");
  const done = section("done");
  const cardItems = (entries: { source: "today" | "priority"; item: TodayItem }[] | undefined) =>
    (entries ?? []).map(({ source, item }) =>
      source === "priority" ? { ...item, reason: productText(item.reason, copy) } : item,
    );
  const foldedLine = home.folded ? (
    <p className={`mx-0.5 mt-2.5 ${THEME_TOKENS.typography.capsLabel}`}>
      {copy.home_folded.replace("{count}", String(home.folded.count))}
    </p>
  ) : null;
  const foldedUnder = (id: NonNullable<HomeView["folded"]>["after"]) =>
    home.folded?.after === id && (id === null ? focus === null : shows(id)) ? foldedLine : null;
  const recordText = (
    <button type="button" className={textAction} onClick={record}>{copy.today_record}</button>
  );
  const recordButton = (
    <Button type="button" variant="outline" size="sm" onClick={record}>{copy.today_record}</Button>
  );

  const selectionProps = {
    selectedKey,
    onSelect: select,
  };

  const inCallKey = locked ? selectedKey : null;
  const crmName = provider ? CRM_PROVIDER_CONFIGS[provider as CRMProvider]?.name ?? null : null;

  const homeCards: HomeCards = {
    selectedKey,
    onSelect: (item) => select(itemKey(item)),
    canDial: column?.canDial ?? false,
    now,
    locked,
    inCallKey,
    inCallElapsed: dialer?.liveElapsed ?? null,
    rowNotes,
    leadTiersEnabled: Boolean(user?.company?.features?.includes("HOY_LEAD_TIERS_ENABLED")),
  };

  const connectionId =
    integrations.data?.find((connection) => connection.status === "connected")?.id ?? null;

  // T6 (HOY_AE_DEALS_ENABLED): the AE's/General's "Deals en curso" - active handoffs plus
  // their own deals with a memo, from GET /today's `sections`, not from the calls list.
  const dealsEnabled = Boolean(user?.company?.features?.includes("HOY_AE_DEALS_ENABLED"));
  // The AE keeps "A quién llamar": those are the AE's own follow-ups (callbacks they
  // promised, open objections). Prospecting tiers never reach an AE - the backend only
  // computes them for SDR/General.
  // Lista 4 T8 (E13): with Hoy por bloques the deals are not listed whole - a deal comes back
  // in Seguimiento when it is due, so «Deals en curso» is not painted.
  const sectioned = sdrSections && Array.isArray(settled(query)?.sections?.tasks);
  const deals = dealsEnabled && !sectioned ? dealItems(settled(query)) : [];

  // Falta tu OK: on Hoy por bloques it sits right under Tareas (its follow-up emails to
  // send are tasks too); otherwise where it always was, above "A quién llamar".
  const needsOkSection = (
    <HomeSection title={copy.home_needs_ok}>
      {needsOk ? (
        <>
          <NeedsOk
            section={needsOk}
            now={now}
            copy={copy}
            onConfirm={onConfirm}
            onUndo={onUndo}
            onOpen={openMemo}
            expanded={needsOkOpen}
            onExpandedChange={setNeedsOkOpen}
            groupOpen={confirmGroupOpen}
            onGroupOpenChange={setConfirmGroupOpen}
            {...selectionProps}
          />
          {foldedUnder("needs_ok")}
        </>
      ) : null}
    </HomeSection>
  );
  const cardSection = (
    entries: { source: "today" | "priority"; item: TodayItem }[] | undefined,
    id: "calls" | "tasks" | "followups" | "new",
  ) =>
    entries ? (
      <>
        <TodayItemList
          items={cardItems(entries)}
          onDismiss={onDismiss}
          onUndo={onUndo}
          provider={provider}
          portalId={portalId}
          home={homeCards}
        />
        {foldedUnder(id)}
      </>
    ) : null;

  return (
    <>
      <div className={`mx-auto max-w-[680px] ${THEME_TOKENS.motion.fadeIn}`} aria-busy={home.state === "loading"}>
        <header className="mb-6 space-y-4">
          <div className="flex items-center justify-between gap-3">
            <Link
              to="/dashboard"
              className="-ml-2 inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-[13.5px] text-muted-foreground transition-colors hover:bg-secondary/50 hover:text-foreground"
            >
              <ArrowLeft aria-hidden className="h-4 w-4" />
              {copy.navHome}
            </Link>
            <div className="flex items-center gap-2">
              <span className="text-[13px] capitalize text-muted-foreground">{longDate(now, copy.hourLocale)}</span>
              <IconAction label={copy.today_capture} onClick={() => setCaptureOpen((open) => !open)}>
                <Microphone size={16} weight="light" />
              </IconAction>
            </div>
          </div>
          {chips.length ? (
            <nav aria-label={copy.todayTitle} className="flex flex-wrap gap-2">
              <button type="button" aria-pressed={focus === null} className={dayChipClass(focus === null)} onClick={() => setFocus(null)}>
                {copy.today_focus_all}
              </button>
              {chips.map((chip) => (
                <button
                  key={chip.focus}
                  type="button"
                  aria-pressed={focus === chip.focus}
                  className={dayChipClass(focus === chip.focus)}
                  onClick={() => setFocus(focus === chip.focus ? null : chip.focus)}
                >
                  <span>{focusLabel(chip.focus, copy)}</span>
                  <span className="tabular-nums text-muted-foreground">{chip.count}</span>
                </button>
              ))}
            </nav>
          ) : null}
          {pulse || home.incompleteAt ? (
            <div className={`space-y-1 ${THEME_TOKENS.typography.body}`}>
              {pulse ? <p>{pulse}</p> : null}
              {home.incompleteAt ? <p>{copy.today_incomplete} · {home.incompleteAt}</p> : null}
            </div>
          ) : null}
        </header>

        {captureOpen ? (
          <div className="mb-6">
            <VoiceRecorderWidget quiet onComplete={openMemo} />
          </div>
        ) : null}

        <div className="space-y-6">
          {home.state === "loading" ? (
            <div className="space-y-2" aria-hidden="true">
              {[0, 1, 2].map((key) => (
                <div key={key} className={`h-16 ${paper} motion-safe:animate-[v-breathe_1.6s_ease-in-out_infinite]`} />
              ))}
            </div>
          ) : null}
          {home.state === "error" ? (
            <div className="flex flex-wrap items-center gap-3" role="alert">
              <p className={THEME_TOKENS.typography.body}>{copy.today_prepare_failed}</p>
              <Button type="button" variant="outline" size="sm" onClick={() => void refetch()}>
                {copy.retry}
              </Button>
            </div>
          ) : null}
          {home.state === "connect" ? (
            <StateCard title={copy.today_connect_title} detail={home.canManage ? null : copy.today_connect_admin_detail}>
              {home.canManage ? (
                <>
                  <Button type="button" variant="outline" size="sm" onClick={toIntegrations}>{copy.connect_crm}</Button>
                  {recordText}
                </>
              ) : recordButton}
            </StateCard>
          ) : null}
          {home.state === "no_assigned" ? (
            <StateCard title={copy.title_no_assigned} detail={home.canManage ? null : copy.review_assignment}>
              {home.canManage ? (
                <>
                  <Button type="button" variant="outline" size="sm" onClick={toIntegrations}>{copy.map_owners}</Button>
                  {recordText}
                </>
              ) : recordButton}
            </StateCard>
          ) : null}
          {home.state === "clear" ? <p className={THEME_TOKENS.typography.body}>{copy.today_clear}</p> : null}
          {focusEmpty ? (
            <div className="flex flex-wrap items-center gap-3">
              <p className={THEME_TOKENS.typography.body}>{copy.today_focus_empty}</p>
              <Button type="button" variant="outline" size="sm" onClick={() => setFocus(null)}>
                {copy.today_focus_see_all}
              </Button>
            </div>
          ) : null}

          <HomeSection title={copy.home_demos}>
            {demos && shows("demos") ? (
              <>
                <Meetings section={demos} copy={copy} {...selectionProps} />
                {foldedUnder("demos")}
              </>
            ) : null}
          </HomeSection>
          <HomeSection title={copy.home_meetings}>
            {meetings && shows("meetings") ? (
              <>
                <Meetings section={meetings} copy={copy} {...selectionProps} />
                {foldedUnder("meetings")}
              </>
            ) : null}
          </HomeSection>
          {sectioned ? (
            <>
              <HomeSection title={copy.home_tasks}>{shows("tasks") ? cardSection(tasks?.items, "tasks") : null}</HomeSection>
              {shows("needs_ok") ? needsOkSection : null}
              <HomeSection title={copy.home_followups}>{shows("followups") ? cardSection(followups?.items, "followups") : null}</HomeSection>
              <HomeSection title={copy.home_new}>{shows("new") ? cardSection(fresh?.items, "new") : null}</HomeSection>
            </>
          ) : (
            <>
              {shows("needs_ok") ? needsOkSection : null}
              <HomeSection title={copy.home_calls}>{shows("calls") ? cardSection(calls?.items, "calls") : null}</HomeSection>
            </>
          )}
          {focus === null && dealsEnabled && deals.length > 0 ? (
            <HomeSection title={copy.home_deals}>
              <TodayItemList
                items={deals}
                onDismiss={onDismiss}
                onUndo={onUndo}
                provider={provider}
                portalId={portalId}
                connectionId={connectionId}
              />
            </HomeSection>
          ) : null}
          {foldedUnder(null)}
          <HomeSection title={copy.home_upcoming}>
            {upcoming && focus === null ? <Upcoming section={upcoming} copy={copy} /> : null}
          </HomeSection>
        </div>

        {done && focus === null ? <Done section={done} copy={copy} /> : null}
      </div>

      <ContactPanel
        row={selectedRow}
        sheet={sheetOpen}
        onClose={clear}
        panel={panel}
        call={{
          onCall,
          inReview,
          failed: selection.mode === "queue" && selection.lastOutcome === "failed",
          summary: callSummary,
          memoId: callSummary?.memoId ?? selection.memoId ?? null,
          crmName,
          nextRow,
          onNext: finishReview,
        }}
        actions={{
          onConfirm,
          onDismiss,
          onSnooze,
          onDisqualify,
          onOpenMemo: openMemo,
          provider: provider ?? null,
          connectionId,
          followups: reads.followups.data,
        }}
      />
    </>
  );
}
