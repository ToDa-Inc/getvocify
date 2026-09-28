import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useAuth } from "@/features/auth";
import { memosApi, memoKeys } from "@/features/memos/api";
import { api } from "@/shared/lib/api-client";
import { ROUTES } from "@/shared/lib/constants";
import {
  encodeChannelAudio,
  hookMicPcm,
  liveTranscriptionWsUrl,
  LIVE_STT_SAMPLE_RATE,
} from "@/lib/copilot-channel-stt";
import {
  applyChannelResult,
  EMPTY_MEETING_TRANSCRIPT,
  meetingDisplayTurns,
  meetingHasSpeech,
  meetingLastLine,
  meetingUploadText,
  settleMeeting,
  type MeetingDisplayTurn,
  type MeetingSpeaker,
  type MeetingTranscript,
} from "@/lib/meeting-transcript";
import { meetingStartedLabel, sortDrafts, type MeetingDraft } from "@/lib/meeting-draft";
import { normalizePermissionStatus } from "@/lib/desktop-permissions";
import { getDesktopBridge, isDesktopHost } from "@/lib/desktop-host";

export type MeetingPhase = "idle" | "starting" | "live" | "stopping" | "uploading";

type DesktopMeeting = {
  available: boolean;
  phase: MeetingPhase;
  elapsed: string;
  error: string | null;
  warning: string | null;
  turns: MeetingDisplayTurn[];
  /** Meetings that could not be sent yet, oldest first. */
  pending: MeetingDraft[];
  /** Whether unsent meetings survive a quit (the host keeps drafts on disk). */
  savedOnDevice: boolean;
  start: () => Promise<void>;
  stop: () => Promise<void>;
  retryPending: () => Promise<void>;
};

const MAX_RECONNECTS = 5;
/** Production closes ~5s after CloseStream, once the last finals are flushed. */
const DRAIN_MS = 6000;
/** Worst case a crash loses this much transcript. */
const SAVE_EVERY_MS = 2000;

const DesktopMeetingContext = createContext<DesktopMeeting | null>(null);

function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const s = String(total % 60).padStart(2, "0");
  return h ? `${h}:${m}:${s}` : `${m}:${s}`;
}

function newDraftId(): string {
  return crypto.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function DesktopMeetingProvider({ children }: { children: ReactNode }) {
  const available = isDesktopHost();
  const savedOnDevice = Boolean(getDesktopBridge()?.drafts);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();

  const [phase, setPhaseState] = useState<MeetingPhase>("idle");
  const [transcript, setTranscript] = useState<MeetingTranscript>(EMPTY_MEETING_TRANSCRIPT);
  const [elapsed, setElapsed] = useState("00:00");
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [pending, setPending] = useState<MeetingDraft[]>([]);

  const phaseRef = useRef<MeetingPhase>("idle");
  const transcriptRef = useRef<MeetingTranscript>(EMPTY_MEETING_TRANSCRIPT);
  const draftRef = useRef<{ id: string; startedAt: number } | null>(null);
  const saveTimerRef = useRef<number | null>(null);
  const recoveredForRef = useRef<string | null>(null);
  const userIdRef = useRef("");
  const wsRef = useRef<WebSocket | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const micRef = useRef<MediaStream | null>(null);
  const releaseAudioRef = useRef<Array<() => void>>([]);
  const timerRef = useRef<number | null>(null);
  const reconnectsRef = useRef(0);
  const startRef = useRef<() => Promise<void>>(async () => {});
  const stopRef = useRef<() => Promise<void>>(async () => {});

  const setPhase = useCallback((next: MeetingPhase) => {
    phaseRef.current = next;
    setPhaseState(next);
  }, []);

  const fail = useCallback((message: string) => {
    setError(message);
    toast.error(message);
  }, []);

  const currentDraft = useCallback((): MeetingDraft | null => {
    const meta = draftRef.current;
    if (!meta) return null;
    return {
      ...meta,
      userId: userIdRef.current,
      updatedAt: Date.now(),
      transcript: transcriptRef.current,
    };
  }, []);

  const saveDraftNow = useCallback(() => {
    if (saveTimerRef.current) {
      window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    const draft = currentDraft();
    if (draft && meetingHasSpeech(draft.transcript)) void getDesktopBridge()?.drafts?.save(draft);
  }, [currentDraft]);

  const scheduleSave = useCallback(() => {
    if (saveTimerRef.current) return;
    saveTimerRef.current = window.setTimeout(() => {
      saveTimerRef.current = null;
      saveDraftNow();
    }, SAVE_EVERY_MS);
  }, [saveDraftNow]);

  const updateTranscript = useCallback(
    (next: MeetingTranscript) => {
      transcriptRef.current = next;
      setTranscript(next);
      getDesktopBridge()?.shell.setState({ lastLine: meetingLastLine(next) });
      if (draftRef.current) scheduleSave();
    },
    [scheduleSave],
  );

  /** Creates the memo, then forgets the draft. Throws when the send fails. */
  const sendDraft = useCallback(
    async (draft: MeetingDraft): Promise<string> => {
      const res = await memosApi.uploadTranscriptAndExtract(
        meetingUploadText(draft.transcript),
        "meeting_transcript",
      );
      await getDesktopBridge()?.drafts?.remove(draft.id);
      queryClient.invalidateQueries({ queryKey: memoKeys.lists() });
      return res.id;
    },
    [queryClient],
  );

  const releaseAudio = useCallback(async () => {
    if (timerRef.current) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    releaseAudioRef.current.forEach((release) => release());
    releaseAudioRef.current = [];
    micRef.current?.getTracks().forEach((track) => track.stop());
    micRef.current = null;
    await getDesktopBridge()?.systemAudio.stop();
    await ctxRef.current?.close().catch(() => {});
    ctxRef.current = null;
  }, []);

  const openSocket = useCallback(() => {
    const ws = new WebSocket(liveTranscriptionWsUrl(userIdRef.current));
    wsRef.current = ws;
    ws.onopen = () => {
      reconnectsRef.current = 0;
      setWarning(null);
    };
    ws.onmessage = (event) => {
      let data: {
        type?: string;
        is_final?: boolean;
        audio_channel?: unknown;
        error?: unknown;
        channel?: { alternatives?: Array<{ transcript?: string }> };
      };
      try {
        data = JSON.parse(String(event.data));
      } catch {
        return;
      }
      if (data.type === "Results") {
        const next = applyChannelResult(transcriptRef.current, {
          text: data.channel?.alternatives?.[0]?.transcript ?? "",
          isFinal: Boolean(data.is_final),
          audioChannel: data.audio_channel,
        });
        if (next !== transcriptRef.current) updateTranscript(next);
      } else if (data.type === "Error") {
        setWarning(typeof data.error === "string" ? data.error : "Transcription error");
      }
    };
    ws.onclose = () => {
      if (wsRef.current !== ws || phaseRef.current !== "live") return;
      if (reconnectsRef.current >= MAX_RECONNECTS) {
        toast.error("Transcription disconnected. Saving what was captured.");
        void stopRef.current();
        return;
      }
      reconnectsRef.current += 1;
      setWarning("Reconnecting…");
      window.setTimeout(() => {
        if (phaseRef.current === "live" && wsRef.current === ws) openSocket();
      }, 1000 * reconnectsRef.current);
    };
  }, [updateTranscript]);

  const drainSocket = useCallback(async () => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      await new Promise<void>((resolve) => {
        const timer = window.setTimeout(resolve, DRAIN_MS);
        ws.addEventListener(
          "close",
          () => {
            window.clearTimeout(timer);
            resolve();
          },
          { once: true },
        );
        ws.send(JSON.stringify({ type: "CloseStream" }));
      });
    }
    ws?.close();
    wsRef.current = null;
  }, []);

  const stop = useCallback(async () => {
    if (phaseRef.current !== "live") return;
    setPhase("stopping");
    const bridge = getDesktopBridge();
    await releaseAudio();
    await drainSocket();
    await bridge?.shell.hideOverlay();
    bridge?.shell.setState({ listening: false });

    transcriptRef.current = settleMeeting(transcriptRef.current);
    const draft = currentDraft();
    draftRef.current = null;
    if (saveTimerRef.current) {
      window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    if (!draft || !meetingHasSpeech(draft.transcript)) {
      if (draft) void bridge?.drafts?.remove(draft.id);
      updateTranscript(EMPTY_MEETING_TRANSCRIPT);
      setPhase("idle");
      fail("Nothing was transcribed. Check the meeting isn't muted.");
      return;
    }
    await bridge?.drafts?.save(draft);

    setPhase("uploading");
    try {
      const memoId = await sendDraft(draft);
      updateTranscript(EMPTY_MEETING_TRANSCRIPT);
      setPhase("idle");
      navigate(ROUTES.MEMO_DETAIL(memoId));
    } catch {
      setPending((list) => [...list, draft]);
      updateTranscript(EMPTY_MEETING_TRANSCRIPT);
      setPhase("idle");
      fail(
        bridge?.drafts
          ? "Couldn't send the meeting. It's saved on this Mac."
          : "Couldn't send the meeting. Retry before closing Vocify.",
      );
    }
  }, [currentDraft, drainSocket, fail, navigate, releaseAudio, sendDraft, setPhase, updateTranscript]);

  const start = useCallback(async () => {
    const bridge = getDesktopBridge();
    if (!bridge || phaseRef.current !== "idle") return;
    if (!user?.id || !api.getToken()) {
      fail("Sign in to record.");
      return;
    }
    userIdRef.current = user.id;
    setError(null);
    setWarning(null);
    setPhase("starting");
    try {
      const perm = await bridge.permissions.status();
      if (normalizePermissionStatus(perm.microphone) !== "authorized") {
        throw new Error("Allow Microphone in the panel above, then try again.");
      }
      if (normalizePermissionStatus(perm.systemAudio) !== "authorized") {
        throw new Error("Allow system audio in the panel above, then try again.");
      }

      const micStream = await navigator.mediaDevices
        .getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        })
        .catch(() => {
          throw new Error("Could not open the microphone.");
        });
      micRef.current = micStream;

      const native = await bridge.systemAudio.start();
      if (!native.ok) {
        throw new Error(
          native.reason === "needs_restart"
            ? "System audio is on but Vocify needs a restart. Quit (⌘Q) and reopen, then record again."
            : "Tap Allow on system audio above — drag Vocify into Settings.",
        );
      }

      const ctx = new AudioContext({ sampleRate: LIVE_STT_SAMPLE_RATE });
      ctxRef.current = ctx;
      if (ctx.state === "suspended") await ctx.resume();

      const startedAt = Date.now();
      draftRef.current = { id: newDraftId(), startedAt };
      updateTranscript(EMPTY_MEETING_TRANSCRIPT);
      reconnectsRef.current = 0;
      setPhase("live");
      openSocket();

      const send = (channel: MeetingSpeaker) => (pcm: ArrayBuffer) => {
        const ws = wsRef.current;
        if (ws?.readyState === WebSocket.OPEN) ws.send(encodeChannelAudio(channel, pcm));
      };
      releaseAudioRef.current = [
        hookMicPcm(ctx, micStream, send("rep")),
        bridge.systemAudio.onPcm(send("prospect")),
        bridge.systemAudio.onLost?.(() =>
          setWarning("Meeting audio stopped. Your mic is still recording."),
        ) ?? (() => {}),
      ];

      setElapsed("00:00");
      timerRef.current = window.setInterval(() => {
        const next = formatElapsed(Date.now() - startedAt);
        setElapsed(next);
        bridge.shell.setState({ elapsed: next });
      }, 500);
      bridge.shell.setState({ listening: true, elapsed: "00:00", lastLine: "" });
      await bridge.shell.showOverlay();
    } catch (e) {
      draftRef.current = null;
      await releaseAudio();
      wsRef.current?.close();
      wsRef.current = null;
      setPhase("idle");
      fail(e instanceof Error && e.message ? e.message : "Could not start recording.");
    }
  }, [fail, openSocket, releaseAudio, setPhase, updateTranscript, user?.id]);

  /** Sends every unsent meeting; the ones that fail again stay pending. */
  const sendAll = useCallback(
    async (drafts: MeetingDraft[]) => {
      const sent: string[] = [];
      const failed: MeetingDraft[] = [];
      for (const draft of drafts) {
        try {
          sent.push(await sendDraft(draft));
        } catch {
          failed.push(draft);
        }
      }
      setPending(failed);
      return { sent, failed };
    },
    [sendDraft],
  );

  const retryPending = useCallback(async () => {
    if (!pending.length) return;
    setError(null);
    const { sent, failed } = await sendAll(pending);
    if (failed.length) {
      fail("Still couldn't send. Check your connection and retry.");
      return;
    }
    navigate(sent.length === 1 ? ROUTES.MEMO_DETAIL(sent[0]) : ROUTES.MEMOS);
  }, [fail, navigate, pending, sendAll]);

  // Meetings left behind by a quit, crash or failed send go out on their own.
  useEffect(() => {
    const drafts = getDesktopBridge()?.drafts;
    if (!drafts || !user?.id || recoveredForRef.current === user.id) return;
    recoveredForRef.current = user.id;
    void (async () => {
      const stored = (await drafts.list()) ?? [];
      const live = draftRef.current?.id;
      const { send, discard } = sortDrafts(stored.filter((d) => (d as MeetingDraft)?.id !== live), user.id);
      discard.forEach((draft) => void drafts.remove(draft.id));
      if (!send.length) return;
      const { sent, failed } = await sendAll(send);
      if (sent.length) {
        toast.success(
          sent.length === 1
            ? `Meeting from ${meetingStartedLabel(send[0])} sent for review`
            : `${sent.length} unsent meetings sent for review`,
          {
            action: {
              label: "Review",
              onClick: () => navigate(sent.length === 1 ? ROUTES.MEMO_DETAIL(sent[0]) : ROUTES.MEMOS),
            },
          },
        );
      }
      if (failed.length) setError("Couldn't send the meeting. It's saved on this Mac.");
    })();
  }, [navigate, sendAll, user?.id]);

  startRef.current = start;
  stopRef.current = stop;

  useEffect(() => {
    const bridge = getDesktopBridge();
    if (!bridge) return;
    return bridge.shell.onCommand((name) => {
      const current = phaseRef.current;
      if (name === "stop" || (name === "toggle" && current === "live")) {
        void stopRef.current();
      } else if (name === "listen" || (name === "toggle" && current === "idle")) {
        navigate(ROUTES.RECORD);
        void startRef.current();
      }
    });
  }, [navigate]);

  // Leaving the dashboard mid-meeting (e.g. signing out) keeps the transcript on disk.
  useEffect(
    () => () => {
      saveDraftNow();
      draftRef.current = null;
      phaseRef.current = "idle";
      void releaseAudio();
      wsRef.current?.close();
      wsRef.current = null;
      const bridge = getDesktopBridge();
      bridge?.shell.setState({ listening: false });
      void bridge?.shell.hideOverlay();
    },
    [releaseAudio, saveDraftNow],
  );

  const turns = useMemo(() => meetingDisplayTurns(transcript), [transcript]);

  const value = useMemo<DesktopMeeting>(
    () => ({
      available,
      phase,
      elapsed,
      error,
      warning,
      turns,
      pending,
      savedOnDevice,
      start,
      stop,
      retryPending,
    }),
    [available, phase, elapsed, error, warning, turns, pending, savedOnDevice, start, stop, retryPending],
  );

  return <DesktopMeetingContext.Provider value={value}>{children}</DesktopMeetingContext.Provider>;
}

export function useDesktopMeeting(): DesktopMeeting {
  const ctx = useContext(DesktopMeetingContext);
  if (!ctx) throw new Error("useDesktopMeeting must be used inside DesktopMeetingProvider");
  return ctx;
}
