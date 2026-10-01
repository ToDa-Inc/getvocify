import { useEffect, useRef, useState } from "react";
import { Calendar, ChevronDown, ChevronUp, Copy, Minus, Pause, Play, Search, Square, X } from "lucide-react";
import { toast } from "sonner";
import { LiveTranscript } from "@/features/recording/components";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";
import { getDesktopBridge, TRANSCRIPT_SEARCH_EVENT } from "@/lib/desktop-host";
import { useDesktopMeeting } from "./DesktopMeetingProvider";
import { LiveAssistPanel } from "./assist/LiveAssistPanel";
import { useLiveAssist, useLiveAssistEnabled } from "./assist/useLiveAssist";

const BAR_SHAPE = [0.45, 0.8, 1, 0.65];

/** Granola-style meeting screen: your notes are the page, the conversation floats below. */
export function MeetingLiveView() {
  const meeting = useDesktopMeeting();
  const live = meeting.phase === "live";
  const [transcriptOpen, setTranscriptOpen] = useState(true);
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const transcriptRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const open = () => {
      setTranscriptOpen(true);
      setSearchOpen(true);
    };
    window.addEventListener(TRANSCRIPT_SEARCH_EVENT, open);
    return () => window.removeEventListener(TRANSCRIPT_SEARCH_EVENT, open);
  }, []);

  const closeSearch = () => {
    setSearchOpen(false);
    setQuery("");
  };
  const [assistOn, setAssistOn] = useLiveAssistEnabled();
  const assist = useLiveAssist(meeting.turns, assistOn && live && !meeting.paused);

  // The floating pill shows the same live card while it is open.
  useEffect(() => {
    const card = assist.active;
    getDesktopBridge()?.shell.setState({
      assist: card
        ? { label: card.label, kind: card.kind, stage: card.stage, bridge: card.bridge, sayThis: card.sayThis, thenAsk: card.thenAsk }
        : null,
    });
  }, [assist.active]);
  const [startedAt] = useState(() =>
    new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
  );

  const copyTranscript = async () => {
    const text = meeting.turns
      .map((turn) => {
        const body = [turn.text, turn.pending].filter(Boolean).join(" ");
        return turn.label ? `${turn.label}: ${body}` : body;
      })
      .join("\n\n");
    if (!text.trim()) return;
    try {
      await navigator.clipboard.writeText(text);
      toast.success("Transcript copied");
    } catch {
      toast.error("Couldn't copy the transcript");
    }
  };

  return (
    <div
      className={cn(
        "mx-auto flex max-w-6xl gap-10",
        THEME_TOKENS.motion.fadeIn,
      )}
    >
      <div className="flex min-h-[calc(100dvh-9rem)] min-w-0 max-w-3xl flex-1 flex-col">
        <header className="pt-2">
          <h1 className={THEME_TOKENS.typography.pageTitle}>
            Meeting{" "}
            <span className={THEME_TOKENS.typography.accentTitle}>notes</span>
          </h1>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Chip>
              <Calendar className="h-3.5 w-3.5" />
              Today {startedAt}
            </Chip>
            <Chip tone={live ? "live" : "plain"}>
              <span
                className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  live
                    ? "bg-destructive animate-pulse motion-reduce:animate-none"
                    : "bg-muted-foreground/40",
                )}
              />
              <span className="tabular-nums">
                {!live ? "Stopped" : meeting.paused ? `Paused · ${meeting.elapsed}` : meeting.elapsed}
              </span>
            </Chip>
          </div>
        </header>

        <MeetingNotes
          value={meeting.notes}
          onChange={meeting.setNotes}
          readOnly={!live}
        />

        <div className="sticky bottom-4 z-10 mt-6">
          <div
            className={cn(
              THEME_TOKENS.cards.premium,
              THEME_TOKENS.radius.container,
              "overflow-hidden shadow-[0_12px_40px_-14px_hsl(30_30%_12%/0.22)]",
            )}
          >
            <div
              className={cn(
                "grid transition-[grid-template-rows] duration-300 ease-out motion-reduce:transition-none",
                transcriptOpen ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
              )}
            >
              <div className="min-h-0 overflow-hidden">
                <div className="flex items-center justify-between gap-2 border-b border-border/50 px-5 py-2.5">
                  {searchOpen ? (
                    <TranscriptSearch
                      query={query}
                      onQuery={setQuery}
                      onClose={closeSearch}
                      containerRef={transcriptRef}
                      revision={meeting.turns}
                    />
                  ) : (
                    <span className={THEME_TOKENS.typography.capsLabel}>
                      Transcript
                    </span>
                  )}
                  <div className="flex items-center gap-1">
                    {!searchOpen ? (
                      <DockIcon label="Search transcript" onClick={() => setSearchOpen(true)}>
                        <Search className="h-4 w-4" />
                      </DockIcon>
                    ) : null}
                    <DockIcon
                      label="Copy transcript"
                      onClick={() => void copyTranscript()}
                    >
                      <Copy className="h-4 w-4" />
                    </DockIcon>
                    <DockIcon
                      label="Minimize transcript"
                      onClick={() => setTranscriptOpen(false)}
                    >
                      <Minus className="h-4 w-4" />
                    </DockIcon>
                  </div>
                </div>
                <div ref={transcriptRef}>
                <LiveTranscript
                  finalTranscript=""
                  interimTranscript=""
                  turns={meeting.turns}
                  query={query}
                  isActive={live}
                  listeningHint="You and Them appear here as the meeting goes."
                  className="min-h-[200px] max-h-[min(42vh,460px)] rounded-none border-0 bg-transparent px-5 py-4 shadow-none ring-0"
                />
                </div>
              </div>
            </div>

            {live && meeting.warning ? (
              <p
                className="border-t border-border/50 px-5 py-2 text-xs text-muted-foreground"
                aria-live="polite"
              >
                {meeting.warning}
              </p>
            ) : null}

            <div className="flex items-center gap-3 border-t border-border/50 px-4 py-3">
              <LevelBars
                level={
                  live ? Math.max(meeting.levels.you, meeting.levels.them) : 0
                }
              />
              {live ? (
                <TooltipProvider delayDuration={300}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        onClick={meeting.paused ? meeting.resume : meeting.pause}
                        aria-label={meeting.paused ? "Resume recording" : "Pause recording"}
                        className="flex h-9 w-9 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-secondary/70 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/50"
                      >
                        {meeting.paused ? <Play className="h-4 w-4 fill-current" /> : <Pause className="h-4 w-4 fill-current" />}
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top">{meeting.paused ? "Resume recording" : "Pause recording"}</TooltipContent>
                  </Tooltip>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        onClick={() => void meeting.stop()}
                        aria-label="Stop recording"
                        className="group glass-panel flex h-11 w-11 items-center justify-center rounded-full border border-white/70 shadow-md transition-transform duration-200 hover:scale-105 active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige"
                      >
                        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-beige text-cream shadow-xs transition-transform duration-200 group-hover:scale-110">
                          <Square className="h-2.5 w-2.5 fill-current" />
                        </span>
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top">Stop recording</TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              ) : (
                <span className="text-sm text-muted-foreground" role="status">
                  {meeting.phase === "stopping"
                    ? "Finishing transcript…"
                    : "Preparing review…"}
                </span>
              )}
              <div className="ml-auto flex min-w-0 items-center gap-4 text-[13px] text-muted-foreground">
                {!transcriptOpen ? (
                  <DockIcon
                    label="Show transcript"
                    onClick={() => setTranscriptOpen(true)}
                  >
                    <ChevronUp className="h-4 w-4" />
                  </DockIcon>
                ) : null}
              </div>
            </div>
          </div>
        </div>
      </div>
      <div className="hidden w-[300px] shrink-0 lg:block">
        <div className="sticky top-6 pt-3">
          <LiveAssistPanel
            active={assist.active}
          earlier={assist.earlier}
            thinking={assist.thinking}
            enabled={assistOn}
            onEnabledChange={setAssistOn}
          />
        </div>
      </div>
    </div>
  );
}

function Chip({
  children,
  tone = "plain",
}: {
  children: React.ReactNode;
  tone?: "plain" | "live";
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[13px] transition-colors duration-300",
        tone === "live"
          ? "border-beige/20 bg-beige/10 text-beige"
          : "border-border/70 bg-card text-muted-foreground",
      )}
    >
      {children}
    </span>
  );
}

function DockIcon({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="flex h-8 w-8 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-secondary/70 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/50"
    >
      {children}
    </button>
  );
}

/** Four bars that move with whoever is talking; flat when silent. */
function LevelBars({ level }: { level: number }) {
  return (
    <div
      className="flex h-5 w-6 items-center justify-center gap-[3px]"
      aria-hidden
    >
      {BAR_SHAPE.map((shape, index) => (
        <span
          key={index}
          className="w-[3px] rounded-full bg-beige transition-[height] duration-150 ease-out motion-reduce:transition-none"
          style={{
            height: `${Math.max(4, Math.round(20 * shape * (0.2 + 0.8 * level)))}px`,
          }}
        />
      ))}
    </div>
  );
}

/** Borderless notepad that grows with its text, like a document. */
function MeetingNotes({
  value,
  onChange,
  readOnly,
}: {
  value: string;
  onChange: (value: string) => void;
  readOnly: boolean;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);
  useEffect(() => {
    ref.current?.focus({ preventScroll: true });
  }, []);
  return (
    <textarea
      ref={ref}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      readOnly={readOnly}
      rows={6}
      aria-label="Meeting notes"
      placeholder="Write notes… Vocify fills in the rest from the conversation."
      className="mt-8 block w-full flex-1 resize-none overflow-hidden bg-transparent text-[17px] leading-8 text-foreground placeholder:text-muted-foreground/45 outline-none"
    />
  );
}

/**
 * Finds text in the live transcript: highlights every match, jumps between them
 * with Enter / Shift+Enter or the arrows, Esc closes.
 */
function TranscriptSearch({
  query,
  onQuery,
  onClose,
  containerRef,
  revision,
}: {
  query: string;
  onQuery: (query: string) => void;
  onClose: () => void;
  containerRef: React.RefObject<HTMLDivElement>;
  /** Changes whenever the transcript does, so counts stay current. */
  revision: unknown;
}) {
  const [active, setActive] = useState(0);
  const [count, setCount] = useState(0);

  useEffect(() => setActive(0), [query]);

  useEffect(() => {
    const marks = Array.from(
      containerRef.current?.querySelectorAll<HTMLElement>("mark[data-transcript-match]") ?? [],
    );
    setCount(marks.length);
    if (!marks.length) return;
    const index = Math.min(active, marks.length - 1);
    marks.forEach((mark, i) => mark.toggleAttribute("data-active", i === index));
    marks[index].scrollIntoView({ block: "center", behavior: "smooth" });
  }, [active, query, revision, containerRef]);

  const step = (delta: number) => {
    if (!count) return;
    setActive((current) => (current + delta + count) % count);
  };

  return (
    <div className="flex min-w-0 flex-1 items-center gap-2">
      <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      <input
        autoFocus
        value={query}
        onChange={(event) => onQuery(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            step(event.shiftKey ? -1 : 1);
          } else if (event.key === "Escape") {
            onClose();
          }
        }}
        placeholder="Search transcript"
        aria-label="Search transcript"
        className="min-w-0 flex-1 bg-transparent text-[13px] text-foreground placeholder:text-muted-foreground/60 outline-none"
      />
      {query.trim() ? (
        <span className="shrink-0 text-xs tabular-nums text-muted-foreground" aria-live="polite">
          {count ? `${Math.min(active, count - 1) + 1}/${count}` : "0"}
        </span>
      ) : null}
      <DockIcon label="Previous match" onClick={() => step(-1)}>
        <ChevronUp className="h-4 w-4" />
      </DockIcon>
      <DockIcon label="Next match" onClick={() => step(1)}>
        <ChevronDown className="h-4 w-4" />
      </DockIcon>
      <DockIcon label="Close search" onClick={onClose}>
        <X className="h-4 w-4" />
      </DockIcon>
    </div>
  );
}
