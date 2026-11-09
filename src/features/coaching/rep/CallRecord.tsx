import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Check, ChevronDown, ChevronLeft, ChevronRight, Timer } from "lucide-react";
import { AudioLines } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Pagination, PaginationContent, PaginationItem } from "@/components/ui/pagination";
import { CHANNEL_ICON, CHANNEL_TILE } from "@/features/interactions/components/InteractionRow";
import { formatCallDuration } from "@/lib/call-duration";
import { channelOf, groupByDay, scrolledToEnd, timeLabel } from "@/lib/interactions";
import { useLanguage } from "@/lib/i18n";
import { cleanSummaryLine, type CoachCall, type CoachCallReading } from "@/lib/rep-coaching";
import { cn } from "@/lib/utils";
import { Bubble, OccurrencePager, type Moment } from "./OccurrencePager";

/** The record shows the app's list size per page, in a panel that dissolves at its bottom edge while
 * there is more to read (Inicio's list), with the pager of Conversaciones under it. */
const CALLS_PER_PAGE = 20;
const FADE = "linear-gradient(to bottom, black calc(100% - 72px), transparent 100%)";

/** The steps of one call at a glance: one segment each, green done, amber halfway, red not done. */
function StepMeter({ call }: { call: CoachCall }) {
  const { t } = useLanguage();
  const p = t.product;
  if (!call.applicable) {
    const count = call.objections?.length ?? 0;
    return (
      <span className="text-xs text-muted-foreground">
        {p.coachCallNothingJudged}
        {count ? ` · ${count} ${count === 1 ? p.coachObjectionOne : p.coachObjectionMany}` : ""}
      </span>
    );
  }
  const halfway = call.slips.filter((slip) => slip.state === "improvable").length;
  const missing = call.slips.filter((slip) => slip.state === "missing").length;
  const segments = [
    ...Array(Math.max(0, call.done - halfway)).fill("bg-success/70"),
    ...Array(halfway).fill("bg-warning/80"),
    ...Array(missing).fill("bg-destructive/70"),
  ];
  return (
    <span className="flex items-center gap-2" role="img" aria-label={`${p.coachCardSteps} ${call.done}/${call.applicable}`}>
      <span className="flex w-24 gap-0.5">
        {segments.map((tone, index) => (
          <span key={index} className={cn("h-1.5 flex-1 rounded-full", tone)} />
        ))}
      </span>
      <span className="text-xs tabular-nums text-muted-foreground">
        {call.done}/{call.applicable}
      </span>
      {!call.slips.length ? (
        <span className="inline-flex items-center gap-1 rounded-full bg-success/10 px-2 py-0.5 text-[11px] font-medium text-success">
          <Check aria-hidden className="h-3 w-3" strokeWidth={2} />
          {p.coachAllDone}
        </span>
      ) : null}
      {call.meeting_agreed ? <span className="text-xs text-success">{p.coachCardMeeting} · {p.coachCardYes}</span> : null}
    </span>
  );
}

/** The call as a whole (C04 v9), first: what cost it most, how to steer the decisive moment next time,
 * and the best it could have given. Each part only when the reading has it. */
function CallReading({ reading }: { reading: CoachCallReading }) {
  const { t } = useLanguage();
  const p = t.product;
  const steer = reading.steer?.line ? reading.steer : null;
  const best = reading.best_outcome?.what ? reading.best_outcome : null;
  if (!reading.main_error && !steer && !best) return null;
  return (
    <div className="space-y-5" data-testid="coach-call-reading">
      {reading.main_error ? (
        <section className="space-y-1.5">
          <h4 className="text-[15px] font-medium text-foreground">{p.coachReadingError}</h4>
          <p className="text-[14.5px] leading-snug text-foreground/90">{reading.main_error}</p>
        </section>
      ) : null}
      {steer ? (
        <section className="space-y-2">
          <h4 className="text-[15px] font-medium text-foreground">{p.coachReadingSteer}</h4>
          <div className="space-y-2.5">
            {reading.decisive_moment?.quote ? <Bubble kind="prospect" caption={p.coachReadingWhenTheySaid}>{reading.decisive_moment.quote}</Bubble> : null}
            <Bubble kind="better" caption={p.coachReadingSay}>
              <span className="font-medium">{steer.line}</span>
            </Bubble>
          </div>
          {steer.branches.length ? (
            <ul className="space-y-1.5 pt-1">
              {steer.branches.map((branch, index) => (
                <li key={index} className="text-[13.5px] leading-snug">
                  <span className="text-muted-foreground">{branch.if}</span>
                  <span aria-hidden className="text-muted-foreground"> → </span>
                  <span className="text-foreground">«{branch.then}»</span>
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}
      {best ? (
        <section className="space-y-1.5">
          <h4 className="text-[15px] font-medium text-foreground">{p.coachReadingBest}</h4>
          <p className="text-[14.5px] leading-snug text-foreground/90">{best.what}</p>
          {best.got !== null ? (
            <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium", best.got ? "bg-success/10 text-success" : "bg-destructive/10 text-destructive")}>
              {best.got ? p.coachReadingGot : p.coachReadingNotGot}
            </span>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}

/** One call opened: first the call as a whole (when it was read with v9), then each objection, then each
 * step slipped on, one moment each, with the line to say instead. The worst first within each. */
function CallDetail({ call, type }: { call: CoachCall; type: string }) {
  const { t } = useLanguage();
  const p = t.product;
  const categories = p.playbookObjectionCategories as Record<string, string>;
  const natures = p.coachObjectionNatures as Record<string, string>;
  const slips = [...call.slips].sort((a, b) => Number(a.state !== "missing") - Number(b.state !== "missing"));
  const objections = [...(call.objections ?? [])].sort((a, b) => Number(a.resolution === "resolved") - Number(b.resolution === "resolved"));
  const at = call.observed_at ?? "";
  return (
    <div className="space-y-5 py-3">
      {call.reading ? <CallReading reading={call.reading} /> : null}
      {objections.map((objection, index) => {
        const moment: Moment = {
          memo_id: call.memo_id, observed_at: at, tone: objection.resolution === "resolved" ? "good" : objection.resolution === "open" ? "bad" : "unknown",
          quote: objection.quote, response: objection.response, reason: null, advice: objection.advice ?? null, line: objection.line ?? null,
        };
        const nature = objection.nature ? natures[objection.nature] : null;
        return (
          <section key={`${objection.key}-${index}`} className="space-y-2">
            <h4 className="text-[15px] font-medium text-foreground">
              {objection.label || categories[objection.category] || objection.category}
              {nature ? <span className="ml-2 text-[12px] font-normal text-muted-foreground">· {nature}</span> : null}
            </h4>
            <OccurrencePager type={type} kind="objection" itemKey={objection.key} how={objection.how} moments={[moment]} eager={index === 0} />
          </section>
        );
      })}
      {slips.map((slip, slipIndex) => {
        const moment: Moment = { memo_id: call.memo_id, observed_at: at, tone: slip.state === "missing" ? "bad" : "half", quote: slip.quote, response: null, reason: slip.reason, advice: slip.advice };
        return (
          <section key={slip.step_id} className="space-y-2">
            <h4 className="text-[15px] font-medium text-foreground">{slip.label}</h4>
            <OccurrencePager type={type} kind="step" itemKey={slip.step_id} how={null} moments={[moment]} eager={objections.length === 0 && slipIndex === 0} />
          </section>
        );
      })}
    </div>
  );
}

/** One call, the row of Conversaciones: its channel, what happened, its steps as a meter, and when. A
 * call with something to improve opens in place; one with nothing opens the call. */
function CallRow({ call, type }: { call: CoachCall; type: string }) {
  const { t } = useLanguage();
  const p = t.product;
  const channel = channelOf(call.kind);
  const Icon = channel ? CHANNEL_ICON[channel] : AudioLines;
  const duration = formatCallDuration(call.duration_s ?? 0);
  const at = call.observed_at ?? "";
  const hasDetail = call.slips.length > 0 || (call.objections?.length ?? 0) > 0 || Boolean(call.reading?.main_error || call.reading?.steer?.line || call.reading?.best_outcome?.what);
  const body = (
    <>
      <span aria-hidden className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] border", CHANNEL_TILE[channel ?? "voice_note"])}>
        <Icon className="h-[18px] w-[18px]" strokeWidth={1.5} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[15px] leading-snug text-foreground" title={cleanSummaryLine(call.summary_line)}>
          {cleanSummaryLine(call.summary_line)}
        </p>
        <div className="mt-1">
          <StepMeter call={call} />
        </div>
      </div>
      <div className="w-[4.25rem] shrink-0 text-right tabular-nums leading-tight">
        <time dateTime={at} className="block text-[13px] text-foreground/85">
          {at ? timeLabel(at, p.hourLocale) : ""}
        </time>
        {duration ? (
          <span className="mt-0.5 inline-flex items-center gap-1 text-[11.5px] text-muted-foreground">
            <Timer aria-hidden className="h-3 w-3" strokeWidth={1.5} />
            {duration}
          </span>
        ) : null}
      </div>
    </>
  );
  const row = "flex w-full items-center gap-3.5 rounded-xl px-3 py-2.5 text-left transition-colors duration-150 hover:bg-secondary/60 motion-reduce:transition-none";
  if (!hasDetail) {
    return (
      <li>
        <Link to={`/dashboard/memos/${call.memo_id}`} className={row} data-testid="coach-call">
          {body}
          <span className="w-4 shrink-0" aria-hidden />
        </Link>
      </li>
    );
  }
  return (
    <li data-testid="coach-call">
      <Collapsible>
        <CollapsibleTrigger className={cn("group", row, "data-[state=open]:bg-secondary/60")}>
          {body}
          <ChevronDown size={16} strokeWidth={1.5} className="shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-180" />
        </CollapsibleTrigger>
        <CollapsibleContent className="ml-[1.4rem] border-l border-border/70 pb-3 pl-5 pr-3">
          <CallDetail call={call} type={type} />
          <Link
            to={`/dashboard/memos/${call.memo_id}`}
            className="mt-1 inline-flex items-center gap-1 text-[13px] text-muted-foreground transition-colors hover:text-foreground"
          >
            {p.coachOpenCall}
            <ArrowUpRight aria-hidden className="h-3.5 w-3.5" />
          </Link>
        </CollapsibleContent>
      </Collapsible>
    </li>
  );
}

/** "Tus llamadas": the calls of the window under Hoy / Ayer / dates, a page of 20 at a time. */
export function CallRecord({ calls, type }: { calls: CoachCall[]; type: string }) {
  const { t } = useLanguage();
  const p = t.product;
  const copy = p.interactions;
  const [page, setPage] = useState(0);
  // Calls and meetings are listed together; a switch appears only when the type has both.
  const [channel, setChannel] = useState("all");
  const present = [...new Set(calls.map((call) => call.kind || "call"))];
  const active = present.includes(channel) ? channel : "all";
  const visible = active === "all" ? calls : calls.filter((call) => (call.kind || "call") === active);
  const pages = Math.ceil(visible.length / CALLS_PER_PAGE);
  const current = Math.min(page, Math.max(0, pages - 1));
  const shown = visible.slice(current * CALLS_PER_PAGE, (current + 1) * CALLS_PER_PAGE);
  const names = p.pb2.ruleChannels as Record<string, string>;
  const groups = groupByDay(shown.map((call) => ({ call, createdAt: call.observed_at ?? "" })), new Date(), p.hourLocale);

  const scroller = useRef<HTMLDivElement>(null);
  const [atEnd, setAtEnd] = useState(true);
  const measure = useCallback(() => {
    if (scroller.current) setAtEnd(scrolledToEnd(scroller.current));
  }, []);
  useEffect(() => {
    measure();
    const node = scroller.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    // Rows opening and closing change the height of what is inside, not of the panel.
    if (node.firstElementChild) observer.observe(node.firstElementChild);
    return () => observer.disconnect();
  }, [measure, shown.length]);
  const goTo = (next: number) => {
    setPage(next);
    scroller.current?.scrollTo({ top: 0 });
  };
  const fade = atEnd ? undefined : { maskImage: FADE, WebkitMaskImage: FADE };

  return (
    <div className="space-y-3">
      {present.length > 1 ? (
        <div className="px-3">
          <Segmented
            value={active}
            onValueChange={(next) => {
              setChannel(next);
              setPage(0);
            }}
            aria-label={copy.channelFilter}
            options={[{ value: "all", label: p.coachChannelAll }, ...present.map((kind) => ({ value: kind, label: names[kind] ?? kind }))]}
          />
        </div>
      ) : null}
      <div ref={scroller} onScroll={measure} style={fade} className="app-scroll max-h-[min(56vh,34rem)] overflow-y-auto overscroll-contain">
        <div className="space-y-4">
          {groups.map((group) => (
            <section key={group.key} aria-label={group.label || undefined}>
              {group.label ? <h3 className="px-3 pb-1 text-[13px] font-medium text-muted-foreground">{group.label}</h3> : null}
              <ul className="space-y-0.5">
                {group.items.map(({ call }) => (
                  <CallRow key={call.memo_id} call={call} type={type} />
                ))}
              </ul>
            </section>
          ))}
        </div>
      </div>
      {pages > 1 ? (
        <Pagination aria-label={copy.pages}>
          <PaginationContent className="gap-3">
            <PaginationItem>
              <Button variant="outline" size="sm" disabled={current === 0} onClick={() => goTo(current - 1)}>
                <ChevronLeft aria-hidden />
                {copy.previous}
              </Button>
            </PaginationItem>
            <PaginationItem aria-current="page" className="text-[13px] tabular-nums text-muted-foreground">
              {copy.page.replace("{n}", String(current + 1))} / {pages}
            </PaginationItem>
            <PaginationItem>
              <Button variant="outline" size="sm" disabled={current >= pages - 1} onClick={() => goTo(current + 1)}>
                {copy.next}
                <ChevronRight aria-hidden />
              </Button>
            </PaginationItem>
          </PaginationContent>
        </Pagination>
      ) : null}
    </div>
  );
}
