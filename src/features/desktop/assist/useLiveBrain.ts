import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { playbooksApi } from "@/features/playbooks/api";
import { getDesktopBridge } from "@/lib/desktop-host";
import { api } from "@/shared/lib/api-client";
import { assistContext, BACKSTOP_MS, turnCheck } from "@/lib/live-assist";
import {
  buildCardReading,
  buildReading,
  clearProgressCursor,
  contactBrief,
  liveBrainPayload,
  nextAsk,
  longTurnDue,
  OFFLINE_AFTER,
  playbookView,
  pointSays,
  repReadingDue,
  repWords,
  resetForType,
  spottedDraft,
  streamedPoints,
  toWireTurns,
  turnObjection,
  turnsUpTo,
  type LiveBrainAsks,
  type LiveDraft,
  type LiveReason,
  type ReadMark,
  type ReadingCall,
  type ReadingTarget,
} from "@/lib/live-brain";
import type { MeetingDisplayTurn } from "@/lib/meeting-transcript";
import { applyPoints, applyProgress, applyRewrite, dismissPoint, emptyLiveState, tick, untick } from "../../../../shared/live-call/state.js";
import { createReader } from "../../../../shared/live-call/reader.js";
import { EVENTS_PER_REQUEST, LiveBrainError, pointsResult, postEvents, readCard, readSlow, streamPoints, type LiveUiEvent } from "./liveBrainApi";
import { useProspectPause } from "./useLiveAssist";
import { readTurn } from "./sources";

/** How the island's push is throttled: a change waits at most this long (many tokens make one push). */
const PUSH_MS = 250;
/** UI events wait at most this long before they are sent together. */
const EVENTS_MS = 5000;
/** The UI events the backend logs (contract §2.4); anything else the island sends is not ours to log. */
const EVENT_KINDS = new Set([
  "shown", "dismissed", "reopened", "rewrite", "ask_step", "tick", "untick", "responder", "bubble",
  "open_recap", "open_steps", "open_brief", "marker_shown", "marker_seen",
]);
const POINT_EVENTS = new Set(["shown", "dismissed", "reopened", "rewrite"]);
const STEP_EVENTS = new Set(["ask_step", "tick", "untick"]);

export type LiveBrainCall = {
  callId?: string | null;
  contactId?: string | null;
  /** The contact's name as the CRM has it: the island's contact button. */
  contactName?: string | null;
  callMode?: "softphone" | "meeting";
  typeKey?: string | null;
  /** The type's name as the rep sees it. */
  typeLabel?: string | null;
  /** Their side's audio level (0–1): when it goes quiet is when they may have finished. */
  prospectLevel?: number;
};

type Spec = { reason: LiveReason; mark: ReadMark; typeChanged?: boolean; objection?: string | null };
type Kind = "step" | "data" | "goal";
type ResultPoint = { id: string };

const NO_ASKS: LiveBrainAsks = { responder: null, recap: null, step: null, rewrite: null };

/**
 * The live call assistant on the dashboard (spec 2026-10-16-live-call-assistant-design.md): holds the LiveState, reads at
 * the spec's checkpoints, merges what comes back with shared/live-call/state.js, and pushes the state to the island.
 * Only runs behind the company flag; with it off nothing here is active and today's live help (useLiveAssist) is.
 *
 * `enabled`: the flag, live help on, the call recording and not paused. `flag`: only the flag (the island is told when help is off).
 * `sayView`: the company flag LIVE_SAY_VIEW_ENABLED: the island draws "Qué decir" and the brain may suggest going deeper.
 * `card`: the company flag LIVE_CARD_ENABLED (pilot, with "Qué decir"): the automatic readings go to the strategic card, ONE
 * card or nothing (backend services/copilot/live_card.py); Responder and the rep's other asks stay with the points producer.
 */
export function useLiveBrain(
  turns: MeetingDisplayTurn[],
  opts: { flag: boolean; enabled: boolean; helpOn: boolean; sayView?: boolean; card?: boolean },
  call: LiveBrainCall = {},
) {
  const { flag, enabled, helpOn } = opts;
  const sayView = Boolean(opts.sayView);
  const cardMode = sayView && Boolean(opts.card);
  const callId = call.callId ?? null;
  const active = flag && enabled && Boolean(callId);

  const stateRef = useRef(emptyLiveState(callId ?? ""));
  const [state, setViewState] = useState(stateRef.current);
  const [drafts, setDrafts] = useState<LiveDraft[]>([]);
  /** What the turn check just spotted (a question, an objection): its card shows at once and the brain writes into it. */
  const [spotted, setSpotted] = useState<LiveDraft | null>(null);
  const [reading, setReading] = useState({ points: false, progress: false, recap: false });
  const [offlineSince, setOfflineSince] = useState<number | null>(null);
  const [asks, setAsks] = useState<LiveBrainAsks>(NO_ASKS);
  const [typeChanged, setTypeChanged] = useState(false);
  /** Point ids whose words were already on screen as a draft: they take the card's place without entering again. */
  const [fromDraft, setFromDraft] = useState<string[]>([]);

  const turnsRef = useRef(turns);
  turnsRef.current = turns;
  const callRef = useRef(call);
  callRef.current = call;
  const activeRef = useRef(active);
  activeRef.current = active;
  const sayViewRef = useRef(sayView);
  sayViewRef.current = sayView;
  const cardRef = useRef(cardMode);
  cardRef.current = cardMode;

  const commit = useCallback((next: typeof stateRef.current) => {
    stateRef.current = next;
    setViewState(next);
  }, []);
  const mutate = useCallback((fn: (state: typeof stateRef.current) => typeof stateRef.current) => commit(fn(stateRef.current)), [commit]);

  // ---- connection: two failed readings in a row and the views say so; a good one clears it ----
  const failuresRef = useRef(0);
  const lastOkRef = useRef(Date.now());
  const succeeded = () => {
    failuresRef.current = 0;
    lastOkRef.current = Date.now();
    setOfflineSince(null);
  };
  const failed = () => {
    failuresRef.current += 1;
    if (failuresRef.current >= OFFLINE_AFTER) setOfflineSince(lastOkRef.current);
  };
  /** A reading the backend refused (4xx: a reason or endpoint it does not have yet) is not a lost connection. */
  const refused = (error: unknown) => {
    const status = (error as { status?: unknown })?.status;
    return typeof status === "number" && status >= 400 && status < 500;
  };

  // ---- what the rep did, logged (contract §2.4): batched, fire-and-forget ----
  const eventsRef = useRef<{ callId: string | null; queue: LiveUiEvent[]; timer: number | undefined; off: boolean }>({
    callId: null,
    queue: [],
    timer: undefined,
    off: false,
  });
  const flushEvents = useCallback(() => {
    const box = eventsRef.current;
    window.clearTimeout(box.timer);
    box.timer = undefined;
    const { callId: id, queue } = box;
    box.queue = [];
    if (!id || box.off) return;
    for (let at = 0; at < queue.length; at += EVENTS_PER_REQUEST) {
      void postEvents(id, queue.slice(at, at + EVENTS_PER_REQUEST)).then((status) => {
        // A backend without the endpoint: nothing more is sent for this call.
        if ((status === 404 || status === 405) && eventsRef.current.callId === id) eventsRef.current.off = true;
      });
    }
  }, []);
  const logEvent = useCallback(
    (kind: string, fields: Omit<LiveUiEvent, "kind" | "at"> = {}) => {
      const box = eventsRef.current;
      if (!activeRef.current || !box.callId || box.off || !EVENT_KINDS.has(kind)) return;
      box.queue.push({ kind, at: new Date().toISOString(), ...fields });
      if (box.queue.length >= EVENTS_PER_REQUEST) flushEvents();
      else if (box.timer === undefined) box.timer = window.setTimeout(flushEvents, EVENTS_MS);
    },
    [flushEvents],
  );

  // ---- the readings ----
  const askedRef = useRef<{ points: LiveReason | null; progress: LiveReason | null }>({ points: null, progress: null });
  const controllersRef = useRef<{ points: AbortController | null; progress: AbortController | null; recap: AbortController | null; card: AbortController | null }>({
    points: null,
    progress: null,
    recap: null,
    card: null,
  });
  /** The previous card reading's `read_t` (seconds into the call): a long stretch is read once per stretch. */
  const lastCardReadRef = useRef<number | null>(null);
  const typeChangedRef = useRef(false);
  const seqRef = useRef({ responder: 0, recap: 0, step: 0, rewrite: 0 });
  /** Responder about one tapped bubble: the turn it reads (kept with the ask, like its reason). */
  const askedTurnRef = useRef<string | null>(null);
  const oneShotRef = useRef<{ step: AbortController | null; rewrite: AbortController | null }>({ step: null, rewrite: null });

  const readingCall = (): ReadingCall => ({
    callId: callRef.current.callId ?? "",
    callMode: callRef.current.callMode ?? "meeting",
    contactId: callRef.current.contactId,
    typeKey: callRef.current.typeKey,
    typeLabel: callRef.current.typeLabel,
  });

  const runPoints = async (spec: Spec, options: { asked: boolean }) => {
    const reason = options.asked && askedRef.current.points ? askedRef.current.points : spec.reason;
    askedRef.current.points = null;
    const focusTurn = reason === "responder" ? askedTurnRef.current : null;
    askedTurnRef.current = null;
    const all = toWireTurns(turnsRef.current);
    // Responder about a tapped bubble reads that sentence: the call up to it, from it.
    const wire = focusTurn ? turnsUpTo(all, focusTurn) ?? all : all;
    const responder = reason === "responder";
    if (!activeRef.current || !wire.length) {
      if (responder) setAsks((a) => ({ ...a, responder: { seq: seqRef.current.responder, status: "nothing", point_id: null, next: null } }));
      return;
    }
    const controller = new AbortController();
    controllersRef.current.points = controller;
    const body = buildReading({
      call: readingCall(),
      turns: wire,
      state: stateRef.current,
      reason,
      mark: spec.mark,
      producer: "points",
      sayView: sayViewRef.current,
      focusTurn: focusTurn && wire !== all ? focusTurn : null,
    });
    setReading((r) => ({ ...r, points: true }));
    let text = "";
    let result: (Record<string, unknown> & { points?: ResultPoint[] }) | null = null;
    let lastDrafts: LiveDraft[] = [];
    try {
      await streamPoints(
        body,
        (event) => {
          if (event.type === "token") {
            text += event.text;
            lastDrafts = streamedPoints(text);
            setDrafts(lastDrafts);
          } else if (event.type === "result") {
            result = event;
          } else if (event.type === "error") {
            throw new LiveBrainError(502, event.message ?? "the live brain could not answer");
          }
        },
        controller.signal,
      );
      if (!result) throw new LiveBrainError(502, "no result");
      succeeded();
      const before = stateRef.current;
      const merged = applyPoints(before, result, { asked: responder });
      commit(merged);
      for (const point of merged.points) {
        const was = before.points.find((p: ResultPoint) => p.id === point.id);
        if (was && was.outcome !== "open" && point.outcome === "open") logEvent("reopened", { point_id: point.id });
      }
      const said = new Set(lastDrafts.map((d) => d.say).filter(Boolean));
      const landed = (result.points ?? []).map((p: { id: string }) => p.id).filter((id: string) => merged.points.some((p: { id: string }) => p.id === id));
      setFromDraft((ids) => [
        ...ids,
        ...landed.filter((id: string) => said.has(pointSays(merged.points.find((p: { id: string }) => p.id === id) ?? { answer: null, fallback: null }))),
      ]);
      if (responder) {
        const found = landed.length ? landed[landed.length - 1] : null;
        // Nothing to answer: the missing item that matters most, with its question (null until the backend gives one).
        const next = found ? null : nextAsk((result as Record<string, unknown>).next);
        setAsks((a) => ({ ...a, responder: { seq: seqRef.current.responder, status: found ? "found" : "nothing", point_id: found, next } }));
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      failed();
      if (responder) setAsks((a) => ({ ...a, responder: null }));
      if (!(error instanceof LiveBrainError)) console.warn("live brain: points reading failed", error);
    } finally {
      if (controllersRef.current.points === controller) controllersRef.current.points = null;
      setDrafts([]);
      // The reading wrote its card (or found nothing to answer): what was spotted has done its job.
      setSpotted(null);
      setReading((r) => ({ ...r, points: false }));
    }
  };

  const runProgress = async (spec: Spec, options: { asked: boolean }) => {
    const reason = options.asked && askedRef.current.progress ? askedRef.current.progress : spec.reason;
    askedRef.current.progress = null;
    const wire = toWireTurns(turnsRef.current);
    if (!activeRef.current || !wire.length) return;
    const controller = new AbortController();
    controllersRef.current.progress = controller;
    const changed = Boolean(spec.typeChanged) || typeChangedRef.current;
    const body = buildReading({
      call: readingCall(),
      turns: wire,
      state: stateRef.current,
      reason,
      mark: spec.mark,
      producer: "progress",
      typeChanged: changed,
      sayView: sayViewRef.current,
    });
    setReading((r) => ({ ...r, progress: true }));
    try {
      const result = await readSlow<Record<string, unknown>>("progress", body, controller.signal);
      succeeded();
      mutate((s) => applyProgress(s, result));
      if (changed) {
        typeChangedRef.current = false;
        setTypeChanged(false);
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      failed();
      if (!(error instanceof LiveBrainError) && !(error as { status?: number })?.status) console.warn("live brain: progress reading failed", error);
    } finally {
      if (controllersRef.current.progress === controller) controllersRef.current.progress = null;
      setReading((r) => ({ ...r, progress: false }));
    }
  };

  /** A strategic card reading: ONE card (the one still open fades) or nothing, merged like a points result. */
  const runCard = async (spec: Spec) => {
    const wire = toWireTurns(turnsRef.current);
    if (!activeRef.current || !wire.length) return;
    const controller = new AbortController();
    controllersRef.current.card = controller;
    const body = buildCardReading({
      call: readingCall(),
      turns: wire,
      state: stateRef.current,
      reason: spec.reason,
      mark: spec.mark,
      sayView: sayViewRef.current,
      objection: spec.objection ?? null,
      lastReadT: lastCardReadRef.current,
    });
    setReading((r) => ({ ...r, points: true }));
    try {
      const result = await readCard(body, controller.signal);
      succeeded();
      if (typeof result.read_t === "number" && !String(result.event ?? "").startsWith("skipped")) lastCardReadRef.current = result.read_t;
      if (result.points?.length || result.closed?.length) commit(applyPoints(stateRef.current, result));
    } catch (error) {
      if (controller.signal.aborted) return;
      if (!refused(error)) failed();
    } finally {
      if (controllersRef.current.card === controller) controllersRef.current.card = null;
      setReading((r) => ({ ...r, points: false }));
    }
  };

  /**
   * A reading that only answers the rep (a rewrite, a step question): the latest of each kind wins, it adds no points and
   * moves no cursor. A backend that does not know the reason yet answers 4xx: then there is just nothing new.
   */
  const readOnce = async (which: "rewrite" | "step", reason: LiveReason, target: ReadingTarget): Promise<Record<string, unknown> | null> => {
    oneShotRef.current[which]?.abort();
    const wire = toWireTurns(turnsRef.current);
    if (!activeRef.current || !wire.length) return null;
    const controller = new AbortController();
    oneShotRef.current[which] = controller;
    try {
      const body = buildReading({ call: readingCall(), turns: wire, state: stateRef.current, reason, producer: "points", target, sayView: sayViewRef.current });
      const result = await pointsResult(body, controller.signal);
      succeeded();
      return result;
    } catch (error) {
      if (controller.signal.aborted) throw error;
      if (!refused(error)) failed();
      return null;
    } finally {
      if (oneShotRef.current[which] === controller) oneShotRef.current[which] = null;
    }
  };

  // The readers see the latest closures: a reading is built when it starts, not when it was asked for.
  const runPointsRef = useRef(runPoints);
  runPointsRef.current = runPoints;
  const runProgressRef = useRef(runProgress);
  runProgressRef.current = runProgress;
  const runCardRef = useRef(runCard);
  runCardRef.current = runCard;
  const readers = useRef<{ points: ReturnType<typeof createReader>; progress: ReturnType<typeof createReader>; card: ReturnType<typeof createReader> } | null>(null);
  if (!readers.current) {
    readers.current = {
      points: createReader((spec: Spec, o: { asked: boolean }) => runPointsRef.current(spec, o)),
      progress: createReader((spec: Spec, o: { asked: boolean }) => runProgressRef.current(spec, o)),
      card: createReader((spec: Spec) => runCardRef.current(spec)),
    };
  }

  // ---- checkpoints ----
  const markRef = useRef<ReadMark>(null);
  const lastPointsAtRef = useRef<number | null>(null);
  const repReadRef = useRef({ words: 0, at: null as number | null });

  /** A checkpoint reading: points (or the strategic card) and progress (a long turn reads only points). */
  const read = (reason: LiveReason, mark: ReadMark, only?: "points", objection?: string | null) => {
    lastPointsAtRef.current = Date.now();
    repReadRef.current = { words: repWords(turnsRef.current), at: Date.now() };
    if (cardRef.current) readers.current!.card.request({ reason, mark, objection: objection ?? null });
    else readers.current!.points.request({ reason, mark });
    if (!only) readers.current!.progress.request({ reason, mark });
  };

  const { paused, quietSinceRef: _quiet } = useProspectPause(active ? call.prospectLevel : undefined);
  void _quiet;
  const lastKeyRef = useRef("");
  const checkRef = useRef<AbortController | null>(null);
  const backstopRef = useRef<number | undefined>(undefined);

  const found = active ? assistContext(turns, markRef.current) : null;
  const key = found?.key ?? "";

  const check = (ctx: NonNullable<typeof found>, final: boolean) => {
    lastKeyRef.current = ctx.key;
    checkRef.current?.abort();
    const controller = new AbortController();
    checkRef.current = controller;
    void readTurn(
      { ...ctx, ...(callRef.current.callId && { callId: callRef.current.callId }), ...(callRef.current.typeKey && { typeKey: callRef.current.typeKey }) },
      controller.signal,
    ).then((turn) => {
      if (controller.signal.aborted) return;
      const previous = markRef.current;
      // A question or an objection: the rep sees its card now, the answer follows (a turn not finished says "Preparando").
      // The strategic card may stay silent: nothing shows before it decides.
      if (!cardRef.current) setSpotted(spottedDraft(turn, ctx.latestTurn));
      if (turn && turn.finished === false && !final) {
        // A breath, not an end: a long turn is read every LONG_TURN_MS; otherwise wait and ask again, final.
        if (longTurnDue({ lastReadAt: lastPointsAtRef.current, now: Date.now() })) {
          markRef.current = { turnKey: ctx.turnKey, length: ctx.length };
          read("long_turn", previous, "points");
        }
        backstopRef.current = window.setTimeout(() => check(ctx, true), BACKSTOP_MS);
        return;
      }
      markRef.current = { turnKey: ctx.turnKey, length: ctx.length };
      read("turn_end", previous, undefined, turnObjection(turn));
    });
  };

  useEffect(() => {
    if (!found || key === lastKeyRef.current) return;
    const plan = turnCheck({ settled: found.settled, paused });
    const timer = window.setTimeout(() => check(found, plan.final), plan.afterMs);
    return () => window.clearTimeout(timer);
    // The key captures every change in their words; found is derived from it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, paused]);
  useEffect(() => () => window.clearTimeout(backstopRef.current), [key]);

  // After the rep's turns: their lines may settle a point or tick a step. Nothing new shows then.
  const repTotal = repWords(turns);
  useEffect(() => {
    if (!active) return;
    const timer = window.setTimeout(() => {
      const { words, at } = repReadRef.current;
      if (!repReadingDue({ words: repTotal, readWords: words, lastReadAt: at, now: Date.now() })) return;
      const open = stateRef.current.points.some((p: { outcome: string }) => p.outcome === "open" || p.outcome === "unanswered");
      repReadRef.current = { words: repTotal, at: Date.now() };
      readers.current!.progress.request({ reason: "rep_turn", mark: markRef.current });
      // The card producer decides in code whether the rep has held the floor long enough to read.
      if (cardRef.current) readers.current!.card.request({ reason: "rep_turn", mark: markRef.current });
      else if (open) readers.current!.points.request({ reason: "rep_turn", mark: markRef.current });
    }, 1500);
    return () => window.clearTimeout(timer);
  }, [repTotal, active]);

  // ---- the call's type ----
  const typeKey = call.typeKey ?? null;
  const typeRef = useRef<string | null>(typeKey);
  useEffect(() => {
    const before = typeRef.current;
    typeRef.current = typeKey;
    if (before === typeKey || !typeKey) return;
    if (before) {
      // Another playbook: it comes in as a whole and the whole call is read again under it.
      mutate(resetForType);
      typeChangedRef.current = true;
      setTypeChanged(true);
    } else {
      mutate(clearProgressCursor);
    }
    if (activeRef.current && turnsRef.current.length) readers.current!.progress.request({ reason: "turn_end", mark: null, typeChanged: Boolean(before) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [typeKey]);

  // ---- a new call, or help switched off ----
  useEffect(() => {
    controllersRef.current.points?.abort();
    controllersRef.current.progress?.abort();
    controllersRef.current.recap?.abort();
    controllersRef.current.card?.abort();
    oneShotRef.current.step?.abort();
    oneShotRef.current.rewrite?.abort();
    askedTurnRef.current = null;
    // The last call's events go out under its own id; this call starts its own.
    flushEvents();
    eventsRef.current = { callId, queue: [], timer: undefined, off: false };
    commit(emptyLiveState(callId ?? ""));
    markRef.current = null;
    lastKeyRef.current = "";
    lastPointsAtRef.current = null;
    lastCardReadRef.current = null;
    repReadRef.current = { words: 0, at: null };
    typeChangedRef.current = false;
    failuresRef.current = 0;
    lastOkRef.current = Date.now();
    seqRef.current = { responder: 0, recap: 0, step: 0, rewrite: 0 };
    setDrafts([]);
    setSpotted(null);
    setFromDraft([]);
    setAsks(NO_ASKS);
    setTypeChanged(false);
    setOfflineSince(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [callId]);

  useEffect(() => {
    if (active) return;
    checkRef.current?.abort();
    controllersRef.current.points?.abort();
    controllersRef.current.progress?.abort();
    controllersRef.current.card?.abort();
    oneShotRef.current.step?.abort();
    oneShotRef.current.rewrite?.abort();
    window.clearTimeout(backstopRef.current);
    flushEvents();
    setDrafts([]);
    setReading({ points: false, progress: false, recap: false });
  }, [active, flushEvents]);

  useEffect(
    () => () => {
      checkRef.current?.abort();
      controllersRef.current.points?.abort();
      controllersRef.current.progress?.abort();
      controllersRef.current.recap?.abort();
      controllersRef.current.card?.abort();
      oneShotRef.current.step?.abort();
      oneShotRef.current.rewrite?.abort();
      window.clearTimeout(backstopRef.current);
      flushEvents();
    },
    [flushEvents],
  );

  // ---- the rep's asks and marks ----
  /** Responder: reads the last minute; with `turnId`, only that bubble (the rep tapped it). */
  const responder = useCallback(
    (turnId?: string) => {
      if (!activeRef.current) return;
      seqRef.current.responder += 1;
      setAsks((a) => ({ ...a, responder: { seq: seqRef.current.responder, status: "reading", point_id: null, next: null } }));
      askedRef.current.points = "responder";
      askedTurnRef.current = turnId ?? null;
      logEvent(turnId ? "bubble" : "responder", turnId ? { detail: { turn_id: turnId } } : {});
      readers.current!.points.request({ reason: "responder", mark: null }, { asked: true });
    },
    [logEvent],
  );

  /** Another version of a point on screen; `version`: how many versions the island already has. */
  const rewrite = useCallback(
    async (pointId: string, version: number) => {
      if (!activeRef.current) return;
      const point = stateRef.current.points.find((p: ResultPoint) => p.id === pointId);
      seqRef.current.rewrite += 1;
      const seq = seqRef.current.rewrite;
      logEvent("rewrite", { point_id: pointId, detail: { version } });
      if (!point || !point.versions?.length) return setAsks((a) => ({ ...a, rewrite: { seq, point_id: pointId, status: "none" } }));
      setAsks((a) => ({ ...a, rewrite: { seq, point_id: pointId, status: "reading" } }));
      let result: Record<string, unknown> | null = null;
      try {
        result = await readOnce("rewrite", "rewrite", { point_id: pointId, version });
      } catch {
        return; // a newer rewrite took its place
      }
      const answer = result?.rewrite as { point_id?: string; version?: number; answer?: string | null } | null | undefined;
      const before = stateRef.current;
      const after = answer?.point_id === pointId ? applyRewrite(before, { point_id: pointId, version: answer.version ?? version, answer: answer.answer ?? null }) : before;
      if (after !== before) commit(after);
      setAsks((a) => (a.rewrite?.seq === seq ? { ...a, rewrite: { seq, point_id: pointId, status: after !== before ? "ready" : "none" } } : a));
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [commit, logEvent],
  );

  /** A question for one pending step or data item (the Pasos tap), written from the call. */
  const askStep = useCallback(
    async (kind: "step" | "data", id: string) => {
      if (!activeRef.current) return;
      seqRef.current.step += 1;
      const seq = seqRef.current.step;
      logEvent("ask_step", { step_kind: kind, step_id: id });
      setAsks((a) => ({ ...a, step: { seq, kind, id, status: "reading", question: null } }));
      let result: Record<string, unknown> | null = null;
      try {
        result = await readOnce("step", "ask_step", { kind, id });
      } catch {
        return;
      }
      const asked = result?.step_question as { kind?: string; id?: string; question?: string | null } | null | undefined;
      const question = asked?.id === id && typeof asked.question === "string" && asked.question.trim() ? asked.question.trim() : null;
      setAsks((a) => (a.step?.seq === seq ? { ...a, step: { seq, kind, id, status: "ready", question } } : a));
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [logEvent],
  );

  const preguntar = useCallback(() => {
    if (!activeRef.current) return;
    askedRef.current.progress = "preguntar";
    readers.current!.progress.request({ reason: "preguntar", mark: null }, { asked: true });
  }, []);

  const resumen = useCallback(async () => {
    if (!activeRef.current) return;
    controllersRef.current.recap?.abort();
    const controller = new AbortController();
    controllersRef.current.recap = controller;
    seqRef.current.recap += 1;
    const seq = seqRef.current.recap;
    const wire = toWireTurns(turnsRef.current);
    const upTo = wire.length ? wire[wire.length - 1] : null;
    setAsks((a) => ({ ...a, recap: { seq, status: "reading", up_to_t: upTo?.t ?? null, lines: [], unknown: [] } }));
    setReading((r) => ({ ...r, recap: true }));
    try {
      const body = buildReading({ call: readingCall(), turns: wire, state: stateRef.current, reason: "resumen", producer: "recap", sayView: sayViewRef.current });
      const result = await readSlow<{ lines?: string[]; unknown?: string[] }>("recap", body, controller.signal);
      succeeded();
      setAsks((a) => ({ ...a, recap: { seq, status: "ready", up_to_t: upTo?.t ?? null, lines: result.lines ?? [], unknown: result.unknown ?? [] } }));
    } catch {
      if (controller.signal.aborted) return;
      failed();
      setAsks((a) => ({ ...a, recap: null }));
    } finally {
      if (controllersRef.current.recap === controller) controllersRef.current.recap = null;
      setReading((r) => ({ ...r, recap: false }));
    }
  }, []);

  const tickItem = useCallback(
    (id: string, kind: Kind) => {
      mutate((s) => tick(s, id, kind));
      logEvent("tick", { step_kind: kind, step_id: id });
      // Ahora and Falta follow the rep's mark on the next reading.
      askedRef.current.progress = "preguntar";
      readers.current!.progress.request({ reason: "preguntar", mark: null }, { asked: true });
    },
    [mutate, logEvent],
  );
  const untickItem = useCallback(
    (id: string, kind: Kind) => {
      mutate((s) => untick(s, id, kind));
      logEvent("untick", { step_kind: kind, step_id: id });
    },
    [mutate, logEvent],
  );
  const dismiss = useCallback(
    (id: string) => {
      mutate((s) => dismissPoint(s, id));
      logEvent("dismissed", { point_id: id });
    },
    [mutate, logEvent],
  );

  /** An event the island logs on its own (what it showed, what the rep opened): its `id` goes where the kind says. */
  const islandEvent = useCallback(
    (action: { [key: string]: unknown }) => {
      const kind = typeof action.kind === "string" ? action.kind : "";
      const text = (value: unknown) => (typeof value === "string" && value ? value : undefined);
      const id = text(action.id);
      const fields: Omit<LiveUiEvent, "kind" | "at"> = {};
      const pointId = text(action.point_id) ?? (POINT_EVENTS.has(kind) ? id : undefined);
      const stepId = text(action.step_id) ?? (STEP_EVENTS.has(kind) ? id : undefined);
      if (pointId) fields.point_id = pointId;
      if (stepId) fields.step_id = stepId;
      if (action.step_kind === "step" || action.step_kind === "data" || action.step_kind === "goal") fields.step_kind = action.step_kind;
      const detail = action.detail && typeof action.detail === "object" ? { ...(action.detail as Record<string, unknown>) } : {};
      if (id && id !== pointId && id !== stepId) detail.id = id;
      if (Object.keys(detail).length) fields.detail = detail;
      logEvent(kind, fields);
    },
    [logEvent],
  );

  /** Closes the Responder ask once its point is dealt with by the view (the island reads `asks`). */
  const clearAsk = useCallback((which: "responder" | "recap") => setAsks((a) => ({ ...a, [which]: null })), []);

  // ---- what the island asks for ----
  const handlersRef = useRef({ responder, preguntar, resumen, tickItem, untickItem, dismiss, rewrite, askStep, islandEvent });
  handlersRef.current = { responder, preguntar, resumen, tickItem, untickItem, dismiss, rewrite, askStep, islandEvent };
  useEffect(() => {
    if (!flag) return;
    return getDesktopBridge()?.shell.onLiveAction?.((action) => {
      const h = handlersRef.current;
      const id = typeof action.id === "string" ? action.id : "";
      const kind = action.kind === "data" || action.kind === "goal" ? action.kind : "step";
      switch (action.type) {
        case "responder": return h.responder();
        case "preguntar": return h.preguntar();
        case "resumen": return void h.resumen();
        case "tick": return id ? h.tickItem(id, kind) : undefined;
        case "untick": return id ? h.untickItem(id, kind) : undefined;
        case "dismiss": return id ? h.dismiss(id) : undefined;
        case "rewrite": {
          const version = typeof action.version === "number" && Number.isFinite(action.version) ? Math.max(0, Math.floor(action.version)) : 1;
          return id ? void h.rewrite(id, version) : undefined;
        }
        case "ask_step": return id && (action.kind === "step" || action.kind === "data") ? void h.askStep(action.kind, id) : undefined;
        case "responder_turn": return typeof action.turn_id === "string" && action.turn_id ? h.responder(action.turn_id) : undefined;
        case "event": return h.islandEvent(action);
        default: return undefined;
      }
    });
  }, [flag]);

  // ---- the playbook's words for the ids ----
  const editor = useQuery({
    // The published version, the one the brain reads: a manager's pending draft would list steps the call does not have.
    queryKey: ["live-brain-playbook", typeKey, "live"],
    queryFn: () => playbooksApi.liveEditor(typeKey as string),
    enabled: flag && Boolean(typeKey),
    staleTime: 5 * 60_000,
    retry: false,
  });
  const playbook = useMemo(
    () =>
      typeKey
        ? playbookView({
            key: typeKey,
            name: call.typeLabel ?? state.progress.playbook?.name ?? null,
            hasPlaybook: state.progress.has_playbook || Boolean(editor.data?.steps?.length || editor.data?.qualification?.length),
            editor: editor.data ?? null,
            aids: state.progress.aids,
            partLists: state.progress.part_lists,
          })
        : null,
    [typeKey, call.typeLabel, state.progress.playbook, state.progress.has_playbook, state.progress.aids, state.progress.part_lists, editor.data],
  );

  // ---- the contact: who they are before this call (only what the CRM and earlier calls say) ----
  const contactId = call.contactId ?? null;
  const activity = useQuery({
    queryKey: ["live-brain-contact", contactId],
    queryFn: () => api.get<Parameters<typeof contactBrief>[1]>(`/contacts/${encodeURIComponent(contactId as string)}/recent-activity?connection_id=hubspot`),
    enabled: flag && Boolean(contactId),
    staleTime: 10 * 60_000,
    retry: false,
  });
  const contact = useMemo(() => contactBrief(call.contactName, contactId ? activity.data : null), [call.contactName, contactId, activity.data]);

  // ---- the island: the whole state, throttled and as changes ----
  const payload =
    flag && callId
      ? liveBrainPayload({
          on: helpOn, callId, state, playbook, reading, offlineSince, drafts: drafts.length ? drafts : spotted && helpOn ? [spotted] : [], asks, typeChanged,
          view: sayView ? "say" : "tabs", contact,
        })
      : null;
  const json = JSON.stringify(payload);
  const pushed = useRef<string | undefined>(undefined);
  const pushTimer = useRef<number | undefined>(undefined);
  const latest = useRef(payload);
  latest.current = payload;
  useEffect(() => {
    if (json === pushed.current || pushTimer.current !== undefined) return;
    pushTimer.current = window.setTimeout(() => {
      pushTimer.current = undefined;
      const now = JSON.stringify(latest.current);
      if (now === pushed.current) return;
      pushed.current = now;
      getDesktopBridge()?.shell.setState({ liveBrain: latest.current });
    }, PUSH_MS);
  }, [json]);
  useEffect(
    () => () => {
      window.clearTimeout(pushTimer.current);
      pushTimer.current = undefined;
      if (pushed.current !== undefined && pushed.current !== "null") getDesktopBridge()?.shell.setState({ liveBrain: null });
    },
    [],
  );

  return {
    state,
    playbook,
    drafts,
    reading,
    offlineSince,
    asks,
    typeChanged,
    fromDraft,
    contact,
    responder,
    preguntar,
    resumen,
    rewrite,
    askStep,
    tick: tickItem,
    untick: untickItem,
    dismiss,
    clearAsk,
  };
}

export type LiveBrain = ReturnType<typeof useLiveBrain>;
