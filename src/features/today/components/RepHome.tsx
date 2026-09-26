import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Microphone } from "@phosphor-icons/react";
import { useNavigate } from "react-router-dom";
import { afterActionError, composeHome, type HomeView } from "@shared/ui/home.js";
import { Button } from "@/components/ui/button";
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
  const record = () => setCaptureOpen(true);
  const toIntegrations = () => navigate("/dashboard/settings/integrations");

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
  const foldedLine = home.folded ? (
    <p className={`mx-0.5 mt-2.5 ${THEME_TOKENS.typography.capsLabel}`}>
      {copy.home_folded.replace("{count}", String(home.folded.count))}
    </p>
  ) : null;
  const foldedUnder = (id: "meetings" | "needs_ok" | "calls") => (home.folded?.after === id ? foldedLine : null);
  const recordText = (
    <button type="button" className={textAction} onClick={record}>{copy.today_record}</button>
  );
  const recordButton = (
    <Button type="button" variant="outline" size="sm" onClick={record}>{copy.today_record}</Button>
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
        {pulse ? <p className={`mt-1.5 ${THEME_TOKENS.typography.body}`}>{pulse}</p> : null}
        {home.incompleteAt ? (
          <p className={`mt-1.5 ${THEME_TOKENS.typography.body}`}>{copy.today_incomplete} · {home.incompleteAt}</p>
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

        <HomeSection title={copy.home_meetings}>
          {meetings ? (
            <>
              <Meetings section={meetings} copy={copy} />
              {foldedUnder("meetings")}
            </>
          ) : null}
        </HomeSection>
        <HomeSection title={copy.home_needs_ok}>
          {needsOk ? (
            <>
              <NeedsOk section={needsOk} now={now} copy={copy} onConfirm={onConfirm} onUndo={onUndo} onOpen={openMemo} />
              {foldedUnder("needs_ok")}
            </>
          ) : null}
        </HomeSection>
        <HomeSection title={copy.home_calls}>
          {calls ? (
            <>
              <TodayItemList items={callItems} onDismiss={onDismiss} onUndo={onUndo} provider={provider} portalId={portalId} />
              {foldedUnder("calls")}
            </>
          ) : null}
        </HomeSection>
        {home.folded?.after === null ? foldedLine : null}
        <HomeSection title={copy.home_upcoming}>
          {upcoming ? <Upcoming section={upcoming} copy={copy} /> : null}
        </HomeSection>
      </div>

      {done ? <Done section={done} copy={copy} /> : null}
    </div>
  );
}
