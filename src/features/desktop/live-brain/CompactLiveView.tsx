import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ChevronDown, Maximize2, MessageSquareReply, Pause, Play, ScrollText, Square, X } from "lucide-react";
import { IconAction } from "@/components/ui/icon-action";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { LiveTranscript } from "@/features/recording/components";
import { clockSeconds, pointSays, stepsView } from "@/lib/live-brain";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";
import type { DesktopMeeting } from "../DesktopMeetingProvider";
import type { LiveBrain } from "../assist/useLiveBrain";
import { clock, type LiveCopy } from "./copy";
import { Dots } from "./PointCard";
import { quoted, sayKind, SaySlot, SayTag } from "./SaySlot";
import { StepsPane } from "./StepsPane";
import type { LivePoint } from "./types";

/** What opens over the tabs, one at a time: the recap, who the call is with, or the earlier answers. */
type Pane = "recap" | "contact" | "older" | null;
/** Under what to say: the steps (the default: they are what the window is for) or the conversation. */
type Tab = "steps" | "transcript";

/** A card this new is what Responder points at (the island's REWRITE_AFTER_S); after that, Responder asks for the next. */
const JUST_CAME_S = 5;
const FLASH_MS = 1200;

/**
 * The live view in the dashboard's compact window (desktop app): one row of controls, what to say (one answer at a time,
 * SaySlot), then two tabs, Pasos (open by default) and Transcripción, and the rep's asks in a bar at the bottom. The
 * recap, the contact and the earlier answers open over the tabs. The window itself goes back to the whole dashboard with
 * the button in its header.
 */
export function CompactLiveView({
  meeting,
  brain,
  copy,
  helpOn,
  onHelpChange,
  typeName,
  onExpand,
}: {
  meeting: DesktopMeeting;
  brain: LiveBrain;
  copy: LiveCopy;
  helpOn: boolean;
  onHelpChange: (on: boolean) => void;
  typeName: string | null;
  onExpand: () => void;
}) {
  const [pane, setPane] = useState<Pane>(null);
  const [tab, setTab] = useState<Tab>("steps");
  const view = useMemo(() => stepsView(brain.state.progress, brain.playbook, copy.goal), [brain.state.progress, brain.playbook, copy.goal]);
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
        {/* One row: the clock, the call's type (a menu, with live help on or off: set once per call), then pause, stop
            and the whole dashboard. Who the call is with is in the bar at the foot. */}
        <header className="flex h-11 shrink-0 items-center gap-1 border-b border-border/60 pl-3.5 pr-1.5">
          <span
            className={cn("h-1.5 w-1.5 shrink-0 rounded-full", meeting.paused ? "bg-muted-foreground/50" : "bg-destructive animate-pulse motion-reduce:animate-none")}
            aria-hidden
          />
          <span className="shrink-0 pl-1 text-[12px] tabular-nums text-foreground">{meeting.paused ? `${copy.compact.paused} · ${meeting.elapsed}` : meeting.elapsed}</span>
          <div className="flex min-w-0 flex-1 pl-1">
            <TypeMenu meeting={meeting} typeName={typeName} copy={copy} helpOn={helpOn} onHelpChange={onHelpChange} />
          </div>
          <IconAction label={meeting.paused ? copy.compact.resume : copy.compact.pause} onClick={meeting.paused ? meeting.resume : meeting.pause}>
            {meeting.paused ? <Play /> : <Pause />}
          </IconAction>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={() => void meeting.stop()}
                className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full bg-destructive px-2.5 text-[12px] font-medium text-destructive-foreground transition-opacity duration-150 hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-destructive/50"
              >
                <Square className="h-2.5 w-2.5 fill-current" strokeWidth={1.5} />
                {copy.compact.stop}
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom">{copy.compact.stopTip}</TooltipContent>
          </Tooltip>
          <IconAction label={copy.compact.expand} onClick={onExpand}>
            <Maximize2 />
          </IconAction>
        </header>

        {helpOn ? (
          <SaySlot brain={brain} copy={copy} responder={responder} flashId={flash} olderOpen={pane === "older"} onOlder={() => toggle("older")} />
        ) : (
          <section aria-label={copy.compact.say} className="shrink-0 border-b border-border/60">
            <p className="px-3.5 py-3 text-[12px] text-muted-foreground">{copy.off}</p>
          </section>
        )}

        <Tabs value={tab} onValueChange={(next) => setTab(next as Tab)} className="shrink-0 px-2.5 pt-2">
          <TabsList className={cn(THEME_TOKENS.interaction.segmentList, "grid w-full grid-cols-2 flex-nowrap gap-0.5 rounded-full p-0.5")}>
            <TabsTrigger value="steps" className={cn(THEME_TOKENS.interaction.segmentTab, "mb-0 h-7 justify-center px-2 text-[12px]")}>
              {copy.compact.steps}
            </TabsTrigger>
            <TabsTrigger value="transcript" className={cn(THEME_TOKENS.interaction.segmentTab, "mb-0 h-7 justify-center px-2 text-[12px]")}>
              {copy.compact.transcript}
            </TabsTrigger>
          </TabsList>
        </Tabs>

        <div className="relative min-h-0 flex-1 overflow-hidden">
          {/* Both stay mounted, so the transcript keeps its place and the steps their scroll when the rep switches. */}
          <div role="tabpanel" aria-label={copy.compact.steps} hidden={tab !== "steps"} className="absolute inset-0">
            <StepsPane
              view={view}
              copy={copy}
              helpOn={helpOn}
              typeName={typeName}
              ask={brain.asks.step}
              onAsk={(kind, id) => void brain.askStep(kind, id)}
              onTick={brain.tick}
              onUntick={brain.untick}
            />
          </div>
          {/* The transcript's own box takes the height of this one: it scrolls and keeps the newest line in view. */}
          <div role="tabpanel" aria-label={copy.compact.transcript} hidden={tab !== "transcript"} className="absolute inset-0 [&>div]:h-full">
            <LiveTranscript
              finalTranscript=""
              interimTranscript=""
              turns={meeting.turns}
              voices={meeting.voices}
              onVoice={meeting.changeVoices}
              speaking={meeting.paused ? undefined : { rep: meeting.speaking.you, prospect: meeting.speaking.them }}
              isActive={meeting.phase === "live"}
              listeningHint={copy.transcriptEmpty}
              className="h-full max-h-none rounded-none border-0 bg-transparent px-3 py-2 shadow-none ring-0"
            />
          </div>
          {pane ? (
            <Over title={pane === "recap" ? copy.bar.recap : pane === "older" ? copy.compact.older : copy.compact.contact} copy={copy} onClose={() => setPane(null)}>
              {pane === "recap" ? <Recap recap={recap} copy={copy} /> : pane === "older" ? <Older points={brain.state.points as LivePoint[]} copy={copy} /> : <Contact contact={brain.contact} copy={copy} />}
            </Over>
          ) : null}
        </div>

        {/* The island's bar, in its order: Responder, Resumen, and who the call is with at the right. Resumen and the contact
            open over the tabs; a second tap closes them. The steps are a tab now, not a button. */}
        <nav aria-label={copy.title} className="flex h-12 shrink-0 items-center gap-1.5 border-t border-border/60 px-2.5">
          <BarAction label={copy.bar.respond} tip={copy.barTips.respond} pending={responder?.status === "reading"} disabled={!helpOn} onClick={respond}>
            <MessageSquareReply />
          </BarAction>
          <BarAction label={copy.bar.recap} tip={copy.barTips.recap} on={pane === "recap"} disabled={!helpOn} onClick={askRecap}>
            <ScrollText />
          </BarAction>
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

/** The call's type, as the island's menu: the channel when types go by channel, then the channel's types (Vocify's
 * proposal marked), or letting Vocify decide; under them, live help on or off for this call. The chip reads like the
 * island's: "Llamada · Descubrimiento". */
function TypeMenu({
  meeting,
  typeName,
  copy,
  helpOn,
  onHelpChange,
}: {
  meeting: DesktopMeeting;
  typeName: string | null;
  copy: LiveCopy;
  helpOn: boolean;
  onHelpChange: (on: boolean) => void;
}) {
  const menu = meeting.typeMenu;
  const channel = menu?.channel ?? null;
  const channelLabel = channel?.options.find((option) => option.key === channel.selected)?.label ?? null;
  const label = [channelLabel, typeName ?? copy.compact.noType].filter(Boolean).join(" · ");
  return (
    <DropdownMenu>
      <Tooltip>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="inline-flex h-7 min-w-0 max-w-full items-center gap-1 rounded-full px-2 text-[12px] text-foreground transition-colors duration-150 hover:bg-secondary/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60 motion-reduce:transition-none"
            >
              <span className="min-w-0 truncate">{label}</span>
              {menu && meeting.callType.proposed ? <span className="shrink-0 text-[11px] text-muted-foreground">· {copy.compact.proposed}</span> : null}
              <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" strokeWidth={1.5} />
            </button>
          </DropdownMenuTrigger>
        </TooltipTrigger>
        <TooltipContent side="bottom">{copy.compact.typeTip}</TooltipContent>
      </Tooltip>
      <DropdownMenuContent align="start" className="w-64">
        {channel && !channel.fixed ? (
          <>
            <DropdownMenuLabel>{copy.compact.channel}</DropdownMenuLabel>
            <DropdownMenuRadioGroup value={channel.selected} onValueChange={(kind) => meeting.pickChannel(kind as "call" | "meeting")}>
              {channel.options.map((option) => (
                <DropdownMenuRadioItem key={option.key} value={option.key}>{option.label}</DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
            <DropdownMenuSeparator />
          </>
        ) : null}
        {menu ? (
          <>
            <DropdownMenuLabel>{copy.compact.type}</DropdownMenuLabel>
            <DropdownMenuRadioGroup
              value={meeting.callType.proposed ? "" : meeting.callType.key ?? ""}
              onValueChange={(key) => meeting.pickCallType(key || null)}
            >
              {menu.options.map((option) => (
                <DropdownMenuRadioItem key={option.key} value={option.key}>
                  <span className="min-w-0 flex-1 truncate">{option.label}</span>
                  {meeting.callType.proposed && meeting.callType.key === option.key ? (
                    <span className="shrink-0 text-[11px] text-muted-foreground">{copy.compact.proposed}</span>
                  ) : null}
                </DropdownMenuRadioItem>
              ))}
              <DropdownMenuRadioItem value="">{copy.compact.vocifyDecides}</DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
            <DropdownMenuSeparator />
          </>
        ) : null}
        <DropdownMenuCheckboxItem checked={helpOn} onCheckedChange={(on) => onHelpChange(Boolean(on))}>{copy.switchLabel}</DropdownMenuCheckboxItem>
      </DropdownMenuContent>
    </DropdownMenu>
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

/** The earlier answers, newest first: when each came, their words and what it said. */
function Older({ points, copy }: { points: LivePoint[]; copy: LiveCopy }) {
  const open = points.filter((point) => point.outcome === "open");
  const current = open[open.length - 1] ?? null;
  const past = points.filter((point) => point !== current).reverse();
  return (
    <div className="space-y-1.5 px-3 pb-4">
      {past.map((point) => {
        const kind = sayKind(point);
        const at = typeof (point as { visible_t?: unknown }).visible_t === "number" ? (point as { visible_t: number }).visible_t : point.said_at;
        return (
          <div key={point.id} className="rounded-xl bg-secondary/40 px-3 py-2">
            <div className="flex min-w-0 items-center gap-1.5">
              <SayTag kind={kind} label={copy.compact.kinds[kind]} />
              <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">{clock(at)}</span>
              {point.title ? <span className="min-w-0 truncate text-[11.5px] text-muted-foreground">{quoted(point.title)}</span> : null}
            </div>
            <p className="select-text pt-0.5 text-[13px] leading-snug text-foreground/85">{pointSays(point)}</p>
          </div>
        );
      })}
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
