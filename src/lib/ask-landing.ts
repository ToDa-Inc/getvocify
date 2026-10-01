/**
 * Which Ask conversation a screen starts on. A `?c=` link is read from the server and only
 * remembered for the tab once it was read, so a dead link never becomes the tab's conversation.
 * Without a link, the tab's last conversation is read back only when the caller wants it (the
 * floating sheet does; Inicio's home does not, it starts every question fresh).
 */
export type Landing = {
  id: string;
  /** Read this conversation's turns from the server on mount. */
  fetch: boolean;
  /** Store `id` as the tab's conversation now. */
  remember: boolean;
  /** Where to land if the linked conversation cannot be read. */
  fallback: string | null;
};

export function landingConversation(input: {
  linked: string | null;
  stored: string | null;
  restoreStored: boolean;
  newId: string;
}): Landing {
  if (input.linked) return { id: input.linked, fetch: true, remember: false, fallback: input.stored ?? input.newId };
  if (input.stored) return { id: input.stored, fetch: input.restoreStored, remember: false, fallback: null };
  return { id: input.newId, fetch: false, remember: true, fallback: null };
}

/** A question asked from home always opens a new conversation; in the chat it continues the one on screen. */
export function homeSendConversation(mode: "home" | "chat", current: string, fresh: () => string): string {
  return mode === "home" ? fresh() : current;
}
