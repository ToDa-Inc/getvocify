import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Info, ListChecks, Maximize2, MessageCircleQuestion, MessageSquareReply, Reply, ScrollText, X } from "lucide-react";
import { IconAction } from "@/components/ui/icon-action";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { LiveTranscript } from "@/features/recording/components";
import { clockSeconds, pointSays, progressView } from "@/lib/live-brain";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";
import type { DesktopMeeting } from "../DesktopMeetingProvider";
import type { LiveBrain } from "../assist/useLiveBrain";
import { ConversacionPane } from "./ConversacionPane";
import { clock, type LiveCopy } from "./copy";
import { Dots } from "./PointCard";
import type { LivePoint } from "./types";

/** What covers the transcript, one at a time: the steps, the recap or who the call is with. */
type Pane = "steps" | "recap" | "contact" | null;

/** How long Responder's "nothing to answer" stays. */
const NOTHING_MS = 6000;
/** A card this new is what Responder points at (the island's REWRITE_AFTER_S); after that, Responder asks for the next. */
const JUST_CAME_S = 5;
const FLASH_MS = 1200;

/**
 * The live view in the dashboard's compact window (desktop app): what to say at the top, the conversation under it, and
 * the rep's asks on a rail at the right. The steps, the recap and the contact open over the conversation, one at a time.
 * The window itself goes back to the whole dashboard with the button in its header.
 */
export function CompactLiveView({
  meeting,
  brain,
  copy,
  helpOn,
  typeName,
  onExpand,
}: {
  meeting: DesktopMeeting;
  brain: LiveBrain;
  copy: LiveCopy;
  helpOn: boolean;
  typeName: string | null;
  onExpand: () => void;
}) {
  const [pane, setPane] = useState<Pane>(null);
  const view = useMemo(() => progressView(brain.state.progress, brain.playbook, copy.goal), [brain.state.progress, brain.playbook, copy.goal]);
  const recap = brain.asks.recap;
  const responder = brain.asks.responder;
  const toggle = (next: Exclude<Pane, null>) => setPane((current) => (current === next ? null : next));
  const askRecap = () => {
    if (pane === "recap") return setPane(null);
    void brain.resumen();
    setPane("recap");
  };
  const contactName = brain.contact?.name ?? null;

  // Responder, as on the island: a card that has only just come is the answer (it lights up, it may not have been read);
  // otherwise the brain is asked now for the next move from the conversation, and its card lights up when it comes.
  const [flash, setFlash] = useState<string | null>(null);
  const flashCard = (id: string) => {
    setFlash(id);
    window.setTimeout(() => setFlash((current) => (current === id ? null : current)), FLASH_MS);
  };
  const respond = () => {
    const open = (brain.state.points as LivePoint[]).filter((p) => p.outcome === "open");
    const newest = open[open.length - 1];
    const now = clockSeconds(meeting.elapsed);
    const at = newest ? (typeof (newest as { visible_t?: unknown }).visible_t === "number" ? (newest as { visible_t: number }).visible_t : newest.said_at) : null;
    if (newest && now !== null && at !== null && now - at < JUST_CAME_S && flash !== newest.id) return flashCard(newest.id);
    brain.responder();
  };
  const handled = useRef(0);
  useEffect(() => {
    if (!responder || responder.status !== "found" || !responder.point_id || handled.current === responder.seq) return;
    handled.current = responder.seq;
    flashCard(responder.point_id);
  }, [responder]);

  return (
    <TooltipProvider delayDuration={300}>
      <div className={cn("flex h-dvh flex-col overflow-hidden bg-card", THEME_TOKENS.motion.fadeIn)}>
        <header className="flex h-10 shrink-0 items-center gap-2 border-b border-border/60 pl-3 pr-1.5">
          <span
            className={cn("h-1.5 w-1.5 shrink-0 rounded-full", meeting.paused ? "bg-muted-foreground/50" : "bg-destructive animate-pulse motion-reduce:animate-none")}
            aria-hidden
          />
          <span className="shrink-0 text-[12px] tabular-nums text-foreground">{meeting.paused ? `${copy.compact.paused} · ${meeting.elapsed}` : meeting.elapsed}</span>
          <span className="min-w-0 flex-1 truncate text-[12px] text-muted-foreground">
            {[typeName, contactName].filter(Boolean).join(" · ")}
          </span>
          <IconAction label={copy.compact.expand} onClick={onExpand}>
            <Maximize2 />
          </IconAction>
        </header>

        <section aria-label={copy.compact.say} className="flex max-h-[42%] min-h-[88px] shrink-0 flex-col border-b border-border/60">
          {helpOn ? <SayList brain={brain} copy={copy} responder={responder} flashId={flash} /> : <p className="px-3.5 py-3 text-[12px] text-muted-foreground">{copy.off}</p>}
        </section>

        <div className="relative min-h-0 flex-1 overflow-hidden">
          {/* The transcript's own box takes the height of this one: it scrolls and keeps the newest line in view. */}
          <div className="absolute inset-0 [&>div]:h-full">
            <LiveTranscript
              finalTranscript=""
              interimTranscript=""
              turns={meeting.turns}
              speaking={meeting.paused ? undefined : { rep: meeting.speaking.you, prospect: meeting.speaking.them }}
              isActive={meeting.phase === "live"}
              listeningHint={copy.transcriptEmpty}
              className="h-full max-h-none rounded-none border-0 bg-transparent px-3 py-2 shadow-none ring-0"
            />
          </div>
          {pane ? (
            <Over
              title={pane === "steps" ? copy.compact.steps : pane === "recap" ? copy.bar.recap : copy.compact.contact}
              copy={copy}
              onClose={() => setPane(null)}
            >
              {pane === "steps" ? (
                <ConversacionPane
                  view={view}
                  copy={copy}
                  helpOn={helpOn}
                  typeName={typeName}
                  pulseNow={false}
                  onTick={brain.tick}
                  onUntick={brain.untick}
                  offline={null}
                />
              ) : pane === "recap" ? (
                <Recap recap={recap} copy={copy} />
              ) : (
                <Contact contact={brain.contact} copy={copy} />
              )}
            </Over>
          ) : null}
        </div>

        {/* The island's bar, in its order: Responder, Resumen, Pasos (no count: a live "2/6" reads as a score of the
            rep), and who the call is with at the right. Each opens over the transcript; a second tap closes it. */}
        <nav aria-label={copy.title} className="flex h-12 shrink-0 items-center gap-1.5 border-t border-border/60 px-2.5">
          <BarAction label={copy.bar.respond} tip={copy.barTips.respond} pending={responder?.status === "reading"} disabled={!helpOn} onClick={respond}>
            <MessageSquareReply />
          </BarAction>
          <BarAction label={copy.bar.recap} tip={copy.barTips.recap} on={pane === "recap"} disabled={!helpOn} onClick={askRecap}>
            <ScrollText />
          </BarAction>
          {view.hasPlaybook ? (
            <BarAction label={copy.compact.steps} tip={copy.compact.stepsTip(view.done, view.total)} on={pane === "steps"} onClick={() => toggle("steps")}>
              <ListChecks />
            </BarAction>
          ) : null}
          <div className="flex-1" />
          {contactName ? (
            <BarAction label={contactName.split(" ")[0]} tip={contactName} on={pane === "contact"} onClick={() => toggle("contact")}>
              <span className="flex h-4 w-4 items-center justify-center rounded-full bg-secondary text-[9px] font-semibold uppercase text-foreground">
                {contactName.trim().charAt(0)}
              </span>
            </BarAction>
          ) : null}
        </nav>
      </div>
    </TooltipProvider>
  );
}

/** A button of the bar: its icon and its name (an icon alone did not say what it does), the longer reason on hover.
 * Open: a soft beige, as on the island. */
function BarAction({
  label,
  tip,
  on = false,
  pending = false,
  disabled = false,
  onClick,
  children,
}: {
  label: string;
  tip: string;
  on?: boolean;
  pending?: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-pressed={on}
          aria-label={tip}
          disabled={disabled || pending}
          onClick={onClick}
          className={cn(
            "inline-flex h-8 min-w-0 items-center gap-1.5 rounded-full bg-secondary/60 px-3 text-[12px] font-medium text-foreground transition-colors duration-150",
            "hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60",
            "disabled:pointer-events-none disabled:opacity-50 motion-reduce:transition-none [&_svg]:h-3.5 [&_svg]:w-3.5 [&_svg]:shrink-0 [&_svg]:stroke-[1.5] [&_svg]:text-beige",
            on && "bg-beige/15 text-beige hover:bg-beige/20",
          )}
        >
          {pending ? <VocifySpinner size={12} /> : children}
          <span className="truncate">{label}</span>
        </button>
      </TooltipTrigger>
      <TooltipContent side="top">{tip}</TooltipContent>
    </Tooltip>
  );
}

/** Qué decir, like a chat (the island's recipe): every card in the order it came, the newest at the bottom; what is still
 * open is bright, what was dealt with fades where it is. It follows the newest unless the rep scrolled up to read.
 * Responder with nothing to answer says so for a moment, with the next thing to find out. */
function SayList({ brain, copy, responder, flashId }: { brain: LiveBrain; copy: LiveCopy; responder: LiveBrain["asks"]["responder"]; flashId: string | null }) {
  const ref = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const points = brain.state.points as LivePoint[];
  const [nothing, setNothing] = useState<{ seq: number; question: string | null } | null>(null);

  useEffect(() => {
    if (!responder || responder.status !== "nothing") return;
    setNothing({ seq: responder.seq, question: responder.next?.question ?? null });
    const timer = window.setTimeout(() => setNothing((n) => (n?.seq === responder.seq ? null : n)), NOTHING_MS);
    return () => window.clearTimeout(timer);
  }, [responder]);

  useEffect(() => {
    if (flashId) ref.current?.querySelector(`[data-point="${CSS.escape(flashId)}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [flashId]);
  const signature = `${points.map((p) => `${p.id}:${p.outcome}`).join(",")}|${brain.drafts.length}|${nothing?.seq ?? ""}`;
  useEffect(() => {
    const box = ref.current;
    if (box && follow.current) box.scrollTo({ top: box.scrollHeight, behavior: "smooth" });
  }, [signature]);

  if (!points.length && !brain.drafts.length && !nothing) {
    return <p className="px-3.5 py-3 text-[12px] text-muted-foreground">{copy.compact.sayEmpty}</p>;
  }
  return (
    <div
      ref={ref}
      onScroll={(event) => {
        const box = event.currentTarget;
        follow.current = box.scrollHeight - box.clientHeight - box.scrollTop < 12;
      }}
      className="flex min-h-0 flex-col gap-1.5 overflow-y-auto px-3 py-2.5"
    >
      {brain.offlineSince !== null ? <p className="text-[11px] text-warning">{copy.offline}</p> : null}
      {points.map((point) => (
        <SayCard key={point.id} point={point} copy={copy} flash={flashId === point.id} onDismiss={() => brain.dismiss(point.id)} />
      ))}
      {brain.drafts.map((draft, index) => (
        <div key={`draft-${index}`} className="flex flex-col gap-0.5 rounded-xl bg-secondary/60 px-3 py-2">
          <Said kind="answer" label={copy.compact.preparing} words={draft.title} />
          {draft.say ? <p className="text-[14px] font-medium leading-snug text-foreground">{draft.say}</p> : <Dots />}
        </div>
      ))}
      {nothing ? (
        <div className="flex flex-col gap-0.5 rounded-xl px-3 py-2 ring-1 ring-inset ring-border">
          <p className="text-[11.5px] text-muted-foreground">{brain.cardMode ? copy.compact.nothingNew : copy.nothingFound}</p>
          {nothing.question ? <p className="text-[14px] leading-snug text-foreground/85">{nothing.question}</p> : null}
        </div>
      ) : null}
    </div>
  );
}

type SayKind = "answer" | "unknown" | "explore";
const KIND_ICON: Record<SayKind, typeof Reply> = { answer: Reply, unknown: Info, explore: MessageCircleQuestion };
const KIND_TONE: Record<SayKind, string> = { answer: "text-beige", unknown: "text-warning", explore: "text-muted-foreground" };

/** The first line of a card: what kind of help it is (always in the same place) and their words. */
function Said({ kind, label, words, tip }: { kind: SayKind; label: string; words: string | null; tip?: string | null }) {
  const Icon = KIND_ICON[kind];
  const tag = (
    <span className={cn("inline-flex shrink-0 items-center gap-1 text-[11px] font-semibold", KIND_TONE[kind])}>
      <Icon className="h-3 w-3" strokeWidth={1.5} />
      {label}
    </span>
  );
  return (
    <div className="flex min-w-0 items-center gap-1.5 pr-5">
      {tip ? (
        <Tooltip>
          <TooltipTrigger asChild>{tag}</TooltipTrigger>
          <TooltipContent side="top">{tip}</TooltipContent>
        </Tooltip>
      ) : (
        tag
      )}
      {words ? <span className="min-w-0 truncate text-[11.5px] text-muted-foreground">«{words.replace(/^[«"]|[»"]$/g, "")}»</span> : null}
    </div>
  );
}

/** One card: an answer is a full card, an opportunity an outlined one, lighter; dealt with, it fades to two lines. */
function SayCard({ point, copy, flash, onDismiss }: { point: LivePoint; copy: LiveCopy; flash: boolean; onDismiss: () => void }) {
  const live = point.outcome === "open";
  const kind: SayKind = point.kind === "deepen" ? "explore" : !point.answer && point.fallback ? "unknown" : "answer";
  return (
    <div
      data-point={point.id}
      className={cn(
        "group relative flex flex-col gap-0.5 rounded-xl px-3 py-2 transition-opacity duration-300 animate-in fade-in slide-in-from-bottom-1 motion-reduce:animate-none",
        kind === "explore" ? "ring-1 ring-inset ring-border" : "bg-secondary/60",
        kind === "unknown" && "ring-1 ring-inset ring-warning/40",
        !live && "opacity-45",
        flash && "ring-2 ring-beige/50",
      )}
    >
      <Said kind={kind} label={copy.compact.kinds[kind]} words={point.title} tip={point.source?.label ?? null} />
      <p
        className={cn(
          "select-text text-[14px] leading-snug text-foreground",
          kind === "explore" ? "text-foreground/85" : "font-medium",
          !live && "line-clamp-2",
        )}
      >
        {pointSays(point)}
      </p>
      {live ? (
        <button
          type="button"
          onClick={onDismiss}
          aria-label={copy.dismissAria}
          title={copy.dismissAria}
          className="absolute right-1.5 top-1.5 flex h-5 w-5 items-center justify-center rounded-full text-muted-foreground opacity-0 transition-opacity hover:bg-secondary hover:text-foreground focus-visible:opacity-100 group-hover:opacity-100"
        >
          <X className="h-3 w-3" strokeWidth={1.5} />
        </button>
      ) : null}
    </div>
  );
}

/** What opens over the conversation: a sheet from the bottom, as tall as what it holds. */
function Over({ title, copy, onClose, children }: { title: string; copy: LiveCopy; onClose: () => void; children: ReactNode }) {
  return (
    <div
      className={cn(
        "absolute inset-x-0 bottom-0 flex max-h-[85%] flex-col rounded-t-2xl border-t border-border/70 bg-card shadow-medium",
        "animate-in fade-in slide-in-from-bottom-2 duration-200 motion-reduce:animate-none",
      )}
    >
      <div className="flex h-10 shrink-0 items-center justify-between pl-3.5 pr-1.5">
        <span className="text-[13px] font-medium text-foreground">{title}</span>
        <IconAction label={copy.closePeek} onClick={onClose}>
          <X />
        </IconAction>
      </div>
      <div className="relative min-h-0 overflow-y-auto">{children}</div>
    </div>
  );
}

function Recap({ recap, copy }: { recap: LiveBrain["asks"]["recap"]; copy: LiveCopy }) {
  return (
    <div className="space-y-2 px-3.5 pb-4">
      <p className="text-[11px] font-semibold text-beige">{copy.recapTitle(clock(recap?.up_to_t ?? 0))}</p>
      {!recap || recap.status === "reading" ? (
        <p className="flex items-center gap-2 text-[12px] text-muted-foreground">
          {copy.recapReading}
          <Dots />
        </p>
      ) : recap.lines.length ? (
        <>
          <ul className="space-y-1.5">
            {recap.lines.map((line) => (
              <li key={line} className="flex items-start gap-2 text-[13px] leading-snug text-foreground">
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
  );
}

function Contact({ contact, copy }: { contact: LiveBrain["contact"]; copy: LiveCopy }) {
  if (!contact) return null;
  return (
    <div className="space-y-2.5 px-3.5 pb-4">
      <div>
        <p className="text-[14px] font-medium text-foreground">{contact.name}</p>
        {contact.company ? <p className="text-[12px] text-muted-foreground">{contact.company}</p> : null}
      </div>
      {contact.lines.length ? (
        <ul className="space-y-1.5">
          {contact.lines.map((line) => (
            <li key={line} className="flex items-start gap-2 text-[13px] leading-snug text-foreground">
              <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-beige" aria-hidden />
              {line}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-[12px] text-muted-foreground">{copy.compact.contactEmpty}</p>
      )}
    </div>
  );
}
