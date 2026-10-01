import { useState } from "react";
import { ArrowLeft, ArrowRight, ClockCounterClockwise, Plus, Trash, X } from "@phosphor-icons/react";
import { IconAction } from "@/components/ui/icon-action";
import { ConfirmAction } from "@/components/ui/confirm-action";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { useAskConversation } from "../hooks/useAskConversation";
import { useAskSuggestions } from "../hooks/useAskSuggestions";
import AskThread from "./AskThread";
import HistoryList from "./HistoryList";

/** First visit, or a new conversation: the question is the whole screen, with the ones this account can answer. */
function EmptyState({ suggestions, onPick }: { suggestions: string[]; onPick: (text: string) => void }) {
  const { t } = useLanguage();
  return (
    <div className="ask-enter flex min-h-full flex-col justify-center py-8">
      <h3 className="text-[24px] leading-tight tracking-tight text-foreground">{t.product.askGreeting}</h3>
      <p className={`mt-1.5 ${THEME_TOKENS.typography.body} text-[14px]`}>{t.product.askEmpty}</p>
      {suggestions.length > 0 ? (
        <ul className="mt-6 overflow-hidden rounded-2xl border border-[hsl(var(--hairline))] bg-card/60 shadow-[inset_0_1px_0_rgb(255_255_255/0.7)]">
          {suggestions.map((text) => (
            <li key={text} className="border-t border-[hsl(var(--hairline))] first:border-t-0">
              <button
                type="button"
                onClick={() => onPick(text)}
                className="group flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-[14px] text-foreground/85 transition-colors hover:bg-secondary/40 hover:text-foreground focus-visible:bg-secondary/40 focus-visible:outline-none"
              >
                <span>{text}</span>
                <ArrowRight
                  size={14}
                  weight="light"
                  className="shrink-0 -translate-x-1 text-muted-foreground opacity-0 transition-[opacity,transform] duration-150 group-hover:translate-x-0 group-hover:opacity-100 group-focus-visible:translate-x-0 group-focus-visible:opacity-100"
                  aria-hidden="true"
                />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export default function AskPanel({ onClose }: { onClose?: () => void }) {
  const { t } = useLanguage();
  const conversation = useAskConversation();
  const { thread } = conversation;
  const [showHistory, setShowHistory] = useState(false);
  const suggestions = useAskSuggestions()
    .map((id) => (t.product as Record<string, string>)[`askSuggest_${id}`])
    .filter(Boolean);
  const [clearing, setClearing] = useState(false);
  const [deletingThis, setDeletingThis] = useState(false);

  const empty = thread.messages.length === 0;

  return (
    <section className="flex h-full min-h-0 flex-col" aria-label={t.product.askTitle}>
      <header className="flex min-h-14 shrink-0 items-center justify-between gap-2 border-b border-[hsl(var(--hairline))] px-3 pl-4">
        {showHistory ? (
          <button
            type="button"
            onClick={() => setShowHistory(false)}
            className="-ml-1.5 inline-flex items-center gap-1.5 rounded-full px-1.5 py-1 text-[15px] text-foreground transition-colors hover:bg-secondary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <ArrowLeft size={15} weight="light" aria-hidden="true" />
            {t.product.askHistoryTitle}
          </button>
        ) : (
          <h2 className={THEME_TOKENS.typography.sectionTitle}>{t.product.askTitle}</h2>
        )}
        <div className="flex items-center">
          {!showHistory && !empty ? (
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
          {onClose ? (
            <IconAction label={t.product.askClose} onClick={onClose}>
              <X size={16} weight="light" />
            </IconAction>
          ) : null}
        </div>
      </header>

      {showHistory ? (
        <div className="ask-scroll ask-enter min-h-0 flex-1 overflow-y-auto px-2 pb-4 pt-4">
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
      ) : null}
      {/* Kept mounted while the history shows, so a half-typed question survives a peek at it. */}
      <div className={showHistory ? "hidden" : "min-h-0 flex-1"}>
        <AskThread
          conversation={conversation}
          visible={!showHistory}
          empty={(submit) => <EmptyState suggestions={suggestions} onPick={submit} />}
        />
      </div>
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
