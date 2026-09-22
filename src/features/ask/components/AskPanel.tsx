import { useEffect, useState } from "react";
import { api } from "@/shared/lib/api-client";
import { emptyAsk, notePosted, noteTick, reopenAsk, type AskSnapshot, type AskView } from "@/lib/ask-turn";

const STORAGE_KEY = "vocify-ask-turn";

type StoredTurn = { conversationId: string; turnId: string };

function readStored(): StoredTurn | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredTurn) : null;
  } catch {
    return null;
  }
}

export default function AskPanel() {
  const [draft, setDraft] = useState("");
  const [view, setView] = useState<AskView>(emptyAsk());
  const [conversationId] = useState("conv-1");

  useEffect(() => {
    const stored = readStored();
    if (!stored) return;
    let cancelled = false;
    api
      .get<AskSnapshot & { turn_id: string; text: string; status: AskSnapshot["status"] }>(
        `/ask/conversations/${stored.conversationId}/turns/${stored.turnId}`,
      )
      .then((turn) => {
        if (cancelled) return;
        setView(reopenAsk(stored.turnId, {
          turnId: turn.turn_id || stored.turnId,
          status: turn.status,
          text: turn.text,
        }));
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
        .get<{ turn_id: string; status: AskSnapshot["status"]; text: string }>(
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
        })
        .catch(() => {
          setView((current) => noteTick(current, 2000, null, false));
        });
    }, 2000);
    return () => window.clearInterval(timer);
  }, [conversationId, view.turnId, view.status]);

  async function send() {
    const text = draft.trim();
    if (!text || view.turnId) return;
    const turn = await api.post<{ turn_id: string; status: AskSnapshot["status"]; text: string }>(
      `/ask/conversations/${conversationId}/turns`,
      { client_turn_id: crypto.randomUUID(), text },
    );
    const next = notePosted(view, {
      turnId: turn.turn_id,
      status: turn.status,
      text: turn.text,
    });
    setView(next);
    if (next.turnId) {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ conversationId, turnId: next.turnId }));
    }
    setDraft("");
  }

  return (
    <section className="mx-auto max-w-xl px-4 py-8">
      <h1 className="text-lg font-medium">Preguntar</h1>
      {view.notice ? (
        <p className="mt-4 text-sm text-muted-foreground" role="status">{view.notice}</p>
      ) : null}
      {view.unread ? (
        <p className="mt-2 text-sm" role="status">Hay una respuesta nueva</p>
      ) : null}
      {view.text ? <p className="mt-4 text-sm">{view.text}</p> : null}
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
        <button
          type="submit"
          className="rounded-full border border-border px-3 py-1 text-sm"
          disabled={Boolean(view.turnId)}
        >
          Enviar
        </button>
      </form>
    </section>
  );
}
