import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/shared/lib/api-client";
import {
  cancelConfirm,
  confirmErrorDetail,
  confirmResult,
  pendingConfirmFromTurn,
  type AskConfirmBody,
  type AskTurnConfirmation,
} from "@/lib/ask-confirm";
import { askConfirmPrompt } from "@/lib/product-catalog";
import { useLanguage } from "@/lib/i18n";
import { emptyAsk, notePosted, noteTick, reopenAsk, type AskSnapshot, type AskView } from "@/lib/ask-turn";
import { askChoices, choiceFollowUp, showAskChoices, viewForFollowUp, type AskChoice } from "@/lib/ask-choices";
import { askStepLabel, askStepsFrom, askStepsSummary, type AskStep } from "@/lib/ask-steps";
import VoiceComposer from "@/features/ask/components/VoiceComposer";
import { useAuth } from "@/features/auth";
import { useOptionalDialerFocus } from "@/features/calling/DialerFocusProvider";
import { TodayCardActions } from "@/features/today/components/TodayCardActions";
import { askCallTargets, dialerAvailable, type AskCallTarget } from "@/lib/ask-calls";
import { isDesktopHost } from "@/lib/desktop-host";
import { askSituation } from "@/lib/ask-situation";
import { productText } from "@/lib/product-catalog";
import { answerParts, plainAnswer } from "@/lib/summary-line";
import { Check, PaperPlaneTilt, Warning, X } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { IconAction } from "@/components/ui/icon-action";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const STORAGE_KEY = "vocify-ask-turn";
const CONVERSATION_KEY = "vocify-ask-conversation";
const PROGRESS_POLL_MS = 800;

type StoredTurn = { conversationId: string; turnId: string };

type AskTurnBody = {
  turn_id: string;
  status: AskSnapshot["status"];
  text: string;
  question?: string | null;
  coverage?: "complete" | "partial" | "forbidden" | "unavailable" | null;
  item_count?: number;
  confirmation?: AskTurnConfirmation | null;
  choices?: AskChoice[];
  call_targets?: AskCallTarget[];
  steps?: unknown;
};

type Line = { role: "user" | "vocify"; text: string; turnId?: string | null };

function newConversationId(): string {
  const id = crypto.randomUUID();
  try {
    sessionStorage.setItem(CONVERSATION_KEY, id);
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* storage unavailable: the id still scopes this tab's conversation */
  }
  return id;
}

function readConversationId(): string {
  try {
    const existing = sessionStorage.getItem(CONVERSATION_KEY);
    if (existing) return existing;
  } catch {
    return crypto.randomUUID();
  }
  return newConversationId();
}

function readStored(): StoredTurn | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredTurn) : null;
  } catch {
    return null;
  }
}

function StepIcon({ state }: { state: AskStep["state"] }) {
  if (state === "running") return <VocifySpinner size={11} />;
  if (state === "error") return <Warning size={12} weight="light" className="text-muted-foreground" />;
  return <Check size={12} weight="light" className="text-muted-foreground" />;
}

export default function AskPanel({ embedded = false }: { embedded?: boolean }) {
  const { t } = useLanguage();
  const copy = t.product;
  const { user } = useAuth();
  const dialer = useOptionalDialerFocus();
  const canCall = Boolean(dialer) && dialerAvailable({ desktop: isDesktopHost(), company: user?.company });
  const [draft, setDraft] = useState("");
  const [read, setRead] = useState<{ coverage?: AskTurnBody["coverage"]; items?: number }>({});
  const [turnChoices, setTurnChoices] = useState<AskChoice[]>([]);
  const [callTargets, setCallTargets] = useState<AskCallTarget[]>([]);
  const [pendingConfirm, setPendingConfirm] = useState<ReturnType<typeof pendingConfirmFromTurn>>(null);
  const [view, setView] = useState<AskView>(emptyAsk());
  const [lines, setLines] = useState<Line[]>([]);
  const [sending, setSending] = useState(false);
  const [conversationId, setConversationId] = useState(readConversationId);
  // Live tool steps of the turn in flight, and the finished steps of each answered turn.
  const [inFlight, setInFlight] = useState<string | null>(null);
  const [liveSteps, setLiveSteps] = useState<AskStep[]>([]);
  const [stepsByTurn, setStepsByTurn] = useState<Record<string, AskStep[]>>({});
  // A turn that could not be answered: shown as such, with the question to retry.
  const [failedQuestion, setFailedQuestion] = useState<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const stick = useRef(true);

  const applyTurn = (turn: AskTurnBody) => {
    setRead({ coverage: turn.coverage, items: turn.item_count });
    setPendingConfirm(pendingConfirmFromTurn(turn));
    setTurnChoices(askChoices(turn));
    setCallTargets(askCallTargets(turn));
    const steps = askStepsFrom(turn.steps);
    if (turn.turn_id && steps.length > 0) {
      setStepsByTurn((current) => ({ ...current, [turn.turn_id]: steps }));
    }
    if (turn.status === "failed") setFailedQuestion((turn.question || "").trim() || null);
  };

  useEffect(() => {
    const stored = readStored();
    if (!stored || stored.conversationId !== conversationId) return;
    let cancelled = false;
    api
      .get<AskTurnBody>(`/ask/conversations/${stored.conversationId}/turns/${stored.turnId}`)
      .then((turn) => {
        if (cancelled) return;
        setView(reopenAsk(stored.turnId, {
          turnId: turn.turn_id || stored.turnId,
          status: turn.status,
          text: turn.text,
        }));
        const question = (turn.question || "").trim();
        const answer = (turn.text || "").trim();
        const restored: Line[] = [];
        if (question) restored.push({ role: "user", text: question });
        if (answer && turn.status === "completed") restored.push({ role: "vocify", text: answer, turnId: turn.turn_id });
        if (restored.length > 0) setLines(restored);
        applyTurn(turn);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  useEffect(() => {
    if (!view.turnId || view.status === "completed" || view.status === "failed" || view.status === "idle") {
      return;
    }
    const timer = window.setInterval(() => {
      api
        .get<AskTurnBody>(`/ask/conversations/${conversationId}/turns/${view.turnId}`)
        .then((turn) => {
          setView((current) =>
            noteTick(current, 2000, { turnId: turn.turn_id, status: turn.status, text: turn.text }, false),
          );
          applyTurn(turn);
        })
        .catch(() => {
          setView((current) => noteTick(current, 2000, null, false));
        });
    }, 2000);
    return () => window.clearInterval(timer);
  }, [conversationId, view.turnId, view.status]);

  // While the answer is being worked out, show what Vocify is doing right now.
  useEffect(() => {
    if (!inFlight) return;
    let stopped = false;
    const tick = () => {
      api
        .get<{ running: boolean; steps: unknown }>(
          `/ask/conversations/${conversationId}/progress?client_turn_id=${encodeURIComponent(inFlight)}`,
        )
        .then((progress) => {
          if (!stopped && progress.running) setLiveSteps(askStepsFrom(progress.steps));
        })
        .catch(() => undefined);
    };
    const timer = window.setInterval(tick, PROGRESS_POLL_MS);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [inFlight, conversationId]);

  useEffect(() => {
    if (!view.text || view.status === "failed") return;
    setLines((prev) => {
      const lastUser = [...prev].reverse().find((line) => line.role === "user");
      if (lastUser?.text === view.text) return prev;
      const last = prev[prev.length - 1];
      if (last?.role === "vocify") {
        if (last.text === view.text) return prev;
        return [...prev.slice(0, -1), { role: "vocify", text: view.text, turnId: view.turnId }];
      }
      return [...prev, { role: "vocify", text: view.text, turnId: view.turnId }];
    });
  }, [view.text, view.status, view.turnId]);

  async function postTurn(text: string, { retry = false }: { retry?: boolean } = {}) {
    if (!retry) setLines((prev) => [...prev, { role: "user", text }]);
    setTurnChoices([]);
    setCallTargets([]);
    setFailedQuestion(null);
    setSending(true);
    const clientTurnId = crypto.randomUUID();
    setInFlight(clientTurnId);
    setLiveSteps([]);
    stick.current = true;
    try {
      const turn = await api.post<AskTurnBody>(
        `/ask/conversations/${conversationId}/turns`,
        { client_turn_id: clientTurnId, text },
      );
      const next = notePosted(viewForFollowUp(view), {
        turnId: turn.turn_id,
        status: turn.status,
        text: turn.text,
      });
      setView(next);
      applyTurn({ ...turn, question: turn.question ?? text });
      if (next.turnId) {
        try {
          sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ conversationId, turnId: next.turnId }));
        } catch {
          /* storage unavailable: nothing to restore later */
        }
      }
      return true;
    } catch {
      // Network or server error before any answer: say so, keep the question to retry.
      setFailedQuestion(text);
      return false;
    } finally {
      setSending(false);
      setInFlight(null);
      setLiveSteps([]);
    }
  }

  async function send() {
    const text = draft.trim();
    if (!text || busy) return;
    setDraft("");
    const ok = await postTurn(text);
    if (!ok) setDraft((current) => current || text);
  }

  function startNewConversation() {
    setConversationId(newConversationId());
    setLines([]);
    setView(emptyAsk());
    setRead({});
    setTurnChoices([]);
    setCallTargets([]);
    setPendingConfirm(null);
    setStepsByTurn({});
    setFailedQuestion(null);
    setDraft("");
    composer.current?.focus();
  }

  function applyConfirmOutcome(outcome: ReturnType<typeof confirmResult>) {
    if (!outcome.clearPending) return;
    setPendingConfirm(null);
    if (outcome.text) {
      setView((current) => ({ ...current, text: outcome.text!, notice: null }));
    }
  }

  async function confirmPending() {
    if (!pendingConfirm) return;
    try {
      const body = await api.post<AskConfirmBody>(
        `/ask/conversations/${conversationId}/operations/${pendingConfirm.operationId}/confirm`,
        { revision: pendingConfirm.revision, contact_id: pendingConfirm.contactId },
      );
      applyConfirmOutcome(confirmResult(body));
    } catch (error) {
      const detail = error instanceof ApiError ? confirmErrorDetail(error.data) : null;
      setView((current) => ({ ...current, notice: detail ?? copy.askConfirmFailed }));
    }
  }

  async function cancelPending() {
    if (!pendingConfirm) return;
    try {
      await api.post(`/ask/conversations/${conversationId}/operations/${pendingConfirm.operationId}/cancel`);
      applyConfirmOutcome(cancelConfirm());
    } catch {
      setView((current) => ({ ...current, notice: copy.askConfirmFailed }));
    }
  }

  const situation = askSituation({
    hasTurns: Boolean(view.turnId),
    coverage: read.coverage,
    items: read.items,
  });

  const choicesOpen = showAskChoices(view, turnChoices);
  const busy = sending || view.status === "pending" || view.status === "running";
  const phase = view.waitedMs >= 30000
    ? copy.askStillGoing
    : read.coverage === "partial"
      ? copy.askPhasePartial
      : copy.askConsulting;
  const stepLabels = copy.askStepLabels as Record<string, string>;

  useEffect(() => {
    const el = scroller.current;
    if (!el || !stick.current) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollTo({ top: el.scrollHeight, behavior: reduced ? "auto" : "smooth" });
  }, [lines, busy, pendingConfirm, turnChoices, callTargets, liveSteps, failedQuestion]);

  // The composer grows with what is typed, up to its max height.
  useEffect(() => {
    const el = composer.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 128)}px`;
  }, [draft]);

  return (
    <section className={embedded
      ? "flex h-full min-h-0 flex-col"
      : `mx-auto flex min-h-[calc(100dvh-8rem)] max-w-2xl flex-col ${THEME_TOKENS.motion.fadeIn}`}>
      {lines.length > 0 ? (
        <div className="flex justify-end pb-2">
          <button
            type="button"
            className="text-[13px] text-muted-foreground hover:text-foreground disabled:opacity-50"
            disabled={busy}
            onClick={startNewConversation}
          >
            {copy.askNewConversation}
          </button>
        </div>
      ) : null}
      <div
        ref={scroller}
        className="flex-1 space-y-3 overflow-y-auto pb-4"
        aria-live="polite"
        onScroll={(event) => {
          const el = event.currentTarget;
          stick.current = el.scrollHeight - el.clientHeight - el.scrollTop < 48;
        }}
      >
        {lines.length === 0 && situation.message ? (
          <>
            <p className={THEME_TOKENS.typography.body}>{productText(situation.message, copy)}</p>
            <p className={THEME_TOKENS.typography.capsLabel}>{copy.askExample}</p>
          </>
        ) : null}
        {lines.map((line, index) => {
          if (line.role === "user") {
            return (
              <p
                key={`${line.role}-${index}`}
                className="ml-auto max-w-[85%] whitespace-pre-line rounded-2xl bg-secondary/70 px-4 py-2.5 text-[15px] leading-relaxed text-foreground"
              >
                {line.text}
              </p>
            );
          }
          const steps = line.turnId ? stepsByTurn[line.turnId] ?? [] : [];
          const summary = askStepsSummary(steps, copy.askStepsSummary, copy.askStepsSummaryOne);
          return (
            <div key={`${line.role}-${index}`} className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} max-w-[85%] px-4 py-3`}>
              <p className="whitespace-pre-line text-[15px] leading-relaxed text-foreground">
                {answerParts(plainAnswer(line.text)).map((part, partIndex) =>
                  part.href ? (
                    <a
                      key={partIndex}
                      href={part.href}
                      target="_blank"
                      rel="noreferrer"
                      className="underline decoration-border underline-offset-2 hover:text-beige"
                    >
                      {part.text}
                    </a>
                  ) : (
                    <span key={partIndex}>{part.text}</span>
                  ),
                )}
              </p>
              {summary ? (
                <details className="mt-2">
                  <summary className="cursor-pointer text-[12px] text-muted-foreground">{summary}</summary>
                  <ul className="mt-1.5 space-y-1">
                    {steps.map((step, stepIndex) => (
                      <li key={stepIndex} className="flex items-center gap-2 text-[12px] text-muted-foreground">
                        <StepIcon state={step.state} />
                        {askStepLabel(step, stepLabels, copy.askStepFallback)}
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </div>
          );
        })}
        {!busy && failedQuestion ? (
          <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} max-w-[85%] space-y-2 px-4 py-3`} role="alert">
            <p className="text-[15px] leading-relaxed text-foreground">{copy.askFailed}</p>
            <Button type="button" variant="outline" size="sm" onClick={() => void postTurn(failedQuestion, { retry: true })}>
              {copy.askRetry}
            </Button>
          </div>
        ) : null}
        {!busy && callTargets.length > 0 ? (
          <ul className="max-w-[85%] space-y-1.5" aria-label={copy.contactPrioritiesTitle}>
            {callTargets.map((target) => (
              <li
                key={`${target.connection_id ?? ""}:${target.contact_id}`}
                className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} flex items-center justify-between gap-3 py-1.5 pl-4 pr-1.5`}
              >
                <div className="min-w-0">
                  <p className="truncate text-[15px] text-foreground">{target.contact_name || copy.today_unknown_contact}</p>
                  <p className={`truncate ${THEME_TOKENS.typography.capsLabel}`}>{productText(target.reason, copy)}</p>
                </div>
                <TodayCardActions
                  onCall={canCall && dialer
                    ? () => dialer.openForContact({ contactId: target.contact_id, name: target.contact_name ?? null })
                    : undefined}
                  crmHref={target.crm_url}
                />
              </li>
            ))}
          </ul>
        ) : null}
        {busy || choicesOpen || pendingConfirm || (!busy && read.coverage === "partial") || view.notice ? (
          <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} max-w-[85%] space-y-3 px-4 py-3`}>
            {busy ? (
              <div role="status" className="space-y-1.5">
                {liveSteps.length > 0 ? (
                  <ul className="space-y-1">
                    {liveSteps.map((step, index) => (
                      <li key={index} className="flex items-center gap-2 text-[13px] text-muted-foreground">
                        <StepIcon state={step.state} />
                        {askStepLabel(step, stepLabels, copy.askStepFallback)}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {liveSteps.every((step) => step.state !== "running") ? (
                  <p className="inline-flex items-center gap-2 text-[13px] text-muted-foreground">
                    <VocifySpinner size={12} />
                    {sending && liveSteps.length === 0 ? copy.askSending : phase}
                  </p>
                ) : null}
              </div>
            ) : null}
            {!busy && read.coverage === "partial" ? (
              <p className={THEME_TOKENS.typography.capsLabel}>{copy.askPhasePartial}</p>
            ) : null}
            {view.notice && !busy ? <p className="text-sm text-muted-foreground" role="alert">{view.notice}</p> : null}
            {view.unread && !busy ? (
              <p className="text-sm text-beige" role="status">{copy.askUnread}</p>
            ) : null}
            {choicesOpen ? (
              <div className="flex flex-wrap gap-2" role="group" aria-label={copy.askChoicesLabel}>
                {turnChoices.map((choice) => (
                  <Button
                    key={choice.id}
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      void postTurn(choiceFollowUp(choice));
                    }}
                  >
                    {choice.label}
                  </Button>
                ))}
              </div>
            ) : null}
            {pendingConfirm ? (
              <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} space-y-3 px-4 py-3`}>
                <p className={THEME_TOKENS.typography.body}>
                  {askConfirmPrompt(copy, pendingConfirm.contactId)}
                </p>
                <div className="flex items-center gap-0.5">
                  <IconAction label={copy.confirmAction} onClick={() => void confirmPending()}>
                    <Check size={16} weight="light" />
                  </IconAction>
                  <IconAction label={copy.cancelAction} tone="danger" onClick={() => void cancelPending()}>
                    <X size={16} weight="light" />
                  </IconAction>
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
      {/* The composer stays available while choices are offered: typing is also an answer. */}
      <form
        className="sticky bottom-0 border-t border-border/60 bg-background pt-3"
        onSubmit={(event) => {
          event.preventDefault();
          void send();
        }}
      >
        <div className="flex items-end gap-2 rounded-xl border border-border/70 bg-card px-3 py-2 focus-within:border-beige/40">
          <textarea
            ref={composer}
            className="block max-h-32 min-h-6 flex-1 resize-none bg-transparent py-1 text-sm text-foreground outline-none"
            rows={1}
            value={draft}
            placeholder={copy.askPlaceholder}
            aria-label={copy.askPlaceholder}
            disabled={busy}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void send();
              }
            }}
          />
          <VoiceComposer
            onText={(text) => setDraft(text)}
            transcribe={async (blob) => {
              const dataUrl = await new Promise<string>((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(String(reader.result || ""));
                reader.onerror = () => reject(reader.error);
                reader.readAsDataURL(blob);
              });
              const comma = dataUrl.indexOf(",");
              const result = await api.post<{ text: string; memo_id: null }>("/ask/transcribe", {
                audio_base64: comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl,
              });
              return result.text;
            }}
          />
          <IconAction
            label={copy.askSend}
            disabled={busy || !draft.trim()}
            pending={sending}
            onClick={() => void send()}
          >
            <PaperPlaneTilt size={16} weight="light" />
          </IconAction>
        </div>
      </form>
    </section>
  );
}
