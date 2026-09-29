import type { AskEvent } from "./ask-sse.ts";
import { askCallTargets, type AskCallTarget } from "./ask-calls.ts";

export type AskEvidence = {
  id: string;
  memo_id?: string;
  quote: string;
  speaker?: string | null;
  at?: string;
  rep?: string;
};
export type AskStep = {
  id: string;
  tool: string;
  status: "running" | "ok" | "failed";
  coverage?: string | null;
  n?: number | null;
};
export type AskCoverageNote = { level: "partial" | "forbidden" | "unavailable" | "period"; n?: number; n_analysed?: number; unit?: string; period_days?: number };
export type AskConfirm = {
  operationId: string;
  revision: number;
  contactId: string;
  summary: string;
  status: "proposed" | "running" | "succeeded" | "failed" | "uncertain" | "cancelled";
  url?: string;
};
export type AskChoiceOption = { id: string; label: string };

export type AskMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  /** sending: request out, nothing back. working: tools running. streaming: text arriving. pending: reader lost, turn still runs. */
  phase: "sending" | "working" | "streaming" | "pending" | "done" | "failed";
  turnId?: string;
  question?: string;
  steps: AskStep[];
  evidence: AskEvidence[];
  coverageNote: AskCoverageNote | null;
  /** Contacts the server chose to call, with a Call action. Built from tool results, never from the model's words. */
  callTargets: AskCallTarget[];
  confirm: AskConfirm | null;
  choices: AskChoiceOption[];
  retryable: boolean;
  /** The reader pressed Stop. The server still finishes the turn; a reload shows the full answer. */
  stopped?: boolean;
};

export type AskThread = { messages: AskMessage[] };

export type AskAction =
  | { type: "send"; id: string; text: string }
  | { type: "event"; event: AskEvent }
  | { type: "connection_lost" }
  | { type: "stopped" }
  | { type: "snapshot"; turn: TurnBody }
  | { type: "confirm_status"; status: AskConfirm["status"]; url?: string }
  | { type: "restore"; messages: AskMessage[] }
  | { type: "clear" };

export type TurnBody = {
  turn_id: string;
  status: "pending" | "running" | "completed" | "failed";
  text: string;
  question?: string | null;
  evidence?: AskEvidence[];
  coverage_note?: AskCoverageNote | null;
  call_targets?: AskCallTarget[];
  choices?: AskChoiceOption[];
  confirmation?: { operation_id?: string; revision?: number; contact_id?: string; applied?: boolean; cancelled?: boolean; state?: string; url?: string } | null;
};

export const emptyThread = (): AskThread => ({ messages: [] });

const EVIDENCE_TOKEN = /\s?\[(?:ev|pb)-[A-Za-z0-9_-]*\]?/g;

/** While text streams the server has not numbered citations yet. Hide the raw tokens until `final`. */
export function displayText(text: string): string {
  return text.replace(EVIDENCE_TOKEN, "").replace(/\s?\[(?:ev|pb)-[A-Za-z0-9_-]*$/, "");
}

function assistant(id: string, question: string): AskMessage {
  return {
    id,
    role: "assistant",
    text: "",
    phase: "sending",
    question,
    steps: [],
    evidence: [],
    coverageNote: null,
    callTargets: [],
    confirm: null,
    choices: [],
    retryable: false,
  };
}

function patchLast(thread: AskThread, patch: (m: AskMessage) => AskMessage): AskThread {
  const i = thread.messages.length - 1;
  if (i < 0 || thread.messages[i].role !== "assistant") return thread;
  const messages = thread.messages.slice();
  messages[i] = patch(messages[i]);
  return { messages };
}

function confirmFrom(e: AskEvent, summary: string): AskConfirm | null {
  if (typeof e.operation_id !== "string" || typeof e.contact_id !== "string") return null;
  return { operationId: e.operation_id, revision: Number(e.revision ?? 1), contactId: e.contact_id, summary, status: "proposed" };
}

function applyEvent(m: AskMessage, e: AskEvent): AskMessage {
  switch (e.type) {
    case "turn":
      return { ...m, turnId: String(e.turn_id) };
    case "state":
      return m.phase === "sending" ? { ...m, phase: "working" } : m;
    case "tool_start":
      return {
        ...m,
        phase: "working",
        steps: [...m.steps, { id: String(e.call_id), tool: String(e.tool), status: "running" }],
      };
    case "tool_result":
      return {
        ...m,
        steps: m.steps.map((s) =>
          s.id === e.call_id
            ? { ...s, status: e.ok === false ? "failed" : "ok", coverage: e.coverage as string | null, n: e.n as number | null }
            : s,
        ),
      };
    case "content":
      return { ...m, phase: "streaming", text: m.text + String(e.delta ?? "") };
    case "content_reset":
      return { ...m, text: "" };
    case "final":
      return {
        ...m,
        phase: "done",
        text: String(e.text ?? m.text),
        evidence: (e.evidence as AskEvidence[]) ?? [],
        coverageNote: (e.coverage_note as AskCoverageNote) ?? null,
        callTargets: askCallTargets({ call_targets: e.call_targets as AskCallTarget[] | undefined }),
      };
    case "choices":
      return { ...m, choices: (e.options as AskChoiceOption[]) ?? [] };
    case "confirm":
      return { ...m, confirm: confirmFrom(e, String(e.summary ?? m.text)) };
    case "pending":
      return { ...m, phase: "pending" };
    case "error":
      return { ...m, phase: "failed", retryable: e.retryable !== false };
    case "done":
      return m.phase === "streaming" || m.phase === "working" || m.phase === "sending"
        ? { ...m, phase: e.status === "failed" ? "failed" : "done" }
        : m;
    default:
      return m;
  }
}

function fromSnapshot(m: AskMessage, t: TurnBody): AskMessage {
  if (t.status === "failed") return { ...m, phase: "failed", retryable: true, turnId: t.turn_id };
  if (t.status !== "completed") return { ...m, phase: "pending", turnId: t.turn_id };
  const c = t.confirmation;
  let confirm: AskConfirm | null = null;
  if (c?.operation_id && c.contact_id && !c.cancelled) {
    confirm = {
      operationId: c.operation_id,
      revision: c.revision ?? 1,
      contactId: c.contact_id,
      summary: t.text,
      status: c.applied ? "succeeded" : c.state === "failed" || c.state === "uncertain" ? c.state : "proposed",
      url: c.url,
    };
  }
  return {
    ...m,
    phase: "done",
    turnId: t.turn_id,
    text: t.text,
    evidence: t.evidence ?? [],
    coverageNote: t.coverage_note ?? null,
    callTargets: askCallTargets(t),
    choices: t.choices ?? [],
    confirm,
  };
}

export function reduceThread(thread: AskThread, action: AskAction): AskThread {
  switch (action.type) {
    case "send":
      return {
        messages: [
          ...thread.messages,
          { ...assistant("", ""), id: `${action.id}-u`, role: "user", text: action.text, phase: "done" },
          assistant(action.id, action.text),
        ],
      };
    case "event":
      return patchLast(thread, (m) => applyEvent(m, action.event));
    case "connection_lost":
      // A turn that reached the server keeps running there. Only a turn that never arrived is a failure.
      return patchLast(thread, (m) =>
        m.phase === "done" || m.phase === "failed" ? m : m.turnId ? { ...m, phase: "pending" } : { ...m, phase: "failed", retryable: true },
      );
    case "stopped":
      return patchLast(thread, (m) =>
        m.phase === "done" || m.phase === "failed" ? m : { ...m, phase: "done", stopped: true, retryable: true },
      );
    case "snapshot":
      return patchLast(thread, (m) => fromSnapshot(m, action.turn));
    case "confirm_status":
      return patchLast(thread, (m) =>
        m.confirm ? { ...m, confirm: { ...m.confirm, status: action.status, url: action.url ?? m.confirm.url } } : m,
      );
    case "restore":
      return { messages: action.messages };
    case "clear":
      return emptyThread();
  }
}

/** Rebuild the thread from stored turns (history, or a reload). */
export function messagesFromTurns(turns: TurnBody[]): AskMessage[] {
  const out: AskMessage[] = [];
  for (const t of turns) {
    const question = t.question ?? "";
    out.push({ ...assistant(`${t.turn_id}-u`, question), role: "user", text: question, phase: "done" });
    out.push(fromSnapshot(assistant(t.turn_id, question), t));
  }
  return out;
}

export function isBusy(thread: AskThread): boolean {
  const last = thread.messages[thread.messages.length - 1];
  return !!last && last.role === "assistant" && (last.phase === "sending" || last.phase === "working" || last.phase === "streaming" || last.phase === "pending");
}
