import { useEffect, useRef, useState } from "react";
import { ArrowDown, ClockCounterClockwise, Plus, Trash } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { IconAction } from "@/components/ui/icon-action";
import { ConfirmAction } from "@/components/ui/confirm-action";
import { useAuth } from "@/features/auth";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { useAskConversation } from "../hooks/useAskConversation";
import { useAskSuggestions } from "../hooks/useAskSuggestions";
import Composer from "./Composer";
import HistoryList from "./HistoryList";
import TurnView from "./TurnView";

const STICK_PX = 48;

export default function AskPanel({ embedded = false }: { embedded?: boolean }) {
  const { t } = useLanguage();
  const { user } = useAuth();
  const conversation = useAskConversation();
  const { thread, busy } = conversation;
  const [draft, setDraft] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [unread, setUnread] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  const isTeamReader = user?.company?.role === "owner" || user?.company?.role === "admin";
  const suggestions = useAskSuggestions()
    .map((id) => (t.product as Record<string, string>)[`askSuggest_${id}`])
    .filter(Boolean);
  const [clearing, setClearing] = useState(false);
  const [deletingThis, setDeletingThis] = useState(false);

  function submit(text: string) {
    stick.current = true;
    setUnread(false);
    conversation.send(text);
  }

  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    if (stick.current) {
      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      el.scrollTo({ top: el.scrollHeight, behavior: reduced || busy ? "auto" : "smooth" });
    } else if (busy) {
      setUnread(true);
    }
  }, [thread, busy]);

  const last = thread.messages[thread.messages.length - 1];

  return (
    <section
      className={embedded ? "flex h-full min-h-0 flex-col" : `mx-auto flex min-h-[calc(100dvh-8rem)] max-w-2xl flex-col ${THEME_TOKENS.motion.fadeIn}`}
      aria-label={t.product.askTitle}
    >
      <div className="-mt-1 mb-3 flex min-h-9 items-center justify-between gap-2">
        {showHistory ? <h2 className={`${THEME_TOKENS.typography.capsLabel} pl-3`}>{t.product.askHistoryTitle}</h2> : <span />}
        <div className="flex items-center gap-0.5">
          {!showHistory && thread.messages.length > 0 ? (
            <IconAction label={t.product.askDeleteThis} tone="danger" onClick={() => setDeletingThis(true)}>
              <Trash size={16} weight="light" />
            </IconAction>
          ) : null}
          <IconAction
            label={t.product.askHistory}
            onClick={() => {
              const next = !showHistory;
              setShowHistory(next);
              if (next) void conversation.loadHistory();
            }}
          >
            <ClockCounterClockwise size={16} weight={showHistory ? "fill" : "light"} />
          </IconAction>
          <IconAction
            label={t.product.askNewChat}
            onClick={() => {
              setShowHistory(false);
              conversation.newConversation();
            }}
          >
            <Plus size={16} weight="light" />
          </IconAction>
        </div>
      </div>

      {showHistory ? (
        <div className="min-h-0 flex-1 overflow-y-auto pb-4">
          <HistoryList
            rows={conversation.history}
            failed={conversation.historyError}
            activeId={typeof window === "undefined" ? "" : (sessionStorage.getItem("vocify-ask-conversation") ?? "")}
            onOpen={(id) => {
              setShowHistory(false);
              void conversation.openConversation(id);
            }}
            onDelete={(id) => void conversation.deleteConversation(id)}
            onClearAll={() => setClearing(true)}
          />
        </div>
      ) : (
        <>
          <div className="relative min-h-0 flex-1">
            <div
              ref={scroller}
              role="log"
              aria-live="off"
              className="h-full space-y-7 overflow-y-auto pb-4"
              onScroll={(event) => {
                const el = event.currentTarget;
                stick.current = el.scrollHeight - el.clientHeight - el.scrollTop < STICK_PX;
                if (stick.current) setUnread(false);
              }}
            >
              {thread.messages.length === 0 ? (
                <div className="space-y-4 pt-2">
                  <p className={THEME_TOKENS.typography.body}>{t.product.askEmpty}</p>
                  {suggestions.length > 0 ? (
                    <div className="flex flex-wrap gap-2">
                      {suggestions.map((text) => (
                        <Button key={text} size="sm" variant="outline" className="h-auto whitespace-normal py-2 text-left" onClick={() => submit(text)}>
                          {text}
                        </Button>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : (
                thread.messages.map((message, index) => (
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
                ))
              )}
            </div>
            {unread ? (
              <Button
                size="sm"
                variant="outline"
                className="absolute bottom-2 left-1/2 -translate-x-1/2 shadow-sm"
                onClick={() => {
                  stick.current = true;
                  setUnread(false);
                  scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
                }}
              >
                <ArrowDown size={14} weight="light" aria-hidden="true" />
                {t.product.askNewReply}
              </Button>
            ) : null}
          </div>
          <Composer
            value={draft}
            onChange={setDraft}
            busy={busy && last?.role === "assistant" && last.phase !== "pending"}
            onStop={conversation.stop}
            onSend={() => {
              const text = draft.trim();
              if (!text) return;
              setDraft("");
              submit(text);
            }}
          />
        </>
      )}
      <ConfirmAction
        open={deletingThis}
        onOpenChange={setDeletingThis}
        title={t.product.askDeleteThisTitle}
        description={t.product.askDeleteThisBody}
        confirmLabel={t.product.askDeleteThis}
        cancelLabel={t.product.cancelAction}
        onConfirm={() => {
          setDeletingThis(false);
          void conversation.deleteCurrent();
        }}
      />
      <ConfirmAction
        open={clearing}
        onOpenChange={setClearing}
        title={t.product.askClearAllTitle}
        description={t.product.askClearAllBody}
        confirmLabel={t.product.askClearAll}
        cancelLabel={t.product.cancelAction}
        onConfirm={() => {
          setClearing(false);
          setShowHistory(false);
          void conversation.clearAll();
        }}
      />
    </section>
  );
}
