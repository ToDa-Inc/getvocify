import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import * as SheetPrimitive from "@radix-ui/react-dialog";
import { ArrowUpRight, Check, ChevronDown, ChevronLeft, ChevronRight, ChevronUp, CornerDownRight, Target, Timer, X } from "lucide-react";
import { AudioLines } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { Toggle } from "@/components/ui/toggle";
import { IconAction } from "@/components/ui/icon-action";
import { Sheet, SheetPortal } from "@/components/ui/sheet";
import { Pagination, PaginationContent, PaginationItem } from "@/components/ui/pagination";
import { CHANNEL_ICON, CHANNEL_TILE } from "@/features/interactions/components/InteractionRow";
import { formatCallDuration } from "@/lib/call-duration";
import { channelOf, groupByDay, scrolledToEnd, timeLabel } from "@/lib/interactions";
import { useLanguage } from "@/lib/i18n";
import { afterTone, cleanSummaryLine, hasFindings, UNANSWERED_KEY, type CoachCall, type CoachCallFindings, type CoachCallReading } from "@/lib/rep-coaching";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";
import { Bubble, OccurrencePager, StateTag, WrittenLine, type Moment } from "./OccurrencePager";

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

/** The title of every moment of an opened call: what it is about, and after a dot what kind of moment it is. */
function MomentTitle({ title, kind }: { title: string; kind?: string | null }) {
  return (
    <h4 className="text-[15px] font-medium text-foreground">
      {title}
      {kind ? <span className="ml-2 text-[12px] font-normal text-muted-foreground">· {kind}</span> : null}
    </h4>
  );
}

/** A grey line under the exchange: what happened or why it matters. */
function Why({ children }: { children: ReactNode }) {
  return <p className="text-[13.5px] leading-snug text-muted-foreground">{children}</p>;
}

/** The best this call could give, and whether the rep got it: one line on top of the opened call. */
function CallOutcome({ reading }: { reading: CoachCallReading }) {
  const { t } = useLanguage();
  const p = t.product;
  const best = reading.best_outcome?.what ? reading.best_outcome : null;
  if (!best) return null;
  return (
    <div className="space-y-1.5" data-testid="coach-call-outcome">
      <div className="flex items-start gap-2.5">
        <Target aria-label={p.coachReadingBest} className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.5} />
        <p className="text-[14.5px] leading-snug text-foreground">{best.what}</p>
      </div>
      {best.got !== null ? (
        <div className="pl-[1.625rem]"><StateTag tone={best.got ? "good" : "bad"}>{best.got ? p.coachReadingGot : p.coachReadingNotGot}</StateTag></div>
      ) : null}
    </div>
  );
}

/** The moment the call turned, drawn like every other moment: what they said, what cost it, what to say, and
 * then by their likely answer. */
function KeyMoment({ reading }: { reading: CoachCallReading }) {
  const { t } = useLanguage();
  const p = t.product;
  const steer = reading.steer?.line ? reading.steer : null;
  const [picked, setPicked] = useState<number | null>(null);
  if (!steer && !reading.main_error) return null;
  return (
    <section className="space-y-3" data-testid="coach-call-reading">
      <MomentTitle title={p.coachKeyMoment} />
      <div className="space-y-2.5">
        {reading.decisive_moment?.quote ? <Bubble kind="prospect" caption={p.coachProspectSaid}>{reading.decisive_moment.quote}</Bubble> : null}
        {reading.main_error ? <Why>{reading.main_error}</Why> : null}
        {steer?.line ? <WrittenLine line={steer.line} /> : null}
      </div>
      {steer?.branches.length ? (
        <div className="space-y-2.5">
          <div className="flex flex-wrap gap-1.5" role="group" aria-label={p.coachReadingSteer}>
            {steer.branches.map((branch, index) => (
              <Toggle key={index} variant="chip" size="sm" pressed={picked === index} onPressedChange={(on) => setPicked(on ? index : null)}>
                <CornerDownRight aria-hidden strokeWidth={1.5} />
                {branch.if}
              </Toggle>
            ))}
          </div>
          {picked !== null && steer.branches[picked] ? <WrittenLine line={steer.branches[picked].then} /> : null}
        </div>
      ) : null}
    </section>
  );
}

/** The doors let pass and the questions not fully answered: same anatomy as an objection. */
function FindingMisses({ findings }: { findings: CoachCallFindings }) {
  const { t } = useLanguage();
  const p = t.product;
  const state = {
    no: { tone: "bad", word: p.coachFindingUnanswered },
    later: { tone: "unknown", word: p.coachFindingLater },
    partly: { tone: "half", word: p.coachFindingPartly },
  } as const;
  return (
    <>
      {findings.signals.map((item, index) => (
        <section key={`door-${index}`} className="space-y-3" data-testid="coach-finding-door">
          <MomentTitle title={item.topic} kind={p.coachFindingDoor} />
          <div className="flex items-center gap-2 text-xs"><StateTag tone="bad">{p.coachFindingNotPicked}</StateTag></div>
          <div className="space-y-2.5">
            <Bubble kind="prospect" caption={p.coachProspectSaid}>{item.quote}</Bubble>
            {item.reply ? <Bubble kind="you" caption={p.coachYouReplied}>{item.reply}</Bubble> : null}
            <Why>{item.why}</Why>
            {item.line ? <WrittenLine line={item.line} /> : null}
          </div>
        </section>
      ))}
      {findings.questions.map((item, index) => (
        <section key={`question-${index}`} className="space-y-3" data-testid="coach-finding-question">
          <MomentTitle title={item.topic} kind={p.coachFindingQuestion} />
          <div className="flex items-center gap-2 text-xs">
            <StateTag tone={state[item.answered].tone}>{state[item.answered].word}</StateTag>
            {!item.better && item.no_answer ? <StateTag tone="unknown">{p.coachFindingNoAnswer}</StateTag> : null}
          </div>
          <div className="space-y-2.5">
            <Bubble kind="prospect" caption={p.coachProspectSaid}>{item.quote}</Bubble>
            {item.answer ? <Bubble kind="you" caption={p.coachYouReplied}>{item.answer}</Bubble> : null}
            {item.better ? <WrittenLine line={item.better} /> : null}
          </div>
        </section>
      ))}
    </>
  );
}

/** What worked off the playbook: what the rep said, what the client replied, and when to use it again. */
function FindingWins({ findings }: { findings: CoachCallFindings }) {
  const { t } = useLanguage();
  const p = t.product;
  return (
    <>
      {findings.worked.map((item, index) => (
        <section key={`worked-${index}`} className="space-y-3" data-testid="coach-finding-worked">
          <MomentTitle title={item.topic} kind={p.coachFindingWorked} />
          <div className="flex items-center gap-2 text-xs"><StateTag tone="good">{p.coachAfterAdvanced}</StateTag></div>
          <div className="space-y-2.5">
            <Bubble kind="you" caption={p.coachYouSaid}>{item.quote}</Bubble>
            <Bubble kind="prospect" caption={p.coachTheyThenSaid}>{item.after_quote}</Bubble>
            {item.use_when ? <Why>{item.use_when}</Why> : null}
          </div>
        </section>
      ))}
    </>
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
    // Every moment the same way, one after another with a hairline between them: the outcome on top, then the
    // turning point, what was let pass, the objections, the steps, and what worked.
    <div className="divide-y divide-border/60 [&>*]:py-5">
      {call.reading ? <CallOutcome reading={call.reading} /> : null}
      {call.reading ? <KeyMoment reading={call.reading} /> : null}
      {call.findings ? <FindingMisses findings={call.findings} /> : null}
      {objections.map((objection, index) => {
        const moment: Moment = {
          memo_id: call.memo_id, observed_at: at, tone: afterTone(objection.after, objection.resolution),
          quote: objection.quote, response: objection.response, reason: null, advice: objection.advice ?? null, line: objection.line ?? null,
          after: objection.after ?? null, afterQuote: objection.after_quote ?? null,
        };
        const nature = objection.nature ? natures[objection.nature] : null;
        return (
          <section key={`${objection.key}-${index}`} className="space-y-3">
            <MomentTitle title={objection.key === UNANSWERED_KEY ? p.coachUnanswered : objection.label || categories[objection.category] || objection.category} kind={nature} />
            <OccurrencePager type={type} kind="objection" itemKey={objection.key} how={objection.how} moments={[moment]} eager={index === 0} />
          </section>
        );
      })}
      {slips.map((slip, slipIndex) => {
        const moment: Moment = { memo_id: call.memo_id, observed_at: at, tone: slip.state === "missing" ? "bad" : "half", quote: slip.quote, response: null, reason: slip.reason, advice: slip.advice };
        return (
          <section key={slip.step_id} className="space-y-3">
            <MomentTitle title={slip.label} kind={p.coachStepKind} />
            <OccurrencePager type={type} kind="step" itemKey={slip.step_id} how={null} moments={[moment]} eager={objections.length === 0 && slipIndex === 0} />
          </section>
        );
      })}
      {call.findings ? <FindingWins findings={call.findings} /> : null}
    </div>
  );
}

/** Whether a call has anything to open in the panel beyond the call itself. */
function callHasDetail(call: CoachCall): boolean {
  return (
    call.slips.length > 0 || (call.objections?.length ?? 0) > 0 || hasFindings(call.findings) ||
    Boolean(call.reading?.main_error || call.reading?.steer?.line || call.reading?.best_outcome?.what)
  );
}

/** What the row and the panel's head both show of a call: its channel, what happened, its steps, and when. */
function CallSummary({ call, large = false }: { call: CoachCall; large?: boolean }) {
  const { t } = useLanguage();
  const p = t.product;
  const channel = channelOf(call.kind);
  const Icon = channel ? CHANNEL_ICON[channel] : AudioLines;
  const duration = formatCallDuration(call.duration_s ?? 0);
  const at = call.observed_at ?? "";
  return (
    <>
      <span aria-hidden className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] border", CHANNEL_TILE[channel ?? "voice_note"])}>
        <Icon className="h-[18px] w-[18px]" strokeWidth={1.5} />
      </span>
      <div className="min-w-0 flex-1">
        <p className={cn("leading-snug text-foreground", large ? "text-[17px] tracking-tight" : "truncate text-[15px]")} title={cleanSummaryLine(call.summary_line)}>
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
}

/** One call, the row of Conversaciones. A call with something to look at opens it in the side panel, with the row
 * marked while it is open; one with nothing opens the call. */
function CallRow({ call, open, onOpen }: { call: CoachCall; open: boolean; onOpen: (id: string) => void }) {
  const row = "flex w-full items-center gap-3.5 rounded-xl px-3 py-2.5 text-left transition-colors duration-150 hover:bg-secondary/60 motion-reduce:transition-none";
  if (!callHasDetail(call)) {
    return (
      <li>
        <Link to={`/dashboard/memos/${call.memo_id}`} className={row} data-testid="coach-call">
          <CallSummary call={call} />
          <span className="w-4 shrink-0" aria-hidden />
        </Link>
      </li>
    );
  }
  return (
    <li>
      <button type="button" aria-pressed={open} onClick={() => onOpen(call.memo_id)} className={cn(row, open && "bg-secondary/60")} data-testid="coach-call">
        <CallSummary call={call} />
        <ChevronRight size={16} strokeWidth={1.5} className="shrink-0 text-muted-foreground" />
      </button>
    </li>
  );
}

/** The call opened on the side, the way Hoy opens a contact: the list stays usable, ↑ / ↓ move to the previous and
 * next call, Esc closes. Its head is the row itself; under it, every moment of the call. */
function CallPanel({ call, type, onClose, onMove, canMove }: {
  call: CoachCall;
  type: string;
  onClose: () => void;
  onMove: (step: -1 | 1) => void;
  canMove: { previous: boolean; next: boolean };
}) {
  const { t } = useLanguage();
  const p = t.product;
  const body = useRef<HTMLDivElement>(null);
  useEffect(() => {
    body.current?.scrollTo({ top: 0 });
  }, [call.memo_id]);
  return (
    <Sheet open modal={false} onOpenChange={(next) => !next && onClose()}>
      <SheetPortal>
        <SheetPrimitive.Content
          aria-label={cleanSummaryLine(call.summary_line)}
          onInteractOutside={(event) => event.preventDefault()}
          className="fixed inset-y-0 right-0 z-30 flex h-full w-[520px] max-w-full flex-col border-l border-border/70 bg-card p-0 shadow-lg outline-none data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right data-[state=closed]:duration-300 data-[state=open]:duration-500"
          data-testid="coach-call-panel"
        >
          <SheetPrimitive.Title className="sr-only">{cleanSummaryLine(call.summary_line)}</SheetPrimitive.Title>
          <header className="space-y-3 border-b border-border/60 px-6 pb-4 pt-5">
            <div className="flex items-center justify-end gap-0.5">
              <IconAction label={p.coachPrevious} disabled={!canMove.previous} onClick={() => onMove(-1)}>
                <ChevronUp className="h-4 w-4" strokeWidth={1.5} />
              </IconAction>
              <IconAction label={p.coachNext} disabled={!canMove.next} onClick={() => onMove(1)}>
                <ChevronDown className="h-4 w-4" strokeWidth={1.5} />
              </IconAction>
              <Link to={`/dashboard/memos/${call.memo_id}`} aria-label={p.coachOpenCall} title={p.coachOpenCall} className={THEME_TOKENS.interaction.iconButton}>
                <ArrowUpRight className="h-4 w-4" strokeWidth={1.5} />
              </Link>
              <IconAction label={p.coachClose} onClick={onClose}>
                <X className="h-4 w-4" strokeWidth={1.5} />
              </IconAction>
            </div>
            <div className="flex items-start gap-3.5">
              <CallSummary call={call} large />
            </div>
          </header>
          <div ref={body} className="app-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain px-6 pb-8">
            <CallDetail key={call.memo_id} call={call} type={type} />
          </div>
        </SheetPrimitive.Content>
      </SheetPortal>
    </Sheet>
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

  // The call open on the side, and the calls it can move to (those with something to open), in the list's order.
  const [openId, setOpenId] = useState<string | null>(null);
  const openable = visible.filter(callHasDetail);
  const openIndex = openable.findIndex((call) => call.memo_id === openId);
  const opened = openIndex >= 0 ? openable[openIndex] : null;
  const move = useCallback(
    (step: -1 | 1) => {
      const target = openable[openIndex + step];
      if (!target) return;
      setOpenId(target.memo_id);
      // The list follows the panel onto the page the call is on.
      setPage(Math.floor(visible.findIndex((call) => call.memo_id === target.memo_id) / CALLS_PER_PAGE));
    },
    [openable, openIndex, visible],
  );
  useEffect(() => {
    if (!opened) return;
    const onKey = (event: KeyboardEvent) => {
      const field = event.target instanceof HTMLElement && event.target.closest("input, textarea, [contenteditable=true]");
      if (field || event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        move(event.key === "ArrowDown" ? 1 : -1);
      } else if (event.key === "Escape") {
        // The list keeps focus while the panel is open, so Esc is heard here, not only inside the panel.
        setOpenId(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [opened, move]);

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
                  <CallRow key={call.memo_id} call={call} open={call.memo_id === openId} onOpen={setOpenId} />
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
      {opened ? (
        <CallPanel
          call={opened}
          type={type}
          onClose={() => setOpenId(null)}
          onMove={move}
          canMove={{ previous: openIndex > 0, next: openIndex < openable.length - 1 }}
        />
      ) : null}
    </div>
  );
}
