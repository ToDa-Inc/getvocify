import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useAskConversation } from "@/features/ask/hooks/useAskConversation";
import { homeSendConversation } from "@/lib/ask-landing";

const PARAM = "c";

/** An open dialog, menu or the floating Ask sheet owns Esc: closing it must not also leave the chat. */
function overlayOpen() {
  return Boolean(
    document.querySelector(
      '[role="dialog"][data-state="open"], [role="alertdialog"][data-state="open"], [role="menu"][data-state="open"], .ask-sheet',
    ),
  );
}

/**
 * Inicio is the chat: home until a question is sent, then the thread. `?c=<id>` is the chat, so a
 * reload, a shared link or Back lands where the person was; Esc and "Nuevo" go home with a new
 * conversation ready. A question asked from home always starts a new conversation.
 */
export function useHomeChat() {
  const [params, setParams] = useSearchParams();
  const linked = params.get(PARAM);
  const [landing] = useState(linked);
  const gone = useRef<() => void>(() => undefined);
  // Only a `?c=` link is read back; home never reopens the tab's last conversation.
  const conversation = useAskConversation({ restoreId: landing, restoreStored: false, onMissing: () => gone.current() });
  const mode: "home" | "chat" = linked ? "chat" : "home";
  const { conversationId, newConversation, openConversation, send: ask } = conversation;
  const current = useRef(conversationId);
  current.current = conversationId;

  const setLinked = useCallback(
    (id: string | null, replace: boolean) => {
      setParams(
        (previous) => {
          const next = new URLSearchParams(previous);
          if (id) next.set(PARAM, id);
          else next.delete(PARAM);
          return next;
        },
        { replace },
      );
    },
    [setParams],
  );

  const reset = useCallback(() => {
    newConversation();
    setLinked(null, true);
  }, [newConversation, setLinked]);

  const send = useCallback(
    (text: string) => {
      if (!text.trim()) return;
      const id = homeSendConversation(mode, current.current, newConversation);
      ask(text);
      if (mode === "home") setLinked(id, false);
    },
    [mode, newConversation, ask, setLinked],
  );

  const open = useCallback(
    async (id: string) => {
      if (await openConversation(id)) setLinked(id, true);
    },
    [openConversation, setLinked],
  );

  gone.current = () => {
    if (landing) setLinked(null, true);
  };

  // A link to another conversation (reload, Back/Forward, a shared URL) opens it; a dead one goes home.
  useEffect(() => {
    if (!linked || linked === current.current) return;
    openConversation(linked).catch(() => setLinked(null, true));
  }, [linked, openConversation, setLinked]);

  useEffect(() => {
    if (mode !== "chat") return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented || event.isComposing || overlayOpen()) return;
      reset();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mode, reset]);

  return { mode, conversation, send, reset, open };
}
