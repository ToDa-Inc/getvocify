import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { playbooksApi } from "@/features/playbooks/api";
import { getDesktopBridge } from "@/lib/desktop-host";
import { assistContext, BACKSTOP_MS, turnCheck } from "@/lib/live-assist";
import {
  buildReading,
  clearProgressCursor,
  liveBrainPayload,
  longTurnDue,
  OFFLINE_AFTER,
  playbookView,
  pointSays,
  repReadingDue,
  repWords,
  resetForType,
  streamedPoints,
  toWireTurns,
  type LiveBrainAsks,
  type LiveDraft,
  type LiveReason,
  type ReadMark,
  type ReadingCall,
} from "@/lib/live-brain";
import type { MeetingDisplayTurn } from "@/lib/meeting-transcript";
import { applyPoints, applyProgress, dismissPoint, emptyLiveState, tick, untick } from "../../../../shared/live-call/state.js";
import { createReader } from "../../../../shared/live-call/reader.js";
import { LiveBrainError, readSlow, streamPoints } from "./liveBrainApi";
import { useProspectPause } from "./useLiveAssist";
import { readTurn } from "./sources";

/** How the island's push is throttled: a change waits at most this long (many tokens make one push). */
const PUSH_MS = 250;

export type LiveBrainCall = {
  callId?: string | null;
  contactId?: string | null;
  callMode?: "softphone" | "meeting";
  typeKey?: string | null;
  /** The type's name as the rep sees it. */
  typeLabel?: string | null;
  /** Their side's audio level (0–1): when it goes quiet is when they may have finished. */
  prospectLevel?: number;
};

type Spec = { reason: LiveReason; mark: ReadMark; typeChanged?: boolean };
type Kind = "step" | "data" | "goal";

const NO_ASKS: LiveBrainAsks = { responder: null, recap: null };

/**
 * The live call assistant on the dashboard (spec 2026-10-16-live-call-assistant-design.md): holds the LiveState, reads at
 * the spec's checkpoints, merges what comes back with shared/live-call/state.js, and pushes the state to the island.
 * Only runs behind the company flag; with it off nothing here is active and today's live help (useLiveAssist) is.
 *
 * `enabled`: the flag, live help on, the call recording and not paused. `flag`: only the flag (the island is told when help is off).
 */
export function useLiveBrain(turns: MeetingDisplayTurn[], opts: { flag: boolean; enabled: boolean; helpOn: boolean }, call: LiveBrainCall = {}) {
  const { flag, enabled, helpOn } = opts;
  const callId = call.callId ?? null;
  const active = flag && enabled && Boolean(callId);

  const stateRef = useRef(emptyLiveState(callId ?? ""));
  const [state, setViewState] = useState(stateRef.current);
  const [drafts, setDrafts] = useState<LiveDraft[]>([]);
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

  // ---- the readings ----
  const askedRef = useRef<{ points: LiveReason | null; progress: LiveReason | null }>({ points: null, progress: null });
  const controllersRef = useRef<{ points: AbortController | null; progress: AbortController | null; recap: AbortController | null }>({
    points: null,
    progress: null,
    recap: null,
  });
  const typeChangedRef = useRef(false);
  const seqRef = useRef({ responder: 0, recap: 0 });

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
    const wire = toWireTurns(turnsRef.current);
    const responder = reason === "responder";
    if (!activeRef.current || !wire.length) {
      if (responder) setAsks((a) => ({ ...a, responder: { seq: seqRef.current.responder, status: "nothing", point_id: null } }));
      return;
    }
    const controller = new AbortController();
    controllersRef.current.points = controller;
    const body = buildReading({ call: readingCall(), turns: wire, state: stateRef.current, reason, mark: spec.mark, producer: "points" });
    setReading((r) => ({ ...r, points: true }));
    let text = "";
    let result: Record<string, unknown> & { points?: { id: string }[] } | null = null;
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
      const merged = applyPoints(stateRef.current, result, { asked: responder });
      commit(merged);
      const said = new Set(lastDrafts.map((d) => d.say).filter(Boolean));
      const landed = (result.points ?? []).map((p: { id: string }) => p.id).filter((id: string) => merged.points.some((p: { id: string }) => p.id === id));
      setFromDraft((ids) => [
        ...ids,
        ...landed.filter((id: string) => said.has(pointSays(merged.points.find((p: { id: string }) => p.id === id) ?? { answer: null, fallback: null }))),
      ]);
      if (responder) {
        const found = landed.length ? landed[landed.length - 1] : null;
        setAsks((a) => ({ ...a, responder: { seq: seqRef.current.responder, status: found ? "found" : "nothing", point_id: found } }));
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      failed();
      if (responder) setAsks((a) => ({ ...a, responder: null }));
      if (!(error instanceof LiveBrainError)) console.warn("live brain: points reading failed", error);
    } finally {
      if (controllersRef.current.points === controller) controllersRef.current.points = null;
      setDrafts([]);
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
    const body = buildReading({ call: readingCall(), turns: wire, state: stateRef.current, reason, mark: spec.mark, producer: "progress", typeChanged: changed });
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

  // The readers see the latest closures: a reading is built when it starts, not when it was asked for.
  const runPointsRef = useRef(runPoints);
  runPointsRef.current = runPoints;
  const runProgressRef = useRef(runProgress);
  runProgressRef.current = runProgress;
  const readers = useRef<{ points: ReturnType<typeof createReader>; progress: ReturnType<typeof createReader> } | null>(null);
  if (!readers.current) {
    readers.current = {
      points: createReader((spec: Spec, o: { asked: boolean }) => runPointsRef.current(spec, o)),
      progress: createReader((spec: Spec, o: { asked: boolean }) => runProgressRef.current(spec, o)),
    };
  }

  // ---- checkpoints ----
  const markRef = useRef<ReadMark>(null);
  const lastPointsAtRef = useRef<number | null>(null);
  const repReadRef = useRef({ words: 0, at: null as number | null });

  /** A checkpoint reading: points and progress (a long turn reads only points). */
  const read = (reason: LiveReason, mark: ReadMark, only?: "points") => {
    lastPointsAtRef.current = Date.now();
    repReadRef.current = { words: repWords(turnsRef.current), at: Date.now() };
    readers.current!.points.request({ reason, mark });
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
      read("turn_end", previous);
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
      if (open) readers.current!.points.request({ reason: "rep_turn", mark: markRef.current });
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
    commit(emptyLiveState(callId ?? ""));
    markRef.current = null;
    lastKeyRef.current = "";
    lastPointsAtRef.current = null;
    repReadRef.current = { words: 0, at: null };
    typeChangedRef.current = false;
    failuresRef.current = 0;
    lastOkRef.current = Date.now();
    seqRef.current = { responder: 0, recap: 0 };
    setDrafts([]);
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
    window.clearTimeout(backstopRef.current);
    setDrafts([]);
    setReading({ points: false, progress: false, recap: false });
  }, [active]);

  useEffect(
    () => () => {
      checkRef.current?.abort();
      controllersRef.current.points?.abort();
      controllersRef.current.progress?.abort();
      controllersRef.current.recap?.abort();
      window.clearTimeout(backstopRef.current);
    },
    [],
  );

  // ---- the rep's asks and marks ----
  const responder = useCallback(() => {
    if (!activeRef.current) return;
    seqRef.current.responder += 1;
    setAsks((a) => ({ ...a, responder: { seq: seqRef.current.responder, status: "reading", point_id: null } }));
    askedRef.current.points = "responder";
    readers.current!.points.request({ reason: "responder", mark: null }, { asked: true });
  }, []);

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
      const body = buildReading({ call: readingCall(), turns: wire, state: stateRef.current, reason: "resumen", producer: "recap" });
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
      // Ahora and Falta follow the rep's mark on the next reading.
      askedRef.current.progress = "preguntar";
      readers.current!.progress.request({ reason: "preguntar", mark: null }, { asked: true });
    },
    [mutate],
  );
  const untickItem = useCallback((id: string, kind: Kind) => mutate((s) => untick(s, id, kind)), [mutate]);
  const dismiss = useCallback((id: string) => mutate((s) => dismissPoint(s, id)), [mutate]);

  /** Closes the Responder ask once its point is dealt with by the view (the island reads `asks`). */
  const clearAsk = useCallback((which: "responder" | "recap") => setAsks((a) => ({ ...a, [which]: null })), []);

  // ---- what the island asks for ----
  const handlersRef = useRef({ responder, preguntar, resumen, tickItem, untickItem, dismiss });
  handlersRef.current = { responder, preguntar, resumen, tickItem, untickItem, dismiss };
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
        default: return undefined;
      }
    });
  }, [flag]);

  // ---- the playbook's words for the ids ----
  const editor = useQuery({
    queryKey: ["live-brain-playbook", typeKey],
    queryFn: () => playbooksApi.editor(typeKey as string),
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
          })
        : null,
    [typeKey, call.typeLabel, state.progress.playbook, state.progress.has_playbook, state.progress.aids, editor.data],
  );

  // ---- the island: the whole state, throttled and as changes ----
  const payload = flag && callId ? liveBrainPayload({ on: helpOn, callId, state, playbook, reading, offlineSince, drafts, asks, typeChanged }) : null;
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
    responder,
    preguntar,
    resumen,
    tick: tickItem,
    untick: untickItem,
    dismiss,
    clearAsk,
  };
}

export type LiveBrain = ReturnType<typeof useLiveBrain>;
