import { useCallback, useEffect, useRef, useState } from "react";
import { CaretDown, Microphone } from "@phosphor-icons/react";
import { useNavigate } from "react-router-dom";
import { afterActionError, composeHome, type HomeNeedsOkRow, type HomeView } from "@shared/ui/home.js";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { IconAction } from "@/components/ui/icon-action";
import { VoiceRecorderWidget } from "@/components/dashboard/VoiceRecorderWidget";
import { useAuth } from "@/features/auth";
import { CRM_PROVIDER_CONFIGS, type CRMProvider } from "@/features/integrations/types";
import { useLanguage } from "@/lib/i18n";
import { productText, type ProductTranslations } from "@/lib/product-catalog";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import type { TodayItem } from "@/lib/today";
import { useContactPriorities } from "../hooks/useContactPriorities";
import { useHomeReads } from "../hooks/useHomeReads";
import { forgetActed, useTodayCardActions } from "../hooks/useTodayCardActions";
import { HomeSection } from "./HomeSection";
import { TodayItemList } from "./TodayItemList";

type SectionOf<Id extends HomeView["sections"][number]["id"]> = Extract<HomeView["sections"][number], { id: Id }>;

const paper = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card}`;
const textAction = "px-1 py-1.5 text-[13px] text-muted-foreground transition-colors hover:text-foreground";
const hairline = "border-[hsl(var(--hairline))]";

function longDate(now: number, locale: string) {
  return new Intl.DateTimeFormat(locale, { weekday: "long", day: "numeric", month: "long" }).format(new Date(now));
}

function undoOpen(item: TodayItem, now: number) {
  return item.undo_deadline != null && Date.parse(item.undo_deadline) >= now;
}

function pulseLine(pulse: HomeView["pulse"], copy: ProductTranslations) {
  if (!pulse) return null;
  const one = pulse.calls === 1;
  const calls = one ? copy.home_pulse_call : copy.home_pulse_calls.replace("{count}", String(pulse.calls));
  if (!pulse.savedTo) return calls;
  return `${calls}, ${(one ? copy.home_pulse_saved_one : copy.home_pulse_saved).replace("{crm}", pulse.savedTo)}`;
}

function doneLine(row: SectionOf<"done">["rows"][number], copy: ProductTranslations) {
  const name = row.name || copy.today_unknown_contact;
  if (row.kind === "call") return copy.done_call.replace("{name}", name);
  if (row.kind === "followup") return copy.done_followup.replace("{name}", name);
  if (row.kind === "confirmation") return copy.done_confirmed.replace("{what}", name);
  return copy.done_signal.replace("{name}", name);
}

function Meetings({ section, copy }: { section: SectionOf<"meetings">; copy: ProductTranslations }) {
  return (
    <div className="space-y-2">
      {section.items.map(({ item, time, past }) => (
        <div
          key={item.id ?? item.dedupe_key ?? item.reason}
          className={`flex items-baseline gap-3.5 px-[18px] py-[13px] ${paper} ${past ? "opacity-60" : ""}`}
        >
          <p className="min-w-10 shrink-0 whitespace-nowrap text-[15px] leading-normal tabular-nums text-foreground">
            {time ?? copy.home_meeting_no_time}
          </p>
          <p className="min-w-0 truncate text-[15px] leading-normal text-foreground">
            {item.reason || item.contact_name || copy.today_unknown_contact}
            {item.company_name ? <span className="text-muted-foreground"> · {item.company_name}</span> : null}
          </p>
          {item.detail ? (
            <p className="ml-auto max-w-[45%] shrink-0 truncate text-right text-[13.5px] leading-normal text-muted-foreground">{item.detail}</p>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function ConfirmRow({
  item,
  now,
  copy,
  onConfirm,
  onUndo,
  onOpen,
}: {
  item: TodayItem;
  now: number;
  copy: ProductTranslations;
  onConfirm: (item: TodayItem) => void;
  onUndo: (item: TodayItem) => void;
  onOpen: (memoId: string) => void;
}) {
  const settled = item.status != null && item.status !== "pending";
  return (
    <div className="flex min-h-[50px] items-center gap-4 px-[18px] py-3">
      <div className="min-w-0 flex-1">
        <p className="text-[14.5px] leading-normal text-foreground">{item.reason}</p>
        {item.detail ? <p className="mt-px truncate text-[13px] leading-normal text-muted-foreground">{item.detail}</p> : null}
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        {settled ? (
          undoOpen(item, now) ? (
            <button type="button" className={textAction} onClick={() => onUndo(item)}>{copy.undo}</button>
          ) : null
        ) : (
          <>
            <Button type="button" variant="outline" className="h-8 px-3.5 text-[13.5px]" onClick={() => onConfirm(item)}>
              {copy.confirmAction}
            </Button>
            {item.memo_id ? (
              <button type="button" className={textAction} onClick={() => onOpen(item.memo_id as string)}>{copy.home_review}</button>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}

function NeedsOk({
  section,
  now,
  copy,
  onConfirm,
  onUndo,
  onOpen,
}: {
  section: SectionOf<"needs_ok">;
  now: number;
  copy: ProductTranslations;
  onConfirm: (item: TodayItem) => void;
  onUndo: (item: TodayItem) => void;
  onOpen: (memoId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [groupOpen, setGroupOpen] = useState(false);
  const rows = expanded ? section.rows : section.shown;

  const row = (entry: HomeNeedsOkRow) => {
    if (entry.kind === "confirm") {
      return (
        <ConfirmRow
          key={entry.item.id ?? entry.item.dedupe_key ?? entry.item.reason}
          item={entry.item}
          now={now}
          copy={copy}
          onConfirm={onConfirm}
          onUndo={onUndo}
          onOpen={onOpen}
        />
      );
    }
    if (entry.kind === "confirm_group") {
      return (
        <div key="confirm-group" className="divide-y divide-border/60">
          <button
            type="button"
            aria-expanded={groupOpen}
            onClick={() => setGroupOpen((open) => !open)}
            className="group flex min-h-[50px] w-full items-center gap-4 px-[18px] py-3 text-left text-[14.5px] leading-normal text-foreground"
            data-state={groupOpen ? "open" : "closed"}
          >
            <span className="min-w-0 flex-1">{copy.home_confirm_group.replace("{count}", String(entry.count))}</span>
            <CaretDown size={14} weight="light" className="shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-180" />
          </button>
          {groupOpen
            ? entry.items.map((item) => (
                <ConfirmRow
                  key={item.id ?? item.dedupe_key ?? item.reason}
                  item={item}
                  now={now}
                  copy={copy}
                  onConfirm={onConfirm}
                  onUndo={onUndo}
                  onOpen={onOpen}
                />
              ))
            : null}
        </div>
      );
    }
    const name = entry.name || copy.today_unknown_contact;
    const line = entry.kind === "followup" ? copy.home_followup_row.replace("{name}", name) : copy.home_review_row.replace("{name}", name);
    const tail =
      entry.kind !== "followup"
        ? null
        : entry.status === "generating"
          ? copy.home_followup_writing
          : entry.status === "unavailable"
            ? copy.home_followup_failed
            : entry.subject
              ? `«${entry.subject}»`
              : null;
    return (
      <div key={`${entry.kind}:${entry.memoId}`} className="flex min-h-[50px] items-center gap-4 px-[18px] py-3">
        <p className="min-w-0 flex-1 truncate text-[14.5px] leading-normal text-foreground">
          {line}
          {tail ? <span className="text-muted-foreground"> · {tail}</span> : null}
        </p>
        {entry.action ? (
          <button type="button" className={`shrink-0 ${textAction}`} onClick={() => onOpen(entry.memoId)}>
            {entry.action === "review" ? copy.home_review : copy.home_open}
          </button>
        ) : null}
      </div>
    );
  };

  return (
    <>
      <div className={`${paper} divide-y divide-border/60`}>{rows.map(row)}</div>
      {!expanded && section.more > 0 ? (
        <button type="button" className="mx-0.5 mt-2.5 text-[13px] text-muted-foreground transition-colors hover:text-foreground" onClick={() => setExpanded(true)}>
          {copy.today_folded.replace("{count}", String(section.more))}
        </button>
      ) : null}
    </>
  );
}

function Upcoming({ section, copy }: { section: SectionOf<"upcoming">; copy: ProductTranslations }) {
  return (
    <div>
      {section.rows.map((row, index) => (
        <div
          key={`${row.memo_id}:${row.due_at}:${row.text}`}
          className={`grid grid-cols-[84px_1fr_auto] items-baseline gap-3 px-0.5 py-2 ${index ? `border-t ${hairline}` : ""}`}
        >
          <span className="text-[13px] text-muted-foreground">{row.when}</span>
          <span className="text-[14px] leading-normal text-foreground">{row.text}</span>
          {row.inCrm ? <span className="v-chip whitespace-nowrap">{copy.home_in_crm}</span> : <span />}
        </div>
      ))}
    </div>
  );
}

function Done({ section, copy }: { section: SectionOf<"done">; copy: ProductTranslations }) {
  return (
    <Collapsible className="mt-7">
      <CollapsibleTrigger className={`group flex w-full items-center gap-1.5 border-t ${hairline} px-0.5 pt-3.5 text-[13px] text-muted-foreground transition-colors hover:text-foreground`}>
        {copy.home_done} · <span className="tabular-nums">{section.count}</span>
        <CaretDown size={14} weight="light" className="ml-auto transition-transform group-data-[state=open]:rotate-180" />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ul className="mt-2">
          {section.rows.map((row, index) => (
            <li
              key={`${row.kind}:${row.at}:${row.name ?? ""}`}
              className={`grid grid-cols-[84px_1fr] items-baseline gap-3 px-0.5 py-2 ${index ? `border-t ${hairline}` : ""}`}
            >
              <span className="text-[13px] tabular-nums text-muted-foreground">{row.time}</span>
              <span className="text-[14px] leading-normal text-foreground">{doneLine(row, copy)}</span>
            </li>
          ))}
        </ul>
      </CollapsibleContent>
    </Collapsible>
  );
}

export function RepHome() {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const copy = t.product;
  const { user } = useAuth();
  const { query, acted, dismiss, confirm, undo, connected, provider, portalId } = useTodayCardActions({ fresh: true });
  const priorities = useContactPriorities({ fresh: true });
  const reads = useHomeReads();
  const [captureOpen, setCaptureOpen] = useState(false);
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

  const home = composeHome({
    today: query.data ?? null,
    todayError: query.isError && !query.data,
    todayStale: query.isError && Boolean(query.data),
    acted,
    priorities: priorities.data ?? null,
    followups: reads.followups.data ?? null,
    reviews: reads.reviews.isError ? null : reads.reviews.data ?? null,
    upcoming: reads.upcoming.data ?? null,
    done: reads.done.data ?? null,
    connected: connected ?? true,
    role: user?.company?.role ?? "member",
    crm: provider ? CRM_PROVIDER_CONFIGS[provider as CRMProvider]?.name ?? null : null,
    now,
    locale: copy.hourLocale,
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
  const onDismiss = (item: TodayItem) => void settle(() => dismiss(item));
  const onConfirm = (item: TodayItem) => void settle(() => confirm(item));
  const onUndo = (item: TodayItem) => void settle(() => undo(item));
  const openMemo = (memoId: string) => navigate(`/dashboard/memos/${memoId}`);

  const pulse = pulseLine(home.pulse, copy);
  const section = <Id extends HomeView["sections"][number]["id"]>(id: Id) =>
    home.sections.find((entry) => entry.id === id) as SectionOf<Id> | undefined;
  const meetings = section("meetings");
  const needsOk = section("needs_ok");
  const calls = section("calls");
  const upcoming = section("upcoming");
  const done = section("done");
  const callItems = (calls?.items ?? []).map(({ source, item }) =>
    source === "priority" ? { ...item, reason: productText(item.reason, copy) } : item,
  );

  return (
    <div className={`mx-auto max-w-[680px] ${THEME_TOKENS.motion.fadeIn}`} aria-busy={home.state === "loading"}>
      <header className="mb-7">
        <div className="flex items-center justify-between gap-3">
          <h1 className={THEME_TOKENS.typography.pageTitle}>
            {copy.todayTitle}
            <span className="ml-2.5 text-[15px] tracking-normal text-muted-foreground">{longDate(now, copy.hourLocale)}</span>
          </h1>
          <IconAction label={copy.today_capture} onClick={() => setCaptureOpen((open) => !open)}>
            <Microphone size={16} weight="light" />
          </IconAction>
        </div>
        {pulse ? <p className="mt-1.5 text-[15px] leading-relaxed text-muted-foreground">{pulse}</p> : null}
        {home.incompleteAt ? (
          <p className="mt-1.5 text-[15px] leading-relaxed text-muted-foreground">{copy.today_incomplete} · {home.incompleteAt}</p>
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
          <div className={`${paper} space-y-3 p-5`}>
            <p className="text-[15px] text-foreground">{copy.today_connect_title}</p>
            {home.canManage ? null : <p className={THEME_TOKENS.typography.body}>{copy.today_connect_admin_detail}</p>}
            <div className="flex flex-wrap gap-2">
              {home.canManage ? (
                <Button type="button" variant="outline" size="sm" onClick={() => navigate("/dashboard/settings/integrations")}>
                  {copy.connect_crm}
                </Button>
              ) : null}
              <Button type="button" variant="outline" size="sm" onClick={() => setCaptureOpen(true)}>
                {copy.today_record}
              </Button>
            </div>
          </div>
        ) : null}
        {home.state === "no_assigned" ? (
          <div className={`${paper} space-y-3 p-5`}>
            <p className="text-[15px] text-foreground">{copy.title_no_assigned}</p>
            {home.canManage ? null : <p className={THEME_TOKENS.typography.body}>{copy.review_assignment}</p>}
            <div className="flex flex-wrap gap-2">
              {home.canManage ? (
                <Button type="button" variant="outline" size="sm" onClick={() => navigate("/dashboard/settings/integrations")}>
                  {copy.map_owners}
                </Button>
              ) : null}
              <Button type="button" variant="outline" size="sm" onClick={() => setCaptureOpen(true)}>
                {copy.today_record}
              </Button>
            </div>
          </div>
        ) : null}
        {home.state === "clear" ? <p className={THEME_TOKENS.typography.body}>{copy.today_clear}</p> : null}

        <HomeSection title={copy.home_meetings}>
          {meetings ? <Meetings section={meetings} copy={copy} /> : null}
        </HomeSection>
        <HomeSection title={copy.home_needs_ok}>
          {needsOk ? (
            <NeedsOk section={needsOk} now={now} copy={copy} onConfirm={onConfirm} onUndo={onUndo} onOpen={openMemo} />
          ) : null}
        </HomeSection>
        <HomeSection title={copy.home_calls}>
          {calls ? (
            <>
              <TodayItemList items={callItems} onDismiss={onDismiss} onUndo={onUndo} provider={provider} portalId={portalId} />
              {calls.folded > 0 ? (
                <p className="mx-0.5 mt-2.5 text-[13px] text-muted-foreground">{copy.home_folded.replace("{count}", String(calls.folded))}</p>
              ) : null}
            </>
          ) : null}
        </HomeSection>
        <HomeSection title={copy.home_upcoming}>
          {upcoming ? <Upcoming section={upcoming} copy={copy} /> : null}
        </HomeSection>
      </div>

      {done ? <Done section={done} copy={copy} /> : null}
    </div>
  );
}
