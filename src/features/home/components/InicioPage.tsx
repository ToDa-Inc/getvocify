import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { History, Plus } from "lucide-react";
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
import { HomeRecordButton } from "./HomeRecordButton";
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
 * Inicio (/dashboard), one page for every role: ask on top, the latest interactions under it. A rep's
 * day sits under the composer as a row of chips; the Admin/Owner's team signals sit on the side. Sending a question turns the main column into
 * the conversation; Esc or "Nuevo" brings the home back. At home the page scrolls as one piece (the
 * side column stays put); in the chat only the thread scrolls.
 */
export function InicioPage() {
  const { t } = useLanguage();
  const p = t.product;
  const { user } = useAuth();
  const manager = isManagerRole(user?.company?.role);
  const chat = useHomeChat();
  const { conversation } = chat;
  const inChat = chat.mode === "chat";
  // The history opens from the home too (the toolbar is always there), not only from inside a chat.
  const [historyOpen, setShowHistory] = useState(false);
  // Leaving the chat (Esc included) closes the history with it.
  const wasInChat = useRef(inChat);
  useEffect(() => {
    if (wasInChat.current && !inChat) setShowHistory(false);
    wasInChat.current = inChat;
  }, [inChat]);
  // At home, Esc closes an open history (in the chat, Esc already leaves the chat and closes it with it).
  useEffect(() => {
    if (inChat || !historyOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented || event.isComposing) return;
      setShowHistory(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [inChat, historyOpen]);
  const toggleHistory = () => {
    const next = !historyOpen;
    setShowHistory(next);
    if (next) void conversation.loadHistory();
  };
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

  const goHome = () => {
    setShowHistory(false);
    chat.reset();
  };

  // A signal's question lands in the home composer to edit or send, never sent on its own.
  const prefill = (question: string) => {
    if (inChat) goHome();
    composer.current?.prefill(question);
  };

  // A rep without the rep workspace has no Hoy to condense (its reads and /dashboard/today 404
  // server-side): composer and feed only.
  const repDay = !manager && usesRepHome(user?.company);
  const rail = manager ? <SignalsRail onAsk={prefill} /> : null;

  const history = (
    <HistoryList
      rows={conversation.history}
      failed={conversation.historyError}
      activeId={inChat ? conversation.conversationId : null}
      onOpen={(id) => {
        setShowHistory(false);
        void chat.open(id).catch(() => undefined);
      }}
      onDelete={(id) => {
        const current = inChat && id === conversation.conversationId;
        void conversation.deleteConversation(id).then(() => (current ? goHome() : undefined));
      }}
      onClearAll={() => setClearing(true)}
    />
  );

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
    <div className={cn("flex flex-col gap-6 md:flex-row md:items-start", inChat && "h-full md:items-stretch")}>
      <div className={cn("relative flex min-w-0 flex-col md:flex-1", inChat && "min-h-0 flex-1")}>
        <div className="relative z-10 flex shrink-0 items-center justify-end gap-0.5">
          <HomeRecordButton />
          <IconAction label={p.askHistory} onClick={toggleHistory}>
            <History size={16} strokeWidth={historyOpen ? 2.25 : 1.5} />
          </IconAction>
          {inChat ? (
            <IconAction label={p.home.newChat} shortcut={p.home.newChatKey} onClick={goHome}>
              <Plus size={16} strokeWidth={1.5} />
            </IconAction>
          ) : null}
        </div>
        <div
          aria-hidden={inChat || historyOpen || undefined}
          className={cn(
            "flex flex-col gap-8 transition-opacity duration-200 motion-reduce:transition-none",
            (inChat || historyOpen) && "pointer-events-none invisible absolute inset-0 overflow-hidden opacity-0",
          )}
        >
          <div className="mx-auto w-full max-w-[680px] space-y-5 pt-2 xl:pt-6">
            <h1 className="text-center text-[1.5rem] font-normal leading-tight tracking-tight text-foreground xl:text-[1.75rem]">
              {p.home[greetingKey(now.getHours())].replace("{name}", name)}
              {/* A narrow column keeps the greeting on one line; the date is the first thing to go. */}
              <span className="ml-2.5 hidden whitespace-nowrap text-[15px] tracking-normal text-muted-foreground xl:inline">{date}</span>
            </h1>
            <HomeComposer ref={composer} onSend={send} autoFocus={wide && !inChat} />
            {repDay ? <RepRail /> : null}
          </div>
          <LatestInteractions manager={manager} />
        </div>

        {inChat ? (
          <div className="flex min-h-0 flex-1 flex-col">
            <div ref={threadBox} className="mx-auto flex min-h-0 w-full max-w-[760px] flex-1 flex-col">
              {historyOpen ? <div className="ask-scroll min-h-0 flex-1 overflow-y-auto px-2 pb-4 pt-2">{history}</div> : null}
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
        ) : historyOpen ? (
          <div className="mx-auto w-full max-w-[760px] px-2 pb-4 pt-2">{history}</div>
        ) : null}
      </div>

      {rail ? (
        <aside className={cn("md:sticky md:top-0 md:w-[320px] md:shrink-0", inChat && "max-md:hidden md:max-h-full md:overflow-y-auto")}>
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
