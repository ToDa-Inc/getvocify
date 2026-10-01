import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { ArrowDown } from "@phosphor-icons/react";
import { useAuth } from "@/features/auth";
import { useLanguage } from "@/lib/i18n";
import type { useAskConversation } from "../hooks/useAskConversation";
import Composer from "./Composer";
import TurnView from "./TurnView";

const STICK_PX = 64;

/**
 * The conversation and its composer, without any chrome: it fills its parent's height and scrolls internally.
 * The caller owns the conversation, so the sheet and the home can share one. `empty` renders while there are no
 * turns and gets the thread's own `submit`, so a picked suggestion behaves like a typed message. A caller that hides
 * the thread without unmounting it (to keep the draft) passes `visible`; coming back lands at the end and refocuses.
 */
export default function AskThread({
  conversation,
  empty,
  visible = true,
}: {
  conversation: ReturnType<typeof useAskConversation>;
  empty?: (submit: (text: string) => void) => ReactNode;
  visible?: boolean;
}) {
  const { t } = useLanguage();
  const { user } = useAuth();
  const { thread, busy } = conversation;
  const [draft, setDraft] = useState("");
  const [unread, setUnread] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const shownCount = useRef(0);

  const isTeamReader = user?.company?.role === "owner" || user?.company?.role === "admin";

  function submit(text: string) {
    stick.current = true;
    setUnread(false);
    conversation.send(text);
  }

  function toBottom(behavior: ScrollBehavior) {
    const el = scroller.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior });
  }

  // display:none drops the scroll offset without a scroll event, so coming back re-lands at the end.
  useLayoutEffect(() => {
    if (!visible) return;
    stick.current = true;
    setUnread(false);
    toBottom("auto");
  }, [visible]);

  useEffect(() => {
    const count = thread.messages.length;
    // A restored or opened conversation lands at its end at once; a new turn glides there.
    const jumped = Math.abs(count - shownCount.current) > 2;
    shownCount.current = count;
    if (stick.current || jumped) {
      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      stick.current = true;
      toBottom(reduced || busy || jumped ? "auto" : "smooth");
    } else if (busy) {
      setUnread(true);
    }
  }, [thread, busy]);

  const last = thread.messages[thread.messages.length - 1];

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="relative min-h-0 flex-1">
        <div
          ref={scroller}
          role="log"
          aria-live="off"
          className="ask-scroll h-full overflow-y-auto px-4 pb-6 pt-5"
          onScroll={(event) => {
            const el = event.currentTarget;
            stick.current = el.scrollHeight - el.clientHeight - el.scrollTop < STICK_PX;
            if (stick.current) setUnread(false);
          }}
        >
          {last ? (
            <div className="space-y-8">
              {thread.messages.map((message, index) => (
                <TurnView
                  key={message.id || index}
                  message={message}
                  isLast={index === thread.messages.length - 1}
                  onRetry={conversation.retry}
                  onChoose={(id) => submit(id)}
                  onConfirm={(m) => void conversation.confirm(m)}
                  onCancel={(m) => void conversation.cancel(m)}
                  canAnalyze={isTeamReader}
                />
              ))}
            </div>
          ) : (
            empty?.(submit)
          )}
        </div>
        {unread ? (
          <button
            type="button"
            className="glass-card-strong ask-enter absolute bottom-3 left-1/2 inline-flex -translate-x-1/2 items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[13px] text-foreground transition-transform duration-150 active:scale-[0.98]"
            onClick={() => {
              stick.current = true;
              setUnread(false);
              toBottom("smooth");
            }}
          >
            <ArrowDown size={13} weight="light" aria-hidden="true" />
            {t.product.askNewReply}
          </button>
        ) : null}
      </div>
      <div className="shrink-0 px-3 pb-3">
        <Composer
          value={draft}
          onChange={setDraft}
          autoFocus={visible}
          busy={busy && last?.role === "assistant" && last.phase !== "pending"}
          onStop={conversation.stop}
          onSend={() => {
            const text = draft.trim();
            if (!text) return;
            setDraft("");
            submit(text);
          }}
        />
      </div>
    </div>
  );
}
