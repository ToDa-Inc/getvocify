import { useState } from "react";
import { useAuth } from "@/features/auth";
import { useOptionalDialerFocus } from "@/features/calling/DialerFocusProvider";
import { TodayCardActions } from "@/features/today/components/TodayCardActions";
import { dialerAvailable } from "@/lib/ask-calls";
import { productText } from "@/lib/product-catalog";
import { AnimIcon } from "@/components/ui/anim-icon";
import { Button } from "@/components/ui/button";
import { IconAction } from "@/components/ui/icon-action";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import type { AskMessage } from "@/lib/ask-thread";
import ActivityLine from "./ActivityLine";
import AnswerCards from "./AnswerCards";
import AnswerBody from "./AnswerBody";
import ConfirmCard from "./ConfirmCard";
import CoverageNote from "./CoverageNote";

type Props = {
  message: AskMessage;
  isLast: boolean;
  onRetry: () => void;
  onChoose: (id: string) => void;
  onConfirm: (message: AskMessage) => void;
  onCancel: (message: AskMessage) => void;
  canAnalyze: boolean;
};

export default function TurnView({ message, isLast, onRetry, onChoose, onConfirm, onCancel, canAnalyze }: Props) {
  const { t } = useLanguage();
  const { user } = useAuth();
  const dialer = useOptionalDialerFocus();
  const canCall = Boolean(dialer) && dialerAvailable({ company: user?.company });
  const [copied, setCopied] = useState(false);

  if (message.role === "user") {
    return (
      <div className="ask-enter flex justify-end">
        <p className="max-w-[85%] whitespace-pre-line rounded-[20px] rounded-br-md border border-[hsl(var(--hairline))] bg-secondary/70 px-4 py-2.5 text-[15px] leading-relaxed text-foreground [overflow-wrap:anywhere]">
          {message.text}
        </p>
      </div>
    );
  }

  const running = message.phase === "sending" || message.phase === "working" || message.phase === "streaming";
  const hasText = message.text.trim().length > 0;
  const failed = message.phase === "failed";

  async function copy() {
    try {
      await navigator.clipboard.writeText(message.text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard can be blocked; nothing to recover.
    }
  }

  return (
    <div className="group/turn ask-enter space-y-3">
      <ActivityLine
        steps={message.steps}
        thinking={message.phase === "sending" || (message.phase === "working" && !hasText)}
        settled={hasText || !running}
      />
      {/* A proposed write shows its sentence once, inside the card that asks for the decision. */}
      {hasText && !message.confirm ? <AnswerBody text={message.text} evidence={message.evidence} streaming={running} /> : null}
      {message.phase === "done" && !message.confirm ? <AnswerCards cards={message.cards} evidence={message.evidence} /> : null}
      {message.phase === "pending" ? (
        <p className="ask-shimmer text-[13px]" role="status">{t.product.askReconnecting}</p>
      ) : null}
      {message.stopped ? <p className={THEME_TOKENS.typography.capsLabel}>{t.product.askStopped}</p> : null}
      {message.phase === "done" && message.callTargets.length > 0 ? (
        <ul className="space-y-1.5" aria-label={t.product.contactPrioritiesTitle}>
          {message.callTargets.map((target) => (
            <li
              key={`${target.connection_id ?? ""}:${target.contact_id}`}
              className="ask-enter flex items-center justify-between gap-3 rounded-xl border border-[hsl(var(--hairline))] bg-card py-1.5 pl-4 pr-1.5 shadow-soft transition-colors hover:border-beige/25"
            >
              <div className="min-w-0">
                <p className="truncate text-[15px] text-foreground">{target.contact_name || t.product.today_unknown_contact}</p>
                <p className={`truncate ${THEME_TOKENS.typography.capsLabel}`}>{productText(target.reason, t.product)}</p>
              </div>
              <TodayCardActions
                onCall={canCall && dialer ? () => dialer.openForContact({ contactId: target.contact_id, name: target.contact_name ?? null }) : undefined}
                crmHref={target.crm_url}
              />
            </li>
          ))}
        </ul>
      ) : null}
      {message.coverageNote ? <CoverageNote note={message.coverageNote} canAnalyze={canAnalyze} /> : null}
      {message.confirm ? (
        <ConfirmCard card={message.confirm} onConfirm={() => onConfirm(message)} onCancel={() => onCancel(message)} />
      ) : null}
      {message.choices.length > 0 && isLast ? (
        <div className="flex flex-wrap gap-2" role="group" aria-label={t.product.askChoicesLabel}>
          {message.choices.map((choice) => (
            <Button key={choice.id} size="sm" variant="outline" className="rounded-full" onClick={() => onChoose(choice.id)}>
              {choice.label}
            </Button>
          ))}
        </div>
      ) : null}
      {failed ? (
        <div className="flex flex-wrap items-center gap-3" role="alert">
          <p className="text-[13px] text-muted-foreground">{t.product.askFailed}</p>
          {message.retryable && isLast ? (
            <Button size="sm" variant="outline" onClick={onRetry}>
              <AnimIcon name="refresh" size={14} stroke={1.25} />
              {t.product.askRetry}
            </Button>
          ) : null}
        </div>
      ) : null}
      {message.stopped && isLast ? (
        <Button size="sm" variant="outline" onClick={onRetry}>
          <AnimIcon name="refresh" size={14} stroke={1.25} />
          {t.product.askRetry}
        </Button>
      ) : null}
      {message.phase === "done" && hasText && !message.stopped ? (
        <div className={`-ml-2.5 -mt-1 flex transition-opacity duration-150 ${isLast ? "" : "opacity-0 group-hover/turn:opacity-100 group-focus-within/turn:opacity-100 max-md:opacity-100"}`}>
          <IconAction label={copied ? t.product.askCopied : t.product.askCopy} onClick={() => void copy()}>
            <AnimIcon name="copy" stroke={1.25} state={copied && "done"} />
          </IconAction>
        </div>
      ) : null}
    </div>
  );
}
