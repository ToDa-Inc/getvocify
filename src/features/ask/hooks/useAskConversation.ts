import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { api, ApiError } from "@/shared/lib/api-client";
import { parseSse } from "@/lib/ask-sse";
import {
  emptyThread,
  isBusy,
  messagesFromTurns,
  reduceThread,
  type AskConfirm,
  type AskMessage,
  type TurnBody,
} from "@/lib/ask-thread";

const CONVERSATION_KEY = "vocify-ask-conversation";
const POLL_FAST_MS = 2000;
const POLL_SLOW_MS = 5000;
const POLL_SLOW_AFTER_MS = 30000;

export type ConversationSummary = { id: string; title: string; turns: number; updated_at: string | null };

/** `fresh` means this tab has no conversation yet, so there is nothing to restore from the server. */
function readConversation(restoreId?: string | null): { id: string; fresh: boolean } {
  if (restoreId) {
    rememberConversationId(restoreId);
    return { id: restoreId, fresh: false };
  }
  try {
    const existing = sessionStorage.getItem(CONVERSATION_KEY);
    if (existing) return { id: existing, fresh: false };
    const id = crypto.randomUUID();
    sessionStorage.setItem(CONVERSATION_KEY, id);
    return { id, fresh: true };
  } catch {
    return { id: crypto.randomUUID(), fresh: true };
  }
}

function rememberConversationId(id: string) {
  try {
    sessionStorage.setItem(CONVERSATION_KEY, id);
  } catch {
    // Storage can be blocked; the conversation still works for this page view.
  }
}

/**
 * One conversation: streams a turn, recovers it if the reader drops, runs confirmations, lists history.
 * `restoreId` opens that conversation instead of this tab's last one (a `?c=` link); `onMissing` hears
 * when the conversation restored on mount could not be read.
 */
export function useAskConversation({ restoreId, onMissing }: { restoreId?: string | null; onMissing?: () => void } = {}) {
  const [thread, dispatch] = useReducer(reduceThread, undefined, emptyThread);
  const initial = useRef<{ id: string; fresh: boolean } | null>(null);
  if (initial.current === null) initial.current = readConversation(restoreId);
  const missing = useRef(onMissing);
  missing.current = onMissing;
  const [conversationId, setConversationId] = useState(initial.current.id);
  const [history, setHistory] = useState<ConversationSummary[] | null>(null);
  const [historyError, setHistoryError] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const pollTimer = useRef<number | null>(null);
  const alive = useRef(true);
  const threadRef = useRef(thread);
  threadRef.current = thread;
  const historyRef = useRef(history);
  historyRef.current = history;
  const conversationRef = useRef(conversationId);
  conversationRef.current = conversationId;

  const stopPolling = useCallback(() => {
    if (pollTimer.current !== null) window.clearTimeout(pollTimer.current);
    pollTimer.current = null;
    setReconnecting(false);
  }, []);

  const pollTurn = useCallback(
    (turnId: string, startedAt = Date.now()) => {
      stopPolling();
      setReconnecting(true);
      const tick = async () => {
        if (!alive.current) return;
        try {
          const turn = await api.get<TurnBody>(`/ask/conversations/${conversationRef.current}/turns/${turnId}`);
          if (!alive.current) return;
          if (turn.status === "completed" || turn.status === "failed") {
            dispatch({ type: "snapshot", turn });
            setReconnecting(false);
            return;
          }
        } catch (error) {
          if (error instanceof ApiError && error.status === 404) {
            dispatch({ type: "connection_lost" });
            setReconnecting(false);
            return;
          }
        }
        const wait = Date.now() - startedAt >= POLL_SLOW_AFTER_MS ? POLL_SLOW_MS : POLL_FAST_MS;
        pollTimer.current = window.setTimeout(tick, wait);
      };
      pollTimer.current = window.setTimeout(tick, POLL_FAST_MS);
    },
    [stopPolling],
  );

  const runTurn = useCallback(
    async (text: string) => {
      const clientTurnId = crypto.randomUUID();
      stopPolling();
      abort.current?.abort();
      const controller = new AbortController();
      abort.current = controller;
      dispatch({ type: "send", id: clientTurnId, text });
      let turnId: string | null = null;
      let finished = false;
      try {
        const response = await api.openStream(
          `/ask/conversations/${conversationRef.current}/turns/stream`,
          { client_turn_id: clientTurnId, text },
          controller.signal,
        );
        const reader = response.body?.getReader();
        if (!reader) throw new Error("no stream");
        const decoder = new TextDecoder();
        let buffer = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const parsed = parseSse(buffer);
          buffer = parsed.rest;
          for (const event of parsed.events) {
            if (event.type === "turn") turnId = String(event.turn_id);
            if (event.type === "done") finished = true;
            dispatch({ type: "event", event });
          }
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError) {
          dispatch({ type: "event", event: { type: "error", code: `http_${error.status}`, retryable: error.status >= 500 } });
          return;
        }
      }
      if (controller.signal.aborted || finished) return;
      dispatch({ type: "connection_lost" });
      if (turnId) pollTurn(turnId);
    },
    [pollTurn, stopPolling],
  );

  const send = useCallback(
    (text: string) => {
      const clean = text.trim();
      if (!clean || isBusy(threadRef.current)) return;
      void runTurn(clean);
    },
    [runTurn],
  );

  const stop = useCallback(() => {
    abort.current?.abort();
    stopPolling();
    dispatch({ type: "stopped" });
  }, [stopPolling]);

  const retry = useCallback(() => {
    const messages = threadRef.current.messages;
    const failed = messages[messages.length - 1];
    if (!failed || failed.role !== "assistant" || !failed.question) return;
    dispatch({ type: "restore", messages: messages.slice(0, -2) });
    void runTurn(failed.question);
  }, [runTurn]);

  const confirm = useCallback(
    async (message: AskMessage) => {
      const card = message.confirm;
      if (!card) return;
      dispatch({ type: "confirm_status", status: "running" });
      try {
        const body = await api.post<{ status?: string; url?: string }>(
          `/ask/conversations/${conversationRef.current}/operations/${card.operationId}/confirm`,
          { revision: card.revision, contact_id: card.contactId },
        );
        const status = (body.status ?? "failed") as AskConfirm["status"];
        dispatch({ type: "confirm_status", status, url: body.url });
      } catch (error) {
        const uncertain = error instanceof ApiError && error.status === 409;
        dispatch({ type: "confirm_status", status: uncertain ? "uncertain" : "failed" });
      }
    },
    [],
  );

  const cancel = useCallback(async (message: AskMessage) => {
    const card = message.confirm;
    if (!card) return;
    try {
      await api.post(`/ask/conversations/${conversationRef.current}/operations/${card.operationId}/cancel`);
      dispatch({ type: "confirm_status", status: "cancelled" });
    } catch {
      // The card stays actionable if the cancel did not reach the server.
    }
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const body = await api.get<{ conversations: ConversationSummary[] }>("/ask/conversations");
      setHistory(body.conversations);
      setHistoryError(false);
    } catch {
      setHistoryError(true);
    }
  }, []);

  const openConversation = useCallback(
    async (id: string) => {
      stopPolling();
      abort.current?.abort();
      const body = await api.get<{ turns: TurnBody[] }>(`/ask/conversations/${id}`);
      rememberConversationId(id);
      setConversationId(id);
      conversationRef.current = id;
      dispatch({ type: "restore", messages: messagesFromTurns(body.turns) });
      const last = body.turns[body.turns.length - 1];
      if (last && (last.status === "pending" || last.status === "running")) pollTurn(last.turn_id);
    },
    [pollTurn, stopPolling],
  );

  const newConversation = useCallback(() => {
    stopPolling();
    abort.current?.abort();
    const id = crypto.randomUUID();
    rememberConversationId(id);
    setConversationId(id);
    conversationRef.current = id;
    dispatch({ type: "clear" });
    return id;
  }, [stopPolling]);

  const deleteConversation = useCallback(
    async (id: string) => {
      await api.delete(`/ask/conversations/${id}`);
      setHistory((rows) => (rows ? rows.filter((row) => row.id !== id) : rows));
      if (id === conversationRef.current) newConversation();
    },
    [newConversation],
  );

  const deleteCurrent = useCallback(async () => {
    await deleteConversation(conversationRef.current);
  }, [deleteConversation]);

  // Another device may have added turns to this conversation. When the tab comes back, pick them up.
  const refresh = useCallback(async () => {
    if (isBusy(threadRef.current) || !threadRef.current.messages.length) return;
    try {
      const body = await api.get<{ turns: TurnBody[] }>(`/ask/conversations/${conversationRef.current}`);
      const local = threadRef.current.messages.filter((m) => m.role === "user").length;
      if (alive.current && body.turns.length > local) dispatch({ type: "restore", messages: messagesFromTurns(body.turns) });
    } catch {
      // Offline or signed out: the conversation on screen is still correct.
    }
  }, []);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState !== "visible") return;
      void refresh();
      if (historyRef.current !== null) void loadHistory();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [refresh, loadHistory]);

  const clearAll = useCallback(async () => {
    await api.delete("/ask/conversations");
    setHistory([]);
    newConversation();
  }, [newConversation]);

  // Reload: bring back this tab's conversation, and keep waiting for a turn that was still running.
  useEffect(() => {
    alive.current = true;
    if (!initial.current?.fresh) void openConversation(conversationRef.current).catch(() => missing.current?.());
    return () => {
      alive.current = false;
      abort.current?.abort();
      stopPolling();
    };
    // Mount only: switching conversations goes through openConversation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    conversationId,
    thread,
    busy: isBusy(thread),
    reconnecting,
    history,
    historyError,
    send,
    stop,
    retry,
    confirm,
    cancel,
    loadHistory,
    openConversation,
    newConversation,
    deleteConversation,
    deleteCurrent,
    clearAll,
  };
}
