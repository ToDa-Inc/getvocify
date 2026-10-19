import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ChevronRight, History, Info, ListChecks, MessageCircleQuestion, MessageSquareText, ShieldCheck, Sparkles, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { pointsView, progressView } from "@/lib/live-brain";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";
import type { LiveBrain } from "../assist/useLiveBrain";
import { AhoraCard, ConversacionPane } from "./ConversacionPane";
import { AyudaPane } from "./AyudaPane";
import { clock, pointTag, type LiveCopy } from "./copy";
import { Dots, PointCard } from "./PointCard";

type Tab = "transcript" | "help" | "conversation";
/** What the peek shows: a window onto an object that also lives in its tab. */
type Peek = { kind: "point"; id: string } | { kind: "responder" } | { kind: "nothing" } | { kind: "now" } | { kind: "recap" } | null;

const PULSE_MS = 1200;
const TAB_PULSE_MS = 900;

/** "Sin conexión con Vocify · Lo que ves es de hace N s": what is on screen stays, nothing is invented. */
function OfflineLine({ since, copy }: { since: number | null; copy: LiveCopy }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (since === null) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [since]);
  if (since === null) return null;
  return (
    <div className="mb-2 flex items-start gap-2 rounded-xl bg-warning/10 px-3 py-2" role="status">
      <Info className="mt-0.5 h-3 w-3 shrink-0 text-warning" />
      <div className="min-w-0 text-[12px]">
        <p className="font-medium text-foreground">{copy.offline}</p>
        <p className="text-muted-foreground">{copy.offlineAge(Math.max(0, Math.round((now - since) / 1000)))}</p>
      </div>
    </div>
  );
}

function BarButton({ label, tip, on, disabled, onClick, children }: { label: string; tip: string; on: boolean; disabled: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex">
          <Button
            type="button"
            variant="secondary"
            size="text"
            disabled={disabled}
            aria-pressed={on}
            onClick={onClick}
            className={cn("h-8 rounded-full px-2.5 text-[12px]", on && "bg-beige/15 text-beige hover:bg-beige/20")}
          >
            <span className="text-beige [&_svg]:h-3 [&_svg]:w-3">{children}</span>
            {label}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent side="top">{tip}</TooltipContent>
    </Tooltip>
  );
}

/**
 * The dashboard's live view (spec 2026-10-16, "UI specification"): the island's three tabs and its bar, with more room.
 * Pull, not push: nothing changes tab on its own; attention is a count on a tab and one soft pulse.
 */
export function LiveBrainPanel({
  brain,
  copy,
  helpOn,
  onHelpChange,
  typeName,
  transcript,
}: {
  brain: LiveBrain;
  copy: LiveCopy;
  helpOn: boolean;
  onHelpChange: (on: boolean) => void;
  typeName: string | null;
  transcript: ReactNode;
}) {
  const [tab, setTab] = useState<Tab>("transcript");
  const [peek, setPeek] = useState<Peek>(null);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const [pulseId, setPulseId] = useState<string | null>(null);
  const [pulseNow, setPulseNow] = useState(false);
  const [pulseTab, setPulseTab] = useState<Tab | null>(null);

  const pv = useMemo(() => progressView(brain.state.progress, brain.playbook, copy.goal), [brain.state.progress, brain.playbook, copy.goal]);
  const points = useMemo(() => pointsView(brain.state.points, expanded), [brain.state.points, expanded]);
  const helpCount = helpOn ? points.waiting.length : 0;
  const doCount = helpOn ? pv.picks : 0;

  // A count that goes up pulses its tab once; one that goes down does nothing.
  const lastCounts = useRef({ help: helpCount, conversation: doCount });
  useEffect(() => {
    const before = lastCounts.current;
    lastCounts.current = { help: helpCount, conversation: doCount };
    const up: Tab | null = helpCount > before.help ? "help" : doCount > before.conversation ? "conversation" : null;
    if (!up) return;
    setPulseTab(up);
    const timer = window.setTimeout(() => setPulseTab(null), TAB_PULSE_MS);
    return () => window.clearTimeout(timer);
  }, [helpCount, doCount]);

  const pulse = (id: string) => {
    setPulseId(id);
    window.setTimeout(() => setPulseId((current) => (current === id ? null : current)), PULSE_MS);
  };

  // Responder's answer: a point already up or being read is shown (pulse in Ayuda, slid up elsewhere); nothing says so.
  const handled = useRef(0);
  const responder = brain.asks.responder;
  useEffect(() => {
    if (!responder || responder.status === "reading" || handled.current === responder.seq) return;
    handled.current = responder.seq;
    if (responder.status === "found" && responder.point_id) {
      if (tab === "help") {
        setPeek(null);
        pulse(responder.point_id);
      } else {
        setPeek({ kind: "point", id: responder.point_id });
      }
    } else {
      setPeek({ kind: "nothing" });
    }
  }, [responder, tab]);
  // A reading that failed leaves no ask: its peek would wait forever.
  useEffect(() => {
    if (!responder) setPeek((p) => (p?.kind === "responder" ? null : p));
  }, [responder]);

  const switchTab = (next: Tab) => {
    setTab(next);
    // The tab that owns an object shows it: its peek would be a copy.
    setPeek((p) => (p && ((next === "help" && (p.kind === "point" || p.kind === "responder" || p.kind === "nothing")) || (next === "conversation" && p.kind === "now")) ? null : p));
  };

  const askRespond = () => {
    brain.responder();
    setPeek({ kind: "responder" });
  };
  const askNow = () => {
    if (tab === "conversation") {
      brain.preguntar();
      setPulseNow(true);
      window.setTimeout(() => setPulseNow(false), PULSE_MS);
      return;
    }
    if (peek?.kind === "now") return setPeek(null);
    brain.preguntar();
    setPeek({ kind: "now" });
  };
  const askRecap = () => {
    if (peek?.kind === "recap") {
      brain.clearAsk("recap");
      return setPeek(null);
    }
    void brain.resumen();
    setPeek({ kind: "recap" });
  };
  const closePeek = () => {
    if (peek?.kind === "recap") brain.clearAsk("recap");
    setPeek(null);
  };

  // The chip: what waits outside the open tab.
  const newestOpen = points.waiting[points.waiting.length - 1];
  const chip =
    helpOn && points.waiting.length && tab !== "help"
      ? { lead: copy.chipWaiting(points.waiting.length), tip: points.waiting.map((p: { title: string }) => p.title).join(" · "), go: () => setPeek({ kind: "point", id: newestOpen.id }) }
      : helpOn && tab !== "conversation" && pv.now && pv.picks > 0
        ? { lead: copy.chipMissing, tip: pv.falta.slice(0, 3).map((f) => f.label).join(" · "), go: () => setPeek({ kind: "now" }) }
        : null;

  const offline = <OfflineLine since={brain.offlineSince} copy={copy} />;
  const peekPoint = peek?.kind === "point" ? brain.state.points.find((p: { id: string }) => p.id === peek.id) : null;
  const recap = brain.asks.recap;
  const tabs: { id: Tab; label: string; icon: ReactNode; count: number; tip: string }[] = [
    { id: "transcript", label: copy.tabs.transcript, icon: <MessageSquareText className="h-3 w-3" />, count: 0, tip: copy.tabs.transcript },
    { id: "help", label: copy.tabs.help, icon: <Sparkles className="h-3 w-3" />, count: helpCount, tip: `${copy.tabs.help} · ${copy.tabCountHelp(helpCount)}` },
    { id: "conversation", label: copy.tabs.conversation, icon: <ListChecks className="h-3 w-3" />, count: doCount, tip: `${copy.tabs.conversation} · ${copy.tabCountDo(doCount)}` },
  ];
  const pane = (id: Tab) =>
    cn(
      "absolute inset-0 transition-[opacity,transform] duration-200 ease-out motion-reduce:transition-none",
      tab === id ? "translate-y-0 opacity-100" : "pointer-events-none invisible translate-y-[3px] opacity-0",
    );

  return (
    <TooltipProvider delayDuration={300}>
      <section
        aria-label={copy.title}
        className="flex h-[calc(100dvh-9rem)] max-h-[720px] min-h-[460px] flex-col overflow-hidden rounded-2xl border border-border/70 bg-card"
      >
        <div className="flex items-center justify-between gap-3 px-4 pb-1 pt-3">
          <div className="flex min-w-0 items-center gap-2">
            <span className="text-[15px] tracking-tight text-foreground">{copy.title}</span>
            {typeName ? <span className="min-w-0 truncate rounded-md bg-beige/10 px-1.5 py-px text-[11px] font-medium text-beige">{typeName}</span> : null}
          </div>
          <Switch checked={helpOn} onCheckedChange={onHelpChange} aria-label={copy.switchLabel} />
        </div>

        <Tabs value={tab} onValueChange={(v) => switchTab(v as Tab)} className="px-3 pb-2 pt-1">
          <TabsList className={cn(THEME_TOKENS.interaction.segmentList, "grid w-full grid-cols-3 flex-nowrap gap-0.5 rounded-full p-0.5")}>
            {tabs.map((item) => (
              <Tooltip key={item.id}>
                <TooltipTrigger asChild>
                  <TabsTrigger
                    value={item.id}
                    className={cn(THEME_TOKENS.interaction.segmentTab, "relative h-7 justify-center gap-1.5 border-b-0 px-2 text-[12px]")}
                  >
                    {pulseTab === item.id ? (
                      <span aria-hidden className="pointer-events-none absolute -inset-x-[3px] -inset-y-[2px] rounded-full ring-2 ring-beige/50 animate-ping [animation-iteration-count:1] motion-reduce:hidden" />
                    ) : null}
                    {item.icon}
                    {item.label}
                    {item.count ? (
                      <span
                        className={cn(
                          "flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[10px] font-semibold tabular-nums",
                          tab === item.id ? "bg-beige text-cream" : "bg-secondary text-foreground",
                        )}
                      >
                        {item.count}
                      </span>
                    ) : null}
                  </TabsTrigger>
                </TooltipTrigger>
                <TooltipContent side="top">{item.tip}</TooltipContent>
              </Tooltip>
            ))}
          </TabsList>
        </Tabs>
        <div className="h-px bg-border/60" />

        <div className="relative min-h-0 flex-1">
          <div role="tabpanel" aria-label={copy.tabs.transcript} aria-hidden={tab !== "transcript"} className={pane("transcript")}>
            <div className="h-full [&>div]:h-full">{transcript}</div>
          </div>
          <div role="tabpanel" aria-label={copy.tabs.help} aria-hidden={tab !== "help"} className={pane("help")}>
            <AyudaPane
              brain={brain}
              copy={copy}
              helpOn={helpOn}
              pulseId={pulseId}
              expanded={expanded}
              onExpand={(id) => setExpanded((set) => new Set([...set, id]))}
              offline={offline}
            />
          </div>
          <div role="tabpanel" aria-label={copy.tabs.conversation} aria-hidden={tab !== "conversation"} className={pane("conversation")}>
            <ConversacionPane
              view={pv}
              copy={copy}
              helpOn={helpOn}
              typeName={typeName}
              pulseNow={pulseNow}
              onTick={brain.tick}
              onUntick={brain.untick}
              offline={offline}
            />
          </div>

          {peek ? (
            <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10">
              <div className="pointer-events-none h-6 bg-gradient-to-t from-card/95 to-transparent" aria-hidden />
              <div className="pointer-events-none bg-card/95 px-2.5 pb-2">
                <div
                  className="pointer-events-auto relative max-h-[260px] overflow-y-auto rounded-xl border border-border/70 bg-card p-2 shadow-medium animate-in fade-in slide-in-from-bottom-3 duration-300 motion-reduce:animate-none [scrollbar-width:none]"
                  role="region"
                  aria-live="polite"
                >
                  <button
                    type="button"
                    onClick={closePeek}
                    aria-label={copy.closePeek}
                    className="absolute right-2.5 top-2.5 z-10 flex h-[18px] w-[18px] items-center justify-center rounded-full text-muted-foreground transition-colors duration-150 hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60 motion-reduce:transition-none"
                  >
                    <X className="h-3 w-3" />
                  </button>
                  {peek.kind === "point" && peekPoint ? (
                    peekPoint.outcome === "open" ? (
                      <PointCard point={peekPoint} copy={copy} enter={false} hideDismiss />
                    ) : (
                      <p className="pr-6 text-[13px] text-foreground">
                        ✓ {pointTag(copy, peekPoint)} · {copy.outcomes[peekPoint.outcome]}
                      </p>
                    )
                  ) : null}
                  {peek.kind === "responder" ? (
                    <p className="flex items-center gap-2 py-1 pr-6 text-[12px] text-muted-foreground">
                      {copy.readingMinute}
                      <Dots />
                    </p>
                  ) : null}
                  {peek.kind === "nothing" ? <p className="py-1 pr-6 text-[13px] text-muted-foreground">{copy.nothingFound}</p> : null}
                  {peek.kind === "now" ? (
                    pv.now ? (
                      <AhoraCard now={pv.now} copy={copy} clearOfClose onTick={() => brain.tick(pv.now!.id, pv.now!.kind)} />
                    ) : (
                      <p className="py-1 pr-6 text-[13px] text-muted-foreground">{copy.noPlaybookBody}</p>
                    )
                  ) : null}
                  {peek.kind === "recap" ? (
                    <div className="space-y-2 rounded-xl bg-beige/10 px-3.5 py-3 ring-1 ring-beige/25">
                      <p className="pr-6 text-[11px] font-semibold text-beige">{copy.recapTitle(clock(recap?.up_to_t ?? 0))}</p>
                      {!recap || recap.status === "reading" ? (
                        <p className="flex items-center gap-2 text-[12px] text-muted-foreground">
                          {copy.recapReading}
                          <Dots />
                        </p>
                      ) : recap.lines.length ? (
                        <>
                          <ul className="space-y-1.5">
                            {recap.lines.map((line, index) => (
                              <li
                                key={line}
                                style={{ animationDelay: `${index * 60}ms` }}
                                className="flex items-start gap-2 text-[13px] leading-snug text-foreground animate-in fade-in slide-in-from-bottom-1 fill-mode-both duration-200 motion-reduce:animate-none"
                              >
                                <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-beige" aria-hidden />
                                {line}
                              </li>
                            ))}
                          </ul>
                          {recap.unknown.length ? <p className="text-[12px] text-muted-foreground">{copy.recapUnknown(recap.unknown.join(", "))}</p> : null}
                        </>
                      ) : (
                        <p className="text-[13px] text-muted-foreground">{copy.recapEmpty}</p>
                      )}
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          ) : null}
        </div>

        <div className="flex h-12 shrink-0 items-center gap-1 border-t border-border/60 px-3">
          <BarButton
            label={copy.bar.respond}
            tip={copy.barTips.respond}
            on={peek?.kind === "responder" || peek?.kind === "point" || peek?.kind === "nothing"}
            disabled={!helpOn}
            onClick={askRespond}
          >
            <ShieldCheck />
          </BarButton>
          <BarButton label={copy.bar.ask} tip={copy.barTips.ask} on={peek?.kind === "now"} disabled={!helpOn || !pv.hasPlaybook} onClick={askNow}>
            <MessageCircleQuestion />
          </BarButton>
          <BarButton label={copy.bar.recap} tip={copy.barTips.recap} on={peek?.kind === "recap"} disabled={!helpOn} onClick={askRecap}>
            <History />
          </BarButton>
          {chip ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={chip.go}
                  className="ml-auto flex h-7 shrink-0 items-center gap-1.5 rounded-full bg-beige/10 pl-2.5 pr-2 text-[12px] font-semibold text-beige ring-1 ring-beige/25 transition-colors duration-150 hover:bg-beige/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60 animate-in fade-in duration-200 motion-reduce:animate-none motion-reduce:transition-none"
                >
                  <span className="h-[5px] w-[5px] rounded-full bg-beige" aria-hidden />
                  {chip.lead}
                  <ChevronRight className="h-2.5 w-2.5" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="top" className="max-w-xs">
                {chip.tip}
              </TooltipContent>
            </Tooltip>
          ) : null}
        </div>
      </section>
    </TooltipProvider>
  );
}
