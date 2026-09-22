import { useEffect, useState } from "react";
import { api, ApiError } from "@/shared/lib/api-client";
import { cancelConfirm, confirmErrorDetail, confirmResult, type AskConfirmBody } from "@/lib/ask-confirm";
import { askConfirmPrompt } from "@/lib/product-catalog";
import { useLanguage } from "@/lib/i18n";
import { emptyAsk, notePosted, noteTick, reopenAsk, type AskSnapshot, type AskView } from "@/lib/ask-turn";
import { askChoices, choiceFollowUp, showAskChoices, viewForFollowUp, type AskChoice } from "@/lib/ask-choices";
import VoiceComposer from "@/features/ask/components/VoiceComposer";
import { askConfirmation, askSituation } from "@/lib/ask-situation";

const STORAGE_KEY = "vocify-ask-turn";

type StoredTurn = { conversationId: string; turnId: string };

type AskTurnBody = {
  turn_id: string;
  status: AskSnapshot["status"];
  text: string;
  coverage?: "complete" | "partial" | "forbidden" | "unavailable" | null;
  item_count?: number;
  confirmation?: { operation_id?: string; revision?: number; contact_id?: string } | null;
  choices?: AskChoice[];
};

function readStored(): StoredTurn | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredTurn) : null;
  } catch {
    return null;
  }
}

export default function AskPanel() {
  const { t } = useLanguage();
  const [draft, setDraft] = useState("");
  const [read, setRead] = useState<{ coverage?: AskTurnBody["coverage"]; items?: number }>({});
  const [turnChoices, setTurnChoices] = useState<AskChoice[]>([]);
  const [pendingConfirm, setPendingConfirm] = useState<ReturnType<typeof askConfirmation>>(null);
  const [view, setView] = useState<AskView>(emptyAsk());
  const [conversationId] = useState("conv-1");

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
        setRead({ coverage: turn.coverage, items: turn.item_count });
        setPendingConfirm(askConfirmation(turn));
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
          setPendingConfirm(askConfirmation(turn));
          setTurnChoices(askChoices(turn));
        })
        .catch(() => {
          setView((current) => noteTick(current, 2000, null, false));
        });
    }, 2000);
    return () => window.clearInterval(timer);
  }, [conversationId, view.turnId, view.status]);

  async function postTurn(text: string) {
    setTurnChoices([]);
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
    setPendingConfirm(askConfirmation(turn));
    setTurnChoices(askChoices(turn));
    if (next.turnId) {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ conversationId, turnId: next.turnId }));
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

  return (
    <section className="mx-auto max-w-xl px-4 py-8">
      <h1 className="text-lg font-medium">Preguntar</h1>
      {situation.message ? (
        <p className="mt-4 text-sm text-muted-foreground">{situation.message}</p>
      ) : null}
      {view.notice ? (
        <p className="mt-4 text-sm text-muted-foreground" role="status">{view.notice}</p>
      ) : null}
      {view.unread ? (
        <p className="mt-2 text-sm" role="status">Hay una respuesta nueva</p>
      ) : null}
      {view.text ? <p className="mt-4 text-sm">{view.text}</p> : null}
      {choicesOpen ? (
        <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Opciones">
          {turnChoices.map((choice) => (
            <button
              key={choice.id}
              type="button"
              className="rounded-full border border-border px-3 py-1 text-sm"
              onClick={() => {
                void postTurn(choiceFollowUp(choice));
              }}
            >
              {choice.label}
            </button>
          ))}
        </div>
      ) : null}
      {pendingConfirm ? (
        <div className="mt-3 space-y-2">
          <p className="text-sm text-muted-foreground">
            {askConfirmPrompt(t.product, pendingConfirm.contactId)}
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded-full border border-border px-3 py-1 text-sm"
              onClick={() => {
                void confirmPending();
              }}
            >
              {t.product.confirmAction}
            </button>
            <button
              type="button"
              className="rounded-full border border-border px-3 py-1 text-sm"
              onClick={() => {
                void cancelPending();
              }}
            >
              {t.product.cancelAction}
            </button>
          </div>
        </div>
      ) : null}
      {!choicesOpen ? (
        <form
          className="mt-6 space-y-2"
          onSubmit={(event) => {
            event.preventDefault();
            void send();
          }}
        >
          <textarea
            className="w-full rounded-lg border border-border bg-transparent px-3 py-2 text-sm"
            rows={3}
            value={draft}
            placeholder="Pregunta por un contacto"
            onChange={(event) => setDraft(event.target.value)}
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
          <button
            type="submit"
            className="rounded-full border border-border px-3 py-1 text-sm"
            disabled={Boolean(view.turnId && view.status !== "completed" && view.status !== "failed")}
          >
            Enviar
          </button>
        </form>
      ) : null}
    </section>
  );
}
