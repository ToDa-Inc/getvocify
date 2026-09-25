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
import VoiceComposer from "@/features/ask/components/VoiceComposer";
import { askSituation } from "@/lib/ask-situation";
import { productText } from "@/lib/product-catalog";
import { Check, PaperPlaneTilt, X } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { IconAction } from "@/components/ui/icon-action";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const STORAGE_KEY = "vocify-ask-turn";
const CONVERSATION_KEY = "vocify-ask-conversation";

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
};

function readConversationId(): string {
  try {
    const existing = sessionStorage.getItem(CONVERSATION_KEY);
    if (existing) return existing;
    const id = crypto.randomUUID();
    sessionStorage.setItem(CONVERSATION_KEY, id);
    return id;
  } catch {
    return crypto.randomUUID();
  }
}

function readStored(): StoredTurn | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredTurn) : null;
  } catch {
    return null;
  }
}

export default function AskPanel({ embedded = false }: { embedded?: boolean }) {
  const { t } = useLanguage();
  const [draft, setDraft] = useState("");
  const [read, setRead] = useState<{ coverage?: AskTurnBody["coverage"]; items?: number }>({});
  const [turnChoices, setTurnChoices] = useState<AskChoice[]>([]);
  const [pendingConfirm, setPendingConfirm] = useState<ReturnType<typeof pendingConfirmFromTurn>>(null);
  const [view, setView] = useState<AskView>(emptyAsk());
  const [lines, setLines] = useState<{ role: "user" | "vocify"; text: string }[]>([]);
  const [sending, setSending] = useState(false);
  const [conversationId] = useState(readConversationId);
  const scroller = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  useEffect(() => {
    const stored = readStored();
    if (!stored) return;
    let cancelled = false;
    api
      .get<AskTurnBody>(
        `/ask/conversations/${stored.conversationId}/turns/${stored.turnId}`,
      )
      .then((turn) => {
        if (cancelled) return;
        setView(reopenAsk(stored.turnId, {
          turnId: turn.turn_id || stored.turnId,
          status: turn.status,
          text: turn.text,
        }));
        const question = (turn.question || "").trim();
        const answer = (turn.text || "").trim();
        const restored: { role: "user" | "vocify"; text: string }[] = [];
        if (question) restored.push({ role: "user", text: question });
        if (answer && turn.status !== "pending") restored.push({ role: "vocify", text: answer });
        if (restored.length > 0) setLines(restored);
        setRead({ coverage: turn.coverage, items: turn.item_count });
        setPendingConfirm(pendingConfirmFromTurn(turn));
        setTurnChoices(askChoices(turn));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!view.turnId || view.status === "completed" || view.status === "failed" || view.status === "idle") {
      return;
    }
    const timer = window.setInterval(() => {
      api
        .get<AskTurnBody>(
          `/ask/conversations/${conversationId}/turns/${view.turnId}`,
        )
        .then((turn) => {
          setView((current) =>
            noteTick(
              current,
              2000,
              { turnId: turn.turn_id, status: turn.status, text: turn.text },
              false,
            ),
          );
          setRead({ coverage: turn.coverage, items: turn.item_count });
          setPendingConfirm(pendingConfirmFromTurn(turn));
          setTurnChoices(askChoices(turn));
        })
        .catch(() => {
          setView((current) => noteTick(current, 2000, null, false));
        });
    }, 2000);
    return () => window.clearInterval(timer);
  }, [conversationId, view.turnId, view.status]);

  useEffect(() => {
    if (!view.text) return;
    setLines((prev) => {
      const lastUser = [...prev].reverse().find((line) => line.role === "user");
      if (lastUser?.text === view.text) return prev;
      const last = prev[prev.length - 1];
      if (last?.role === "vocify") {
        if (last.text === view.text) return prev;
        return [...prev.slice(0, -1), { role: "vocify", text: view.text }];
      }
      return [...prev, { role: "vocify", text: view.text }];
    });
  }, [view.text]);

  async function postTurn(text: string) {
    setLines((prev) => [...prev, { role: "user", text }]);
    setTurnChoices([]);
    setSending(true);
    stick.current = true;
    try {
      const turn = await api.post<AskTurnBody>(
        `/ask/conversations/${conversationId}/turns`,
        { client_turn_id: crypto.randomUUID(), text },
      );
      const next = notePosted(viewForFollowUp(view), {
        turnId: turn.turn_id,
        status: turn.status,
        text: turn.text,
      });
      setView(next);
      setRead({ coverage: turn.coverage, items: turn.item_count });
      setPendingConfirm(pendingConfirmFromTurn(turn));
      setTurnChoices(askChoices(turn));
      if (next.turnId) {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ conversationId, turnId: next.turnId }));
      }
    } finally {
      setSending(false);
    }
  }

  async function send() {
    const text = draft.trim();
    if (!text || (view.turnId && view.status !== "completed" && view.status !== "failed")) return;
    await postTurn(text);
    setDraft("");
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
      setView((current) => ({
        ...current,
        notice: detail ?? t.product.askConfirmFailed,
      }));
    }
  }

  async function cancelPending() {
    if (!pendingConfirm) return;
    try {
      await api.post(
        `/ask/conversations/${conversationId}/operations/${pendingConfirm.operationId}/cancel`,
      );
      applyConfirmOutcome(cancelConfirm());
    } catch {
      /* deja el botón si falla */
    }
  }

  const situation = askSituation({
    hasTurns: Boolean(view.turnId),
    coverage: read.coverage,
    items: read.items,
  });

  const choicesOpen = showAskChoices(view, turnChoices);
  const busy = sending || view.status === "pending" || view.status === "running";
  const phase = sending
    ? t.product.askSending
    : view.waitedMs >= 30000
      ? t.product.askStillGoing
      : read.coverage === "partial"
        ? t.product.askPhasePartial
        : t.product.askConsulting;

  useEffect(() => {
    const el = scroller.current;
    if (!el || !stick.current) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollTo({ top: el.scrollHeight, behavior: reduced ? "auto" : "smooth" });
  }, [lines, busy, pendingConfirm, turnChoices]);

  return (
    <section className={embedded
      ? "flex h-full min-h-0 flex-col"
      : `mx-auto flex min-h-[calc(100dvh-8rem)] max-w-2xl flex-col ${THEME_TOKENS.motion.fadeIn}`}>
      <div
        ref={scroller}
        className="flex-1 space-y-3 overflow-y-auto pb-4"
        onScroll={(event) => {
          const el = event.currentTarget;
          stick.current = el.scrollHeight - el.clientHeight - el.scrollTop < 48;
        }}
      >
        {lines.length === 0 && situation.message ? (
          <>
            <p className={THEME_TOKENS.typography.body}>{productText(situation.message, t.product)}</p>
            <p className={THEME_TOKENS.typography.capsLabel}>{t.product.askExample}</p>
          </>
        ) : null}
        {lines.map((line, index) => (
          line.role === "user" ? (
            <p
              key={`${line.role}-${index}`}
              className="ml-auto max-w-[85%] rounded-2xl bg-secondary/70 px-4 py-2.5 text-[15px] leading-relaxed text-foreground"
            >
              {line.text}
            </p>
          ) : (
            <div key={`${line.role}-${index}`} className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} max-w-[85%] px-4 py-3`}>
              <p className="text-[15px] leading-relaxed text-foreground">{line.text}</p>
            </div>
          )
        ))}
        {busy || choicesOpen || pendingConfirm || (!busy && read.coverage === "partial") ? (
          <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} max-w-[85%] space-y-3 px-4 py-3`}>
            {busy ? (
              <p className="inline-flex items-center gap-2 text-[13px] text-muted-foreground" role="status">
                <VocifySpinner size={12} />
                {phase}
              </p>
            ) : null}
            {!busy && read.coverage === "partial" ? (
              <p className={THEME_TOKENS.typography.capsLabel}>{t.product.askPhasePartial}</p>
            ) : null}
        {view.unread && !busy ? (
          <p className="text-sm text-beige" role="status">{t.product.askUnread}</p>
        ) : null}
        {choicesOpen ? (
          <div className="flex flex-wrap gap-2" role="group" aria-label={t.product.askChoicesLabel}>
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
              {askConfirmPrompt(t.product, pendingConfirm.contactId)}
            </p>
            <div className="flex items-center gap-0.5">
              <IconAction label={t.product.confirmAction} onClick={() => void confirmPending()}>
                <Check size={16} weight="light" />
              </IconAction>
              <IconAction label={t.product.cancelAction} tone="danger" onClick={() => void cancelPending()}>
                <X size={16} weight="light" />
              </IconAction>
            </div>
          </div>
        ) : null}
          </div>
        ) : null}
      </div>
      {!choicesOpen ? (
        <form
          className="sticky bottom-0 border-t border-border/60 bg-background pt-3"
          onSubmit={(event) => {
            event.preventDefault();
            void send();
          }}
        >
          <div className="flex items-end gap-2 rounded-xl border border-border/70 bg-card px-3 py-2 focus-within:border-beige/40">
          <textarea
            className="block max-h-32 min-h-6 flex-1 resize-none bg-transparent py-1 text-sm text-foreground outline-none"
            rows={1}
            value={draft}
            placeholder={t.product.askPlaceholder}
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
            label={t.product.askSend}
            disabled={busy || !draft.trim()}
            pending={sending}
            onClick={() => void send()}
          >
            <PaperPlaneTilt size={16} weight="light" />
          </IconAction>
          </div>
        </form>
      ) : null}
    </section>
  );
}
