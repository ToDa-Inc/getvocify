import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ClockCounterClockwise, Plus } from "@phosphor-icons/react";
import { ConfirmAction } from "@/components/ui/confirm-action";
import { IconAction } from "@/components/ui/icon-action";
import AskThread from "@/features/ask/components/AskThread";
import HistoryList from "@/features/ask/components/HistoryList";
import { useAuth } from "@/features/auth";
import { getUserDisplayName } from "@/features/auth/types";
import { useLanguage } from "@/lib/i18n";
import { isManagerRole, usesRepHome } from "@/lib/nav";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";
import { useHomeChat } from "../hooks/useHomeChat";
import { HomeComposer, type HomeComposerHandle } from "./HomeComposer";
import { LatestInteractions } from "./LatestInteractions";
import { RepRail } from "./RepRail";
import { SignalsRail } from "./SignalsRail";

const GLIDE = { duration: 200, easing: "cubic-bezier(0.16, 1, 0.3, 1)" };

function greetingKey(hour: number) {
  if (hour >= 5 && hour < 12) return "greetingMorning" as const;
  if (hour >= 12 && hour < 20) return "greetingAfternoon" as const;
  return "greetingEvening" as const;
}

const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * Inicio (/dashboard), one page for every role: ask on top, the latest interactions under it, the
 * day (rep) or the team (Head of Sales) on the side. Sending a question turns the main column into
 * the conversation; Esc or "Nuevo" brings the home back. Only the thread and the feed scroll.
 */
export function InicioPage() {
  const { t } = useLanguage();
  const p = t.product;
  const { user } = useAuth();
  const manager = isManagerRole(user?.company?.role);
  const chat = useHomeChat();
  const { conversation } = chat;
  const inChat = chat.mode === "chat";
  const [showHistory, setShowHistory] = useState(false);
  // Leaving the chat (Esc included) closes the history with it.
  const historyOpen = inChat && showHistory;
  useEffect(() => {
    if (!inChat) setShowHistory(false);
  }, [inChat]);
  const [clearing, setClearing] = useState(false);
  // A phone keeps its keyboard down until the person taps the field.
  const [wide] = useState(() => window.matchMedia("(min-width: 768px)").matches);
  const composer = useRef<HomeComposerHandle>(null);
  const threadBox = useRef<HTMLDivElement>(null);
  const glideFrom = useRef<DOMRect | null>(null);

  const now = new Date();
  const name = user?.fullName?.trim().split(/\s+/)[0] || (user ? getUserDisplayName(user) : "");
  const date = new Intl.DateTimeFormat(p.hourLocale, { weekday: "long", day: "numeric", month: "long" }).format(now);

  const send = (text: string) => {
    glideFrom.current = composer.current?.rect() ?? null;
    chat.send(text);
  };

  const goHome = () => chat.reset();

  // A signal's question lands in the home composer to edit or send, never sent on its own.
  const prefill = (question: string) => {
    if (inChat) goHome();
    composer.current?.prefill(question);
  };

  // A rep without the rep workspace has no Hoy to condense (its reads and /dashboard/today 404
  // server-side): composer and feed only.
  const rail = manager ? <SignalsRail onAsk={prefill} /> : usesRepHome(user?.company) ? <RepRail /> : null;

  // The composer glides from the middle of the page to the bottom of the thread, which fades in.
  useLayoutEffect(() => {
    const from = glideFrom.current;
    glideFrom.current = null;
    if (!inChat || !from || reducedMotion()) return;
    const box = threadBox.current;
    const field = box?.querySelector("form");
    if (!box || !field) return;
    const to = field.getBoundingClientRect();
    box.animate([{ opacity: 0 }, { opacity: 1 }], GLIDE);
    field.animate([{ transform: `translateY(${from.top - to.top}px)` }, { transform: "none" }], GLIDE);
  }, [inChat]);

  return (
    <div className={cn("flex flex-col gap-6 md:h-full md:flex-row", inChat && "h-full")}>
      <div className={cn("relative flex min-w-0 flex-col md:min-h-0 md:flex-1", inChat && "min-h-0 flex-1")}>
        <div
          aria-hidden={inChat || undefined}
          className={cn(
            "flex flex-col gap-6 transition-opacity duration-200 motion-reduce:transition-none md:min-h-0 md:flex-1",
            inChat && "pointer-events-none invisible absolute inset-0 overflow-hidden opacity-0",
          )}
        >
          <div className="mx-auto w-full max-w-[680px] space-y-5 pt-2 xl:pt-6">
            <h1 className="text-center text-[1.5rem] font-normal leading-tight tracking-tight text-foreground xl:text-[1.75rem]">
              {p.home[greetingKey(now.getHours())].replace("{name}", name)}
              {/* A narrow column keeps the greeting on one line; the date is the first thing to go. */}
              <span className="ml-2.5 hidden whitespace-nowrap text-[15px] tracking-normal text-muted-foreground xl:inline">{date}</span>
            </h1>
            <HomeComposer ref={composer} onSend={send} autoFocus={wide && !inChat} />
          </div>
          <LatestInteractions manager={manager} />
        </div>

        {inChat ? (
          <div className="flex min-h-0 flex-1 flex-col">
            <div className="flex shrink-0 justify-end gap-0.5">
              <IconAction
                label={p.askHistory}
                onClick={() => {
                  const next = !historyOpen;
                  setShowHistory(next);
                  if (next) void conversation.loadHistory();
                }}
              >
                <ClockCounterClockwise size={16} weight={historyOpen ? "fill" : "light"} />
              </IconAction>
              <IconAction label={p.home.newChat} shortcut={p.home.newChatKey} onClick={goHome}>
                <Plus size={16} weight="light" />
              </IconAction>
            </div>
            <div ref={threadBox} className="mx-auto flex min-h-0 w-full max-w-[760px] flex-1 flex-col">
              {historyOpen ? (
                <div className="ask-scroll min-h-0 flex-1 overflow-y-auto px-2 pb-4 pt-2">
                  <HistoryList
                    rows={conversation.history}
                    failed={conversation.historyError}
                    activeId={conversation.conversationId}
                    onOpen={(id) => {
                      setShowHistory(false);
                      void chat.open(id).catch(() => undefined);
                    }}
                    onDelete={(id) => {
                      const current = id === conversation.conversationId;
                      void conversation.deleteConversation(id).then(() => (current ? goHome() : undefined));
                    }}
                    onClearAll={() => setClearing(true)}
                  />
                </div>
              ) : null}
              {/* Kept mounted while the history shows, so a half-typed question survives a peek at it. */}
              <div className={historyOpen ? "hidden" : "min-h-0 flex-1"}>
                <AskThread
                  conversation={conversation}
                  visible={!historyOpen}
                  // In the chat an empty thread is one still being read back from a link.
                  empty={() => (
                    <p role="status" className="ask-shimmer px-1 pt-2 text-[13.5px]">
                      {p.teamLoading}
                    </p>
                  )}
                />
              </div>
            </div>
          </div>
        ) : null}
      </div>

      {rail ? (
        <aside className={cn("md:w-[320px] md:min-h-0 md:shrink-0 md:overflow-y-auto", inChat && "max-md:hidden")}>
          <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-5`}>{rail}</div>
        </aside>
      ) : null}

      <ConfirmAction
        open={clearing}
        onOpenChange={setClearing}
        title={p.askClearAllTitle}
        description={p.askClearAllBody}
        confirmLabel={p.askClearAll}
        cancelLabel={p.cancelAction}
        onConfirm={() => {
          setClearing(false);
          void conversation.clearAll().then(goHome);
        }}
      />
    </div>
  );
}
