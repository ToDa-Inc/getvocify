export type AskSnapshot = {
  turnId: string;
  status: "pending" | "running" | "completed" | "failed";
  text: string;
};

export type AskView = {
  turnId: string | null;
  status: "idle" | AskSnapshot["status"];
  posts: number;
  waitedMs: number;
  text: string;
  notice: string | null;
  scroll: boolean;
  unread: boolean;
};

export function emptyAsk(): AskView {
  return {
    turnId: null,
    status: "idle",
    posts: 0,
    waitedMs: 0,
    text: "",
    notice: null,
    scroll: false,
    unread: false,
  };
}

export function notePosted(view: AskView, turn: AskSnapshot): AskView {
  if (view.turnId) return view;
  return {
    turnId: turn.turnId,
    status: turn.status,
    posts: view.posts + 1,
    waitedMs: 0,
    text: turn.text,
    notice: turn.status === "pending" ? "Esperando respuesta" : null,
    scroll: false,
    unread: false,
  };
}

export function noteTick(
  view: AskView,
  elapsedMs: number,
  fetched: AskSnapshot | null,
  readingAbove: boolean,
): AskView {
  if (!view.turnId) return view;
  const status = fetched?.status ?? view.status;
  const arrived = status === "completed" && view.status !== "completed";
  const waitedMs = view.waitedMs + elapsedMs;
  let notice = view.notice;
  if (status === "pending" && waitedMs >= 30000) {
    notice = "Sigue en curso. No se ha reenviado.";
  }
  if (status === "completed") notice = null;
  return {
    ...view,
    status,
    waitedMs,
    text: fetched?.text ?? view.text,
    posts: view.posts,
    notice,
    scroll: false,
    unread: readingAbove && arrived ? true : view.unread,
  };
}

export function reopenAsk(turnId: string, fetched: AskSnapshot): AskView {
  return {
    turnId,
    status: fetched.status,
    posts: 0,
    waitedMs: 0,
    text: fetched.text,
    notice: fetched.status === "pending" ? "Esperando respuesta" : null,
    scroll: false,
    unread: false,
  };
}

/** Closing Ask returns focus to the opener without forcing a scroll jump. */
export function closeAskPanel(view: AskView, openerControlId: string): { view: AskView; focusId: string } {
  return { view: { ...view, scroll: false }, focusId: openerControlId };
}
