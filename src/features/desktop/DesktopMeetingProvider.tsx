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
import { isProcessing } from "@/features/memos/types";
import { crmApi } from "@/lib/api/crm";
import { useIntegrations } from "@/features/integrations/hooks/useIntegrations";
import { CRM_PROVIDER_CONFIGS, type CRMProvider } from "@/features/integrations/types";
import { api } from "@/shared/lib/api-client";
import { liveTickets } from "./liveTickets";
import { ROUTES } from "@/shared/lib/constants";
import { EchoSuppressor } from "@/lib/echo-suppressor";
import {
  encodeChannelAudio,
  hookMicPcm,
  liveAuthMessage,
  liveTranscriptionWsUrl,
  LIVE_STT_SAMPLE_RATE,
} from "@/lib/copilot-channel-stt";
import {
  applyChannelResult,
  resetChannel,
  normalizeMeetingTranscript,
  EMPTY_MEETING_TRANSCRIPT,
  meetingDisplayTurns,
  meetingHasSpeech,
  meetingLastLine,
  meetingOverlay,
  meetingParticipants,
  meetingUploadText,
  settleMeeting,
  type MeetingDisplayTurn,
  type MeetingSpeaker,
  type MeetingTranscript,
} from "@/lib/meeting-transcript";
import { meetingStartedLabel, sortDrafts, type CallSourceInfo, type MeetingDraft } from "@/lib/meeting-draft";
import { SpeakerTimeline } from "@/lib/speaker-timeline";
import { normalizePermissionStatus } from "@/lib/desktop-permissions";
import { getDesktopBridge, isDesktopHost, desktopPlatform, MEMO_CHANGED_EVENT } from "@/lib/desktop-host";
import { islandCallContact, latestOnly, type CallPreview } from "@/lib/call-contact";
import { contactRecordUrl } from "@/lib/today";
import {
  POST_CALL_GIVE_UP_MS,
  UNDO_MS,
  callTypeFrom,
  crmFor,
  crmForType,
  emailFrom,
  meetingFrom,
  pollDelayMs,
  noteMarkdown,
  retypedTo,
  summaryLines,
  withEdits,
  type PostCall,
} from "@/lib/post-call";
import { playbooksApi } from "@/features/playbooks/api";
import { useLanguage } from "@/lib/i18n";
import { motionLabel } from "@/lib/motion-label";
import { retagOptions, typeOptions, type TypeOption } from "@/lib/interactions";
import { LIVE_CHANNELS, byChannel, channelTypeOptions, type LiveChannel } from "@/lib/type-channels";
import {
  NO_CALL_TYPE,
  assistCallMode,
  callKind,
  callTypeShown,
  proposalDue,
  typeForMemo,
  withChannelTypes,
  withPick,
  withProposal,
  type CallTypeState,
} from "@/lib/live-call-type";
import { buildApproveExtraction, proposedFieldKey, type ProposedUpdate } from "@/lib/extraction-omit";
import { afterCallPoll, afterCallResolution, type CallSummary } from "@/lib/after-call";
import { callsApi } from "@/features/calls/api";
import { callEngine, reportCallStep } from "@/features/calling/callEngine";
import { isCallUp } from "@/lib/call-engine-state";

export type MeetingPhase = "idle" | "starting" | "live" | "stopping" | "uploading";

/** A Vocify call (dialled from the island or the dock) the page transcribes live from its own two sides. */
export type VocifyCallSession = {
  callSid: string;
  streams: { local: MediaStream; remote: MediaStream };
  contact: MeetingDraft["contact"] | null;
};

type DesktopMeeting = {
  available: boolean;
  phase: MeetingPhase;
  elapsed: string;
  /** Recording continues but nothing is transcribed and the timer holds. */
  paused: boolean;
  pause: () => void;
  resume: () => void;
  /** 0–1 loudness of each side, for the live bars. */
  levels: { you: number; them: number };
  error: string | null;
  warning: string | null;
  turns: MeetingDisplayTurn[];
  notes: string;
  setNotes: (notes: string) => void;
  /** Meetings that could not be sent yet, oldest first. */
  pending: MeetingDraft[];
  /** Whether unsent meetings survive a quit (the host keeps drafts on disk). */
  savedOnDevice: boolean;
  /** The CRM contact of the call being recorded, when the island knew it. */
  contact: MeetingDraft["contact"] | null;
  /** The call's type: Vocify's proposal (`proposed`) or the rep's pick. Live help uses its playbook. */
  callType: { key: string | null; proposed: boolean };
  /** How live help should treat the call, from the platform that caught it. */
  callMode: "softphone" | "meeting";
  /** The rep switched live help on or off for this call only; null follows the remembered setting. */
  liveHelpOverride: boolean | null;
  start: () => Promise<void>;
  /** Starts a recording and stays on this page (Inicio keeps its chat). False when it did not go live. */
  startHere: () => Promise<boolean>;
  /** Live transcript and help for a Vocify call; its memo comes from the call recording, not from here. */
  startCall: (session: VocifyCallSession) => Promise<void>;
  /** A Vocify call ended without a live session (its audio never reached the page): still follow its memo. */
  followCall: (callSid: string, contactName: string | null) => void;
  stop: () => Promise<void>;
  retryPending: () => Promise<void>;
};

const MAX_RECONNECTS = 5;
/** The server answers CloseStream with EndOfTranscript as soon as the last finals are flushed (well under a second),
 * and gives up after 3 s; this waits a second longer so its answer always wins. */
const DRAIN_MS = 4000;
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

/** Loudness of one PCM16 chunk, eased so normal speech sits around 0.5. */
function pcmLevel(pcm: ArrayBuffer): number {
  const samples = new Int16Array(pcm);
  let sum = 0;
  let count = 0;
  for (let i = 0; i < samples.length; i += 8) {
    const v = samples[i] / 32768;
    sum += v * v;
    count++;
  }
  const rms = count ? Math.sqrt(sum / count) : 0;
  return Math.min(1, Math.sqrt(rms * 6));
}

function newDraftId(): string {
  return crypto.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}


/** The Vocify call's source on its memo draft: always a phone call. */
const VOCIFY_CALL_SOURCE: CallSourceInfo = { name: "Vocify", kind: "call" };

/** Only a change the meter can show re-renders: silence settles at 0 and stays put. */
function levelStep(value: number): number {
  return Math.round(value * 20) / 20;
}

export function DesktopMeetingProvider({ children }: { children: ReactNode }) {
  const available = isDesktopHost();
  const savedOnDevice = Boolean(getDesktopBridge()?.drafts);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { t } = useLanguage();
  const integrations = useIntegrations();
  const connected = integrations.data?.find((connection) => connection.status === "connected")?.provider;
  /** The CRM the island names in its card; read when a call ends. */
  const crmNameRef = useRef<string | null>(null);
  crmNameRef.current = connected ? CRM_PROVIDER_CONFIGS[connected as CRMProvider]?.name ?? null : null;
  /** Where a contact's record lives in the connected CRM (HubSpot only): the card links to it once it is updated. */
  const hubspot = integrations.data?.find((connection) => connection.provider === "hubspot" && connection.status === "connected");
  const contactUrlRef = useRef<(contactId: string | null | undefined) => string | null>(() => null);
  contactUrlRef.current = (contactId) =>
    contactRecordUrl(hubspot ? "hubspot" : null, hubspot?.metadata?.portalId ?? null, contactId ?? null);
  /** A type's name as the memo page shows it: the company's label, else the catalog's. */
  const typeName = useCallback(
    (key: string, label?: string | null) => label || t.product.pb2.typeLabels[key] || motionLabel(key, t.product.motions),
    [t],
  );

  const [phase, setPhaseState] = useState<MeetingPhase>("idle");
  const [transcript, setTranscript] = useState<MeetingTranscript>(EMPTY_MEETING_TRANSCRIPT);
  const [elapsed, setElapsed] = useState("00:00");
  const [paused, setPaused] = useState(false);
  const pausedRef = useRef(false);
  const pausedAtRef = useRef(0);
  const pausedTotalRef = useRef(0);
  const [levels, setLevels] = useState({ you: 0, them: 0 });
  const levelRef = useRef({ you: 0, them: 0 });
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [pending, setPending] = useState<MeetingDraft[]>([]);
  const [notes, setNotesState] = useState("");
  const notesRef = useRef("");
  const [contact, setContact] = useState<MeetingDraft["contact"] | null>(null);
  /** Who the call detected by the island is with; the next recording takes it. */
  const callContactRef = useRef<MeetingDraft["contact"] | null>(null);
  /** Where the detected call happens (app or page), as the Mac told us. */
  const callSourceRef = useRef<CallSourceInfo | null>(null);
  /** The memo the island is following after a call; `cancelled` stops an older follow. */
  const postCallRef = useRef<{
    run: { cancelled: boolean };
    state: PostCall;
    proposed: ProposedUpdate[];
    /** The memo's CRM contact, when it has one. */
    contactId?: string;
    undoTimer?: number;
    /** Every type the call could be, in the order the memo page lists them. */
    typeOrder?: string[];
    /** The CRM part as the memo has it, kept for when the type changes back from internal. */
    crm?: Pick<PostCall, "stage" | "changes" | "canApprove" | "note">;
  } | null>(null);

  /** The call's type while recording: Vocify proposes, the rep's pick is final. */
  const [callType, setCallTypeState] = useState<CallTypeState>(NO_CALL_TYPE);
  const callTypeRef = useRef<CallTypeState>(NO_CALL_TYPE);
  /** The company's types the island offers, once loaded. */
  const typeOptionsRef = useRef<{ key: string; label: string }[]>([]);
  // Every type of the company (GET /playbooks) for this recording: the island's options are the
  // channel's ones, recomputed when the rep switches the channel.
  const allTypesRef = useRef<{ options: TypeOption[]; payload: unknown } | null>(null);
  const channelLabelsRef = useRef<Record<string, string>>(t.product.interactions.channel);
  channelLabelsRef.current = t.product.interactions.channel;
  /** The model proposals asked this call (at most two). */
  // `attempts` per channel (a switch starts them again), `total` for the whole call.
  const proposalRef = useRef({ attempts: 0, total: 0, lastConfident: false, busy: false });
  const [callMode, setCallMode] = useState<"softphone" | "meeting">("meeting");
  const [liveHelpOverride, setLiveHelpOverride] = useState<boolean | null>(null);

  const phaseRef = useRef<MeetingPhase>("idle");
  const transcriptRef = useRef<MeetingTranscript>(EMPTY_MEETING_TRANSCRIPT);
  const draftRef = useRef<{
    id: string;
    startedAt: number;
    contact?: MeetingDraft["contact"];
    source?: CallSourceInfo;
    channel?: MeetingDraft["channel"];
    type?: string;
    typeSource?: MeetingDraft["typeSource"];
  } | null>(null);
  const saveTimerRef = useRef<number | null>(null);
  const recoveredForRef = useRef<string | null>(null);
  const userIdRef = useRef("");
  const wsRef = useRef<WebSocket | null>(null);
  /** Which sides have had their first words transcribed in this recording (logged once each). */
  const firstWordsRef = useRef<{ rep?: boolean; prospect?: boolean }>({});
  /** Who the meeting app showed speaking, timed on the other side's audio clock (page recording only). */
  const speakersRef = useRef<{ timeline: SpeakerTimeline; clockAt: number | null } | null>(null);
  /** Keeps the call out of the microphone when the page records both sides itself (a meeting heard through speakers). */
  const echoRef = useRef<EchoSuppressor | null>(null);
  /** The live service's pass for this recording, sent first on every connection. */
  const ticketRef = useRef<string | null>(null);
  /** The Mac app is recording this meeting itself; the page only mirrors its transcript. */
  const nativeRef = useRef(false);
  const ctxRef = useRef<AudioContext | null>(null);
  const micRef = useRef<MediaStream | null>(null);
  const releaseAudioRef = useRef<Array<() => void>>([]);
  const timerRef = useRef<number | null>(null);
  const reconnectsRef = useRef(0);
  /** Set while the recording is a Vocify call: the server records it, so nothing is uploaded or kept on disk. */
  const vocifyCallRef = useRef<VocifyCallSession | null>(null);
  const startRef = useRef<(call?: VocifyCallSession) => Promise<void>>(async () => {});
  const stopRef = useRef<() => Promise<void>>(async () => {});
  const pauseRef = useRef<() => void>(() => {});
  const resumeRef = useRef<() => void>(() => {});

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
      notes: notesRef.current,
    };
  }, []);

  const saveDraftNow = useCallback(() => {
    if (saveTimerRef.current) {
      window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    const draft = currentDraft();
    // A Vocify call is recorded by the carrier: a draft on disk would be uploaded later as a second memo.
    if (vocifyCallRef.current) return;
    if (draft && (meetingHasSpeech(draft.transcript) || draft.notes?.trim())) {
      void getDesktopBridge()?.drafts?.save(draft);
    }
  }, [currentDraft]);

  const scheduleSave = useCallback(() => {
    if (saveTimerRef.current) return;
    saveTimerRef.current = window.setTimeout(() => {
      saveTimerRef.current = null;
      saveDraftNow();
    }, SAVE_EVERY_MS);
  }, [saveDraftNow]);

  /** The call's type changed: the memo, the island's chip and live help follow it. */
  const applyCallType = useCallback((next: CallTypeState) => {
    callTypeRef.current = next;
    setCallTypeState(next);
    const shown = callTypeShown(next);
    if (draftRef.current) {
      const forMemo = typeForMemo(next);
      if (forMemo) {
        draftRef.current.type = forMemo.key;
        draftRef.current.typeSource = forMemo.source;
      } else {
        delete draftRef.current.type;
        delete draftRef.current.typeSource;
      }
    }
    const all = allTypesRef.current;
    const draft = draftRef.current;
    // Types by channel: the island also shows the channel, switchable unless the call is Vocify's own.
    const channel =
      all && draft && byChannel(all.payload)
        ? {
            selected: callKind(draft),
            fixed: Boolean(vocifyCallRef.current),
            options: LIVE_CHANNELS.map((key) => ({ key, label: channelLabelsRef.current[key] })),
          }
        : null;
    if (typeOptionsRef.current.length || channel) {
      getDesktopBridge()?.shell.setState({
        liveType: { selected: shown.key, proposed: shown.proposed, options: typeOptionsRef.current, ...(channel && { channel }) },
      });
    }
  }, []);

  /** The island's type options: the channel's types with types by channel, else the published ones. */
  const optionsForCall = useCallback((): { key: string; label: string }[] => {
    const all = allTypesRef.current;
    if (!all) return [];
    const offered = byChannel(all.payload)
      ? channelTypeOptions(all.options, all.payload, callKind(draftRef.current ?? {}))
      : retagOptions(all.options);
    return offered.map(({ key, label }) => ({ key, label }));
  }, []);

  /** Vocify's free guess for the call as it is now (channel and contact). */
  const guessCallType = useCallback(async () => {
    const draft = draftRef.current;
    const guess = await api
      .post<{ type: string | null }>("/copilot/call-type/guess", {
        interaction_kind: draft ? callKind(draft) : "meeting",
        ...(draft?.contact?.hubspotId && { contact_id: draft.contact.hubspotId }),
      })
      .catch(() => null);
    if (phaseRef.current !== "live" || draftRef.current !== draft || !guess?.type) return;
    if (!typeOptionsRef.current.some((option) => option.key === guess.type)) return;
    applyCallType(withProposal(callTypeRef.current, guess.type));
  }, [applyCallType]);

  const updateTranscript = useCallback(
    (next: MeetingTranscript) => {
      transcriptRef.current = next;
      setTranscript(next);
      // A native recording draws the island itself.
      if (!nativeRef.current) {
        const prospect = vocifyCallRef.current?.contact?.name ?? null;
        getDesktopBridge()?.shell.setState({ lastLine: meetingLastLine(next), overlay: meetingOverlay(next, { prospect }) });
      }
      if (draftRef.current) scheduleSave();
    },
    [scheduleSave],
  );

  const setNotes = useCallback(
    (next: string) => {
      notesRef.current = next;
      setNotesState(next);
      if (draftRef.current) scheduleSave();
    },
    [scheduleSave],
  );

  const clearNotes = useCallback(() => {
    notesRef.current = "";
    setNotesState("");
  }, []);

  /** Creates the memo, then forgets the draft. Throws when the send fails. */
  const sendDraft = useCallback(
    async (draft: MeetingDraft): Promise<string> => {
      const res = await memosApi.uploadTranscriptAndExtract(meetingUploadText(draft.transcript), {
        interactionKind: callKind(draft),
        callSource: draft.source?.name,
        salesMotionKey: draft.type,
        typeSource: draft.typeSource ?? "vocify",
        sourceType: "meeting_transcript",
        speakersVerified: true,
        notes: draft.notes,
        hubspotContactId: draft.contact?.hubspotId,
        participants: meetingParticipants(draft.transcript),
        recordingStartedAt: new Date(draft.startedAt).toISOString(),
      });
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
    levelRef.current = { you: 0, them: 0 };
    setLevels({ you: 0, them: 0 });
    releaseAudioRef.current.forEach((release) => release());
    releaseAudioRef.current = [];
    speakersRef.current = null;
    if (echoRef.current) {
      // How much of the microphone was the call's echo: the app's log is where a Windows test shows it worked.
      getDesktopBridge()?.shell.log?.("echo:suppressed", echoRef.current.stats());
      echoRef.current = null;
    }
    micRef.current?.getTracks().forEach((track) => track.stop());
    micRef.current = null;
    await getDesktopBridge()?.systemAudio.stop();
    await ctxRef.current?.close().catch(() => {});
    ctxRef.current = null;
  }, []);

  const openSocket = useCallback(() => {
    // A new session times its audio from zero again: who spoke is timed from its first audio too.
    if (speakersRef.current) speakersRef.current = { timeline: new SpeakerTimeline(), clockAt: null };
    const ws = new WebSocket(liveTranscriptionWsUrl(userIdRef.current));
    wsRef.current = ws;
    ws.onopen = () => {
      if (vocifyCallRef.current) reportCallStep("session-socket-open");
      if (ticketRef.current) ws.send(liveAuthMessage(ticketRef.current));
      reconnectsRef.current = 0;
      setWarning(null);
    };
    ws.onmessage = (event) => {
      let data: {
        type?: string;
        is_final?: boolean;
        audio_channel?: unknown;
        start?: unknown;
        end?: unknown;
        from?: unknown;
        error?: unknown;
        channel?: { alternatives?: Array<{ transcript?: string }> };
      };
      try {
        data = JSON.parse(String(event.data));
      } catch {
        return;
      }
      if (data.type === "Results") {
        // Once per side and recording, in the desktop app's log: when its first words came back. A side that starts
        // late (or never) is why the other person's voice, heard by the mic, shows as the rep's.
        const side = data.audio_channel === "rep" || data.audio_channel === "prospect" ? data.audio_channel : null;
        if (side && !firstWordsRef.current[side] && data.channel?.alternatives?.[0]?.transcript?.trim()) {
          firstWordsRef.current[side] = true;
          getDesktopBridge()?.shell.log?.("transcript-first-words", {
            side,
            secondsIntoRecording: draftRef.current ? Math.round((Date.now() - draftRef.current.startedAt) / 100) / 10 : null,
            audioSecond: typeof data.start === "number" ? data.start : null,
          });
        }
        // The other side's words go to whoever the meeting app showed speaking then.
        const speakers = speakersRef.current;
        const name =
          data.is_final && data.audio_channel === "prospect" && speakers && !speakers.timeline.isEmpty && typeof data.start === "number"
            ? speakers.timeline.name(data.start, typeof data.end === "number" ? data.end : data.start)
            : null;
        const next = applyChannelResult(transcriptRef.current, {
          text: data.channel?.alternatives?.[0]?.transcript ?? "",
          isFinal: Boolean(data.is_final),
          audioChannel: data.audio_channel,
          start: data.start,
          end: data.end,
          name,
        });
        if (next !== transcriptRef.current) updateTranscript(next);
      } else if (data.type === "ChannelReset") {
        const next = resetChannel(transcriptRef.current, data.audio_channel, data.from);
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
        const done = () => {
          window.clearTimeout(timer);
          ws.removeEventListener("message", onMessage);
          resolve();
        };
        // The last finals arrive before EndOfTranscript; the close is only a fallback.
        const onMessage = (event: MessageEvent) => {
          if (String(event.data).includes('"EndOfTranscript"')) done();
        };
        const timer = window.setTimeout(done, DRAIN_MS);
        ws.addEventListener("message", onMessage);
        ws.addEventListener("close", done, { once: true });
        ws.send(JSON.stringify({ type: "CloseStream" }));
      });
    }
    ws?.close();
    wsRef.current = null;
  }, []);

  /** The island keeps its own clock from this, so it ticks even while WebKit throttles our timers. */
  const meetingClock = useCallback(
    () => ({
      startedAt: draftRef.current?.startedAt ?? Date.now(),
      pausedMs: pausedTotalRef.current,
      pausedAt: pausedRef.current ? pausedAtRef.current : null,
    }),
    [],
  );

  const pause = useCallback(() => {
    if (phaseRef.current !== "live" || pausedRef.current) return;
    pausedRef.current = true;
    pausedAtRef.current = Date.now();
    setPaused(true);
    if (nativeRef.current) void getDesktopBridge()?.recorder?.pause(true);
    getDesktopBridge()?.shell.setState({ paused: true, clock: meetingClock() });
  }, [meetingClock]);

  const resume = useCallback(() => {
    if (!pausedRef.current) return;
    pausedTotalRef.current += Date.now() - pausedAtRef.current;
    pausedRef.current = false;
    setPaused(false);
    if (nativeRef.current) void getDesktopBridge()?.recorder?.pause(false);
    getDesktopBridge()?.shell.setState({ paused: false, clock: meetingClock() });
  }, [meetingClock]);

  const showPostCall = useCallback((patch: Partial<PostCall>) => {
    const current = postCallRef.current;
    if (!current) return;
    current.state = { ...current.state, ...patch };
    getDesktopBridge()?.shell.setState({ postCall: current.state });
  }, []);

  const endPostCall = useCallback(() => {
    const current = postCallRef.current;
    if (current) {
      current.run.cancelled = true;
      window.clearTimeout(current.undoTimer);
    }
    postCallRef.current = null;
    getDesktopBridge()?.shell.setState({ postCall: null });
  }, []);

  const memoChanged = useCallback(
    (memoId: string) => {
      queryClient.invalidateQueries({ queryKey: memoKeys.all });
      queryClient.invalidateQueries({ queryKey: ["memo-followup", memoId] });
      queryClient.invalidateQueries({ queryKey: ["meeting-proposal", memoId] });
      window.dispatchEvent(new CustomEvent(MEMO_CHANGED_EVENT, { detail: { memoId } }));
    },
    [queryClient],
  );

  /**
   * After a call: follow the memo until its CRM changes are ready, then the email draft and
   * meeting proposal as they arrive. Each row only appears once it exists for this call.
   */
  const followPostCall = useCallback(
    async (memoId: string, contactName: string | null) => {
      endPostCall();
      const run = { cancelled: false };
      const state: PostCall = {
        memoId,
        contactName,
        stage: "writing",
        changes: [],
        canApprove: false,
        email: null,
        meeting: null,
        notes: false,
        crm: crmNameRef.current,
      };
      postCallRef.current = { run, state, proposed: [] };
      getDesktopBridge()?.shell.setState({ postCall: state });
      const startedAt = Date.now();
      const sleep = (attempt: number) => new Promise((resolve) => window.setTimeout(resolve, pollDelayMs(attempt)));

      let memo: Awaited<ReturnType<typeof memosApi.get>> | null = null;
      for (let attempt = 0; Date.now() - startedAt < POST_CALL_GIVE_UP_MS; attempt++) {
        await sleep(attempt);
        if (run.cancelled) return;
        memo = await memosApi.get(memoId).catch(() => null);
        if (run.cancelled) return;
        if (memo && !isProcessing(memo.status)) break;
        memo = null;
      }
      if (!memo) {
        showPostCall({ stage: "review", note: "Still writing. Open it in Vocify" });
        return;
      }

      const contactId = memo.hubspotContactId || undefined;
      const [preview, proposal, playbook] = await Promise.all([
        memo.status === "pending_review"
          ? (crmApi.getPreview(memoId, undefined, contactId ? { contactId } : undefined).catch(() => null) as Promise<
              { proposed_updates?: ProposedUpdate[] } | null
            >)
          : Promise.resolve(null),
        api.get<{ proposal: Record<string, unknown> | null }>(`/memos/${memoId}/meeting-proposal`).catch(() => null),
        api
          .get<Parameters<typeof callTypeFrom>[0]>(`/memos/${encodeURIComponent(memoId)}/playbook`)
          .catch(() => null),
      ]);
      if (run.cancelled || !postCallRef.current) return;
      postCallRef.current.proposed = preview?.proposed_updates ?? [];
      postCallRef.current.typeOrder = (playbook?.options ?? []).map((option) => option.key);
      const type = callTypeFrom(playbook, typeName);
      const crm = crmFor({ status: memo.status, hubspotContactId: memo.hubspotContactId }, preview?.proposed_updates);
      postCallRef.current.crm = crm;
      postCallRef.current.contactId = contactId;
      showPostCall({
        type,
        ...crmForType(type?.key, crm),
        crmUrl: crm.stage === "done" ? contactUrlRef.current(contactId) : null,
        meeting: meetingFrom(proposal?.proposal ?? null),
        notes: Boolean(memo.extraction?.summary?.trim() || memo.userNotes?.trim()),
        summary: summaryLines(memo.extraction?.summary),
      });

      // The email draft is written after the CRM changes: the card says it's on its way,
      // then shows it once it's ready.
      for (let attempt = 0; Date.now() - startedAt < POST_CALL_GIVE_UP_MS; attempt++) {
        const view = await memosApi.getFollowup(memoId).catch(() => null);
        if (run.cancelled) return;
        const email = emailFrom(view);
        if (email?.state !== postCallRef.current?.state.email?.state) showPostCall({ email });
        if (view && view.status !== "generating") return;
        await sleep(attempt);
        if (run.cancelled) return;
      }
    },
    [endPostCall, showPostCall, typeName],
  );


  /** What the rep chose in the island's card. Every write goes through the same API Vocify uses. */
  const onPostCallAction = useCallback(
    async (action: { type: string; [key: string]: unknown }) => {
      const current = postCallRef.current;
      if (!current) return;
      const { memoId } = current.state;
      const fail = (patch: Partial<PostCall>) => !current.run.cancelled && showPostCall(patch);

      switch (action.type) {
        case "approve": {
          if (current.state.stage !== "ready" || !current.state.canApprove) return;
          const omit = (Array.isArray(action.omit) ? action.omit : []).map(String);
          const edits = action.edits && typeof action.edits === "object" ? (action.edits as Record<string, unknown>) : null;
          // The note as the rep left it in the island; absent when they didn't touch it.
          const note = typeof action.note === "string" ? action.note : null;
          const kept = current.state.changes.length - omit.filter((key) => current.state.changes.some((c) => c.key === key)).length;
          if (kept <= 0) return;
          showPostCall({ stage: "applying", undoUntil: Date.now() + UNDO_MS });
          current.undoTimer = window.setTimeout(async () => {
            if (current.run.cancelled) return;
            try {
              const memo = await memosApi.get(memoId);
              const extraction = buildApproveExtraction({
                // The same record the review screen hands to buildApproveExtraction.
                memoExtraction: (memo.extraction ?? null) as unknown as Record<string, unknown> | null,
                updates: withEdits(current.proposed, edits).filter((update) => !omit.includes(proposedFieldKey(update) ?? "")),
                omittedKeys: omit,
                summary: note !== null ? noteMarkdown(note, memo.extraction?.summary) : memo.extraction?.summary ?? "",
                nextSteps: memo.extraction?.nextSteps ?? [],
              });
              await memosApi.approveForContact(memoId, extraction);
              if (current.run.cancelled) return;
              showPostCall({ stage: "done", applied: kept, undoUntil: undefined, crmUrl: contactUrlRef.current(current.contactId) });
              memoChanged(memoId);
            } catch {
              const crm = current.state.crm ?? "the CRM";
              fail({ stage: "review", canApprove: false, undoUntil: undefined, note: `Couldn't update ${crm}. Review it in Vocify` });
            }
          }, UNDO_MS);
          return;
        }
        case "undo":
          window.clearTimeout(current.undoTimer);
          if (current.state.stage === "applying") showPostCall({ stage: "ready", undoUntil: undefined });
          return;
        case "review":
          // Vocify's memo page has the CRM review, the email and the meeting: the card hands over.
          endPostCall();
          navigate(ROUTES.MEMO_DETAIL(memoId));
          return;
        case "chooseContact":
          // A recording with no contact: the review's fields tab is where the contact is chosen.
          endPostCall();
          navigate(`${ROUTES.MEMO_DETAIL(memoId)}?tab=fields`);
          return;
        case "notes":
        case "openNotes":
          navigate(`${ROUTES.MEMO_DETAIL(memoId)}?tab=note`);
          return;
        case "openEmail":
          navigate(`${ROUTES.MEMO_DETAIL(memoId)}?tab=email`);
          return;
        case "skipEmail": {
          if (current.state.email?.state !== "ready") return;
          const view = await memosApi.skipFollowup(memoId).catch(() => null);
          if (!view) return;
          showPostCall({ email: emailFrom(view) });
          memoChanged(memoId);
          return;
        }
        case "unskipEmail": {
          if (current.state.email?.state !== "skipped") return;
          const view = await memosApi.skipFollowup(memoId, true).catch(() => null);
          if (!view) return;
          showPostCall({ email: emailFrom(view) });
          memoChanged(memoId);
          return;
        }
        case "addMeeting": {
          const meeting = current.state.meeting;
          if (!meeting || meeting.state !== "pending") return;
          try {
            await api.post(`/memos/${memoId}/meeting-proposal/accept`, { decision: "accept", proposal_id: meeting.proposalId });
            showPostCall({ meeting: { ...meeting, state: "added" } });
            memoChanged(memoId);
          } catch {
            fail({ meeting: { ...meeting, state: "check" } });
          }
          return;
        }
        case "setType": {
          const type = current.state.type;
          const next = type ? retypedTo(type, String(action.key ?? ""), current.typeOrder ?? []) : null;
          if (!type || !next) return;
          // The card shows the new type at once; the type goes back if Vocify can't save it.
          // Into or out of internal: the CRM part follows; otherwise it stays as it is.
          const crmChanges = current.crm && (next.key === "internal" || current.state.stage === "internal");
          const before: Partial<PostCall> = {
            type,
            ...(crmChanges ? { stage: current.state.stage, changes: current.state.changes, canApprove: current.state.canApprove, note: current.state.note } : {}),
          };
          showPostCall({ type: next, ...(crmChanges ? crmForType(next.key, current.crm!) : {}) });
          try {
            await playbooksApi.changeMemoPlaybook(memoId, next.key);
            if (current.run.cancelled) return;
            queryClient.invalidateQueries({ queryKey: ["memo-playbook", memoId] });
            memoChanged(memoId);
          } catch {
            if (current.state.type?.key === next.key) fail(before);
          }
          return;
        }
        case "dismiss":
          endPostCall();
          return;
      }
    },
    [endPostCall, memoChanged, navigate, queryClient, showPostCall],
  );
  const onPostCallActionRef = useRef(onPostCallAction);
  onPostCallActionRef.current = onPostCallAction;

  /**
   * After a Vocify call: the carrier's recording becomes the memo on the server. Wait for that
   * memo (GET /calls/{sid}), then follow it in the island like a recorded meeting.
   */
  const followCallMemo = useCallback(
    async (callSid: string, contactName: string | null) => {
      const bridge = getDesktopBridge();
      let since: number | null = null;
      for (;;) {
        const summary = (await callsApi.getCall(callSid).catch(() => null)) as CallSummary | null;
        if (summary?.memoId) {
          bridge?.shell.setState({ finish: null });
          navigate(ROUTES.MEMO_DETAIL(summary.memoId));
          void followPostCall(summary.memoId, contactName);
          return;
        }
        const resolution = afterCallResolution(summary);
        if (resolution) {
          const message = resolution === "no_answer" ? "No conversation on this call." : "The call failed.";
          bridge?.shell.setState({ finish: { step: "failed", message } });
          return;
        }
        const next = afterCallPoll(summary, since, Date.now());
        if (!next.interval) {
          bridge?.shell.setState({
            finish: { step: "failed", message: "Still processing the call. It will show up in Vocify." },
          });
          return;
        }
        since = next.since;
        await new Promise((resolve) => window.setTimeout(resolve, next.interval as number));
      }
    },
    [followPostCall, navigate],
  );

  const stop = useCallback(async () => {
    if (phaseRef.current !== "live") return;
    setPhase("stopping");
    pausedRef.current = false;
    setPaused(false);
    const bridge = getDesktopBridge();
    // The pill goes away on the click; finishing the transcript happens behind it.
    // The island keeps a spinner for the ended call until its memo is being written: say where it is.
    bridge?.shell.setState({ listening: false, liveType: null, finish: { step: "stopping" } });
    void bridge?.shell.hideOverlay();
    await releaseAudio();
    if (nativeRef.current) {
      nativeRef.current = false;
      // The Mac waits for the last words before answering.
      const finished = await bridge?.recorder?.stop();
      if (finished?.transcript) transcriptRef.current = normalizeMeetingTranscript(finished.transcript);
    } else {
      await drainSocket();
    }

    transcriptRef.current = settleMeeting(transcriptRef.current);
    const draft = currentDraft();
    draftRef.current = null;
    setContact(null);
    if (saveTimerRef.current) {
      window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    const call = vocifyCallRef.current;
    if (call) {
      vocifyCallRef.current = null;
      clearNotes();
      updateTranscript(EMPTY_MEETING_TRANSCRIPT);
      setPhase("idle");
      bridge?.shell.setState({ finish: { step: "uploading" } });
      const contactName = draft?.contact?.name ?? null;
      // The live transcript is the memo, seconds after hang-up. Twilio's recording joins the same memo
      // later (playback, CRM call log); if this upload fails, the recording makes the memo as before.
      if (draft && meetingHasSpeech(draft.transcript)) {
        try {
          const memo = await memosApi.uploadTranscriptAndExtract(meetingUploadText(draft.transcript), {
            interactionKind: "call",
            sourceType: "meeting_transcript",
            speakersVerified: true,
            notes: draft.notes,
            hubspotContactId: draft.contact?.hubspotId,
            callSource: VOCIFY_CALL_SOURCE.name,
            salesMotionKey: draft.type,
            typeSource: draft.typeSource ?? "vocify",
            participants: meetingParticipants(draft.transcript),
            callSid: call.callSid,
            callDurationSeconds: Math.round((Date.now() - draft.startedAt) / 1000),
          });
          reportCallStep("live-memo", { memoId: memo.id });
          queryClient.invalidateQueries({ queryKey: memoKeys.lists() });
          bridge?.shell.setState({ finish: null });
          navigate(ROUTES.MEMO_DETAIL(memo.id));
          void followPostCall(memo.id, contactName);
          return;
        } catch (e) {
          reportCallStep("live-memo-failed", { message: e instanceof Error ? e.message : String(e) });
        }
      }
      void followCallMemo(call.callSid, contactName);
      return;
    }
    if (!draft || !meetingHasSpeech(draft.transcript)) {
      if (draft) void bridge?.drafts?.remove(draft.id);
      updateTranscript(EMPTY_MEETING_TRANSCRIPT);
      setPhase("idle");
      const nothing = "Nothing was transcribed. Check the meeting isn't muted.";
      bridge?.shell.setState({ finish: { step: "failed", message: nothing } });
      fail(nothing);
      return;
    }
    await bridge?.drafts?.save(draft);

    setPhase("uploading");
    bridge?.shell.setState({ finish: { step: "uploading" } });
    try {
      const memoId = await sendDraft(draft);
      clearNotes();
      updateTranscript(EMPTY_MEETING_TRANSCRIPT);
      setPhase("idle");
      navigate(ROUTES.MEMO_DETAIL(memoId));
      bridge?.shell.setState({ finish: null });
      void followPostCall(memoId, draft.contact?.name ?? null);
    } catch {
      setPending((list) => [...list, draft]);
      clearNotes();
      updateTranscript(EMPTY_MEETING_TRANSCRIPT);
      setPhase("idle");
      const isMac = desktopPlatform() === "darwin";
      const unsent = bridge?.drafts
        ? `Couldn't send the meeting. It's saved on this ${isMac ? "Mac" : "computer"}.`
        : "Couldn't send the meeting. Retry before closing Vocify.";
      bridge?.shell.setState({ finish: { step: "failed", message: unsent } });
      fail(unsent);
    }
  }, [clearNotes, currentDraft, drainSocket, fail, followCallMemo, followPostCall, navigate, queryClient, releaseAudio, sendDraft, setPhase, updateTranscript]);

  const start = useCallback(async (call?: VocifyCallSession, options?: { stay?: boolean }) => {
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
      // A Vocify call already holds the mic and has the prospect's side: no system audio needed.
      if (!call) {
        const perm = await bridge.permissions.status();
        if (normalizePermissionStatus(perm.microphone) !== "authorized") {
          throw new Error("Allow Microphone in the panel above, then try again.");
        }
        if (normalizePermissionStatus(perm.systemAudio) !== "authorized") {
          throw new Error("Allow system audio in the panel above, then try again.");
        }
      }

      const systemAudioError = (reason?: string) => {
        const isMac = desktopPlatform() === "darwin";
        if (reason === "needs_restart" && isMac) {
          return new Error("System audio is on but Vocify needs a restart. Quit (⌘Q) and reopen, then record again.");
        }
        return new Error("Allow system audio in the panel above, then try again.");
      };

      // The live service takes no session of its own: a ticket from the API, valid for the day.
      // (A call asked for it while it rang, so this is usually instant.)
      ticketRef.current = await liveTickets.get(user.id);

      // The Mac app records natively when it can: no web audio, so nothing waits on this page.
      const recorder = call ? undefined : bridge.recorder;
      let ctx: AudioContext | null = null;
      let micStream: MediaStream | null = null;
      if (recorder) {
        const started = await recorder.start({ url: liveTranscriptionWsUrl(user.id), ticket: ticketRef.current ?? undefined });
        if (!started.ok) {
          if (started.reason === "no_microphone") throw new Error("Could not open the microphone.");
          throw systemAudioError(started.reason);
        }
        nativeRef.current = true;
      } else {
        if (!call) {
          micStream = await navigator.mediaDevices
            .getUserMedia({
              audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
            })
            .catch(() => {
              throw new Error("Could not open the microphone.");
            });
          micRef.current = micStream;

          const native = await bridge.systemAudio.start();
          if (!native.ok) throw systemAudioError(native.reason);
        }

        ctx = new AudioContext({ sampleRate: LIVE_STT_SAMPLE_RATE });
        ctxRef.current = ctx;
        if (call) reportCallStep("session-audio", { state: ctx.state });
        if (ctx.state === "suspended") await ctx.resume();
        if (call) reportCallStep("session-audio-ready", { state: ctx.state });
      }

      const startedAt = Date.now();
      const callContact = call ? call.contact : callContactRef.current;
      const callSource = call ? VOCIFY_CALL_SOURCE : callSourceRef.current;
      vocifyCallRef.current = call ?? null;
      draftRef.current = {
        id: newDraftId(),
        startedAt,
        ...(callContact ? { contact: callContact } : {}),
        ...(callSource ? { source: callSource } : {}),
      };
      setContact(callContact);
      typeOptionsRef.current = [];
      proposalRef.current = { attempts: 0, total: 0, lastConfident: false, busy: false };
      allTypesRef.current = null;
      applyCallType(NO_CALL_TYPE);
      setCallMode(assistCallMode(callKind(draftRef.current ?? {})));
      setLiveHelpOverride(null);
      endPostCall();
      clearNotes();
      updateTranscript(EMPTY_MEETING_TRANSCRIPT);
      firstWordsRef.current = {};
      reconnectsRef.current = 0;
      setPhase("live");
      if (!options?.stay) navigate(ROUTES.RECORD);

      const onCallAudioLost = () => {
        // The Mac already tried to restart it: the island must say so, the window may be hidden.
        setWarning("Meeting audio stopped. Your mic is still recording.");
        bridge.shell.setState({ callAudioLost: true });
      };
      if (recorder) {
        releaseAudioRef.current = [
          recorder.onTranscript((raw) => updateTranscript(normalizeMeetingTranscript(raw))),
          recorder.onLevels((next) => {
            levelRef.current = next;
            // Shown as they arrive (4 a second): the meter timer runs once a second while this window is
            // hidden, which made live help notice the prospect's pause up to a second late.
            setLevels((prev) =>
              prev.you === levelStep(next.you) && prev.them === levelStep(next.them)
                ? prev
                : { you: levelStep(next.you), them: levelStep(next.them) },
            );
          }),
          recorder.onWarning(({ text }) => setWarning(text)),
          bridge.systemAudio.onLost?.(onCallAudioLost) ?? (() => {}),
        ];
      } else if (ctx && (micStream || call)) {
        // A Vocify call knows who it is with; a meeting recorded here is named from the meeting app's readings.
        speakersRef.current = call ? null : { timeline: new SpeakerTimeline(), clockAt: null };
        // A Vocify call has the two sides as separate streams already; a meeting is the mic plus what the PC plays.
        echoRef.current = call ? null : new EchoSuppressor();
        openSocket();
        let levelsSentAt = 0;
        const send = (channel: MeetingSpeaker) => (heard: ArrayBuffer) => {
          const side = channel === "rep" ? "you" : "them";
          let pcm = heard;
          const echo = echoRef.current;
          if (echo) {
            // The mic hears the meeting through the speakers: what is only that echo is not the rep.
            if (channel === "prospect") echo.pushCall(new Int16Array(heard), performance.now());
            else pcm = echo.process(new Int16Array(heard), performance.now()).buffer as ArrayBuffer;
          }
          // Paused: send silence so the session stays open and both channels keep one clock.
          const audio = pausedRef.current ? new ArrayBuffer(pcm.byteLength) : pcm;
          if (!pausedRef.current) {
            levelRef.current[side] = Math.max(levelRef.current[side] * 0.85, pcmLevel(pcm));
            // Pushed from the audio callbacks, not a timer: timers stall while Vocify is behind the call.
            const now = performance.now();
            if (now - levelsSentAt > 100) {
              levelsSentAt = now;
              bridge.shell.setState({ levels: { ...levelRef.current } });
            }
          }
          const ws = wsRef.current;
          if (ws?.readyState === WebSocket.OPEN) {
            ws.send(encodeChannelAudio(channel, audio));
            // The other side's audio clock starts with its first frame sent (result times count from it).
            const speakers = speakersRef.current;
            if (channel === "prospect" && speakers && speakers.clockAt === null) speakers.clockAt = performance.now();
          }
        };
        releaseAudioRef.current = call
          ? // The call's own two sides: nothing else on the Mac reaches the prospect's channel.
            [hookMicPcm(ctx, call.streams.local, send("rep")), hookMicPcm(ctx, call.streams.remote, send("prospect"))]
          : [
              hookMicPcm(ctx, micStream as MediaStream, send("rep")),
              bridge.systemAudio.onPcm(send("prospect")),
              bridge.systemAudio.onLost?.(onCallAudioLost) ?? (() => {}),
              // Who the meeting app shows speaking (the desktop app reads Zoom, and Meet through the extension).
              bridge.speakers?.onSpeaking?.(({ names }) => {
                const speakers = speakersRef.current;
                if (!speakers || speakers.clockAt === null || !Array.isArray(names)) return;
                speakers.timeline.record((performance.now() - speakers.clockAt) / 1000, names);
              }) ?? (() => {}),
            ];
      }

      setElapsed("00:00");
      pausedRef.current = false;
      pausedTotalRef.current = 0;
      setPaused(false);
      timerRef.current = window.setInterval(() => {
        const { you, them } = levelRef.current;
        setLevels((prev) =>
          prev.you === levelStep(you) && prev.them === levelStep(them)
            ? prev
            : { you: levelStep(you), them: levelStep(them) },
        );
        levelRef.current = { you: you * 0.6, them: them * 0.6 };
        // Computed every tick from the wall clock, so a throttled timer never shows a stale time.
        const now = Date.now();
        const held = pausedTotalRef.current + (pausedRef.current ? now - pausedAtRef.current : 0);
        setElapsed(formatElapsed(now - startedAt - held));
      }, 125);
      bridge.shell.setState({
        listening: true,
        callAudioLost: false,
        paused: false,
        clock: meetingClock(),
        levels: { you: 0, them: 0 },
        lastLine: "",
        overlay: meetingOverlay(EMPTY_MEETING_TRANSCRIPT),
      });
      await bridge.shell.showOverlay();
      // The island offers the company's call types, starting from Vocify's free guess
      // (the last conversation with this contact, else the routing rule).
      void playbooksApi
        .list()
        .then(async (list) => {
          if (phaseRef.current !== "live") return;
          allTypesRef.current = { options: typeOptions(list, t.product.interactions.internal, (key) => typeName(key)), payload: list };
          typeOptionsRef.current = optionsForCall();
          applyCallType(callTypeRef.current);
          await guessCallType();
        })
        .catch(() => {});
    } catch (e) {
      if (call) reportCallStep("session-failed", { message: e instanceof Error ? e.message : String(e) });
      draftRef.current = null;
      vocifyCallRef.current = null;
      if (nativeRef.current) {
        nativeRef.current = false;
        await bridge.recorder?.stop();
      }
      await releaseAudio();
      wsRef.current?.close();
      wsRef.current = null;
      setPhase("idle");
      fail(e instanceof Error && e.message ? e.message : "Could not start recording.");
      // A start from the notch island happens with Vocify in the background: bring the error forward.
      void bridge.shell.hideOverlay();
      bridge.shell.command("show");
    }
  }, [applyCallType, clearNotes, endPostCall, fail, meetingClock, navigate, openSocket, releaseAudio, setPhase, t, typeName, updateTranscript, user?.id]);

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
      if (failed.length) {
        const isMac = desktopPlatform() === "darwin";
        setError(`Couldn't send the meeting. It's saved on this ${isMac ? "Mac" : "computer"}.`);
      }
    })();
  }, [navigate, sendAll, user?.id]);

  startRef.current = start;
  pauseRef.current = pause;
  resumeRef.current = resume;
  stopRef.current = stop;

  useEffect(() => {
    const bridge = getDesktopBridge();
    if (!bridge) return;
    return bridge.shell.onCommand((name) => {
      const current = phaseRef.current;
      if (isCallUp(callEngine.getState())) {
        // During a Vocify call the island's Stop hangs up; nothing else may start a second recording.
        if (name === "stop") callEngine.hangup();
        return;
      }
      if (name === "stop" || (name === "toggle" && current === "live")) {
        void stopRef.current();
      } else if (name === "listen" || (name === "toggle" && current === "idle")) {
        navigate(ROUTES.RECORD);
        void startRef.current();
      } else if (name === "pause") {
        pauseRef.current();
      } else if (name === "resume") {
        resumeRef.current();
      } else if (name === "assist-on" || name === "assist-off") {
        // Live help switched from the island: this call only.
        if (phaseRef.current === "live") setLiveHelpOverride(name === "assist-on");
      }
    });
  }, [navigate]);

  useEffect(() => {
    const bridge = getDesktopBridge();
    if (!bridge?.shell.onPostCallAction) return;
    return bridge.shell.onPostCallAction((action) => void onPostCallActionRef.current(action));
  }, []);

  // The island detected a call: name the CRM contact on screen for its call menu.
  useEffect(() => {
    const bridge = getDesktopBridge();
    if (!bridge?.crm) return;
    const lookups = latestOnly();
    return bridge.crm.onCallPages(({ urls }) => {
      const ticket = lookups.next();
      if (!api.getToken()) return;
      api
        .post<CallPreview>("/live-calls/preview", { page_urls: urls })
        .then((preview) => {
          if (!lookups.isLatest(ticket)) return;
          // Memos store HubSpot contacts; the next recording takes this one.
          callContactRef.current =
            preview.provider === "hubspot" && preview.contact_id
              ? { hubspotId: preview.contact_id, name: preview.contact_name?.trim() || null }
              : null;
          bridge.shell.setState({ callContact: islandCallContact(preview) });
          // The rep may have pressed Record before the page was read: the recording takes it too.
          const draft = draftRef.current;
          if (draft && !draft.contact && callContactRef.current) {
            draft.contact = callContactRef.current;
            setContact(callContactRef.current);
          }
        })
        .catch(() => {
          // No name: the island keeps showing the app.
        });
    });
  }, []);

  // The call ended: its contact must not stick to the next one.
  useEffect(() => {
    const bridge = getDesktopBridge();
    if (!bridge?.crm?.onCallEnded) return;
    return bridge.crm.onCallEnded(() => {
      callContactRef.current = null;
      callSourceRef.current = null;
      bridge.shell.setState({ callContact: null });
    });
  }, []);

  // The call type the rep picked in the island while recording.
  useEffect(() => {
    const bridge = getDesktopBridge();
    if (!bridge?.shell.onCallType) return;
    return bridge.shell.onCallType(({ key }) => {
      if (!draftRef.current) return;
      applyCallType(withPick(callTypeRef.current, key || null));
    });
  }, [applyCallType]);

  // The channel the rep switched to in the island (types by channel): the types, the proposals and
  // live help follow it. A Vocify call is a call by construction and never switches.
  useEffect(() => {
    const bridge = getDesktopBridge();
    if (!bridge?.shell.onCallChannel) return;
    return bridge.shell.onCallChannel(({ kind }) => {
      const draft = draftRef.current;
      const all = allTypesRef.current;
      if (!draft || !all || !byChannel(all.payload) || vocifyCallRef.current) return;
      if (!LIVE_CHANNELS.includes(kind) || callKind(draft) === kind) return;
      draft.channel = kind;
      typeOptionsRef.current = optionsForCall();
      proposalRef.current.attempts = 0;
      proposalRef.current.lastConfident = false;
      setCallMode(assistCallMode(kind));
      const next = withChannelTypes(callTypeRef.current, typeOptionsRef.current.map((option) => option.key));
      applyCallType(next);
      scheduleSave();
      if (!next.rep && !next.vocify) void guessCallType();
    });
  }, [applyCallType, guessCallType, optionsForCall, scheduleSave]);

  // Where the call happens; a recording that already started without it picks it up.
  useEffect(() => {
    const bridge = getDesktopBridge();
    if (!bridge?.crm?.onCallSource) return;
    return bridge.crm.onCallSource((source) => {
      callSourceRef.current = source;
      if (source && draftRef.current && !draftRef.current.source) {
        draftRef.current.source = source;
        setCallMode(assistCallMode(callKind(draftRef.current)));
      }
    });
  }, []);

  // Leaving the dashboard mid-meeting (e.g. signing out) keeps the transcript on disk.
  useEffect(
    () => () => {
      saveDraftNow();
      draftRef.current = null;
      phaseRef.current = "idle";
      void releaseAudio();
      if (nativeRef.current) {
        nativeRef.current = false;
        void getDesktopBridge()?.recorder?.stop();
      }
      wsRef.current?.close();
      wsRef.current = null;
      const bridge = getDesktopBridge();
      bridge?.shell.setState({ listening: false, liveType: null });
      void bridge?.shell.hideOverlay();
    },
    [releaseAudio, saveDraftNow],
  );

  const turns = useMemo(() => meetingDisplayTurns(transcript), [transcript]);

  // One model proposal once the conversation says enough, a second only if it was unsure.
  useEffect(() => {
    // Only Interna offered (a channel with no types): nothing to propose, and no proposal spent.
    if (phase !== "live" || !typeOptionsRef.current.some((option) => option.key !== "internal")) return;
    const lines = turns.filter((turn) => turn.text.trim()).map((turn) => (turn.label ? `${turn.label}: ${turn.text}` : turn.text));
    const words = lines.reduce((sum, line) => sum + line.split(/\s+/).length, 0);
    const state = proposalRef.current;
    const picked = Boolean(callTypeRef.current.rep);
    if (state.busy || !proposalDue({ words, attempts: state.attempts, picked, lastConfident: state.lastConfident, total: state.total })) return;
    state.busy = true;
    state.attempts += 1;
    state.total += 1;
    const draft = draftRef.current;
    const kind = callKind(draft ?? {});
    void api
      .post<{ type: string | null; confident: boolean }>("/copilot/call-type/propose", {
        transcript_window: lines.join("\n").slice(-6000),
        options: typeOptionsRef.current,
        interaction_kind: kind,
      })
      .then((proposal) => {
        // A proposal for the channel the call had before a switch is dropped.
        if (phaseRef.current !== "live" || draftRef.current !== draft || callKind(draftRef.current ?? {}) !== kind) return;
        state.lastConfident = proposal.confident;
        if (proposal.type) applyCallType(withProposal(callTypeRef.current, proposal.type));
      })
      .catch(() => {})
      .finally(() => {
        state.busy = false;
      });
  }, [phase, turns, applyCallType]);

  const shownCallType = useMemo(() => callTypeShown(callType), [callType]);
  // Separate entry points, so a click handler's event is never taken for a call session.
  const startMeeting = useCallback(() => start(), [start]);
  const startHere = useCallback(async () => {
    await start(undefined, { stay: true });
    return phaseRef.current === "live";
  }, [start]);
  const startCall = useCallback((session: VocifyCallSession) => start(session), [start]);
  const followCall = useCallback(
    (callSid: string, contactName: string | null) => {
      getDesktopBridge()?.shell.setState({ finish: { step: "uploading" } });
      void followCallMemo(callSid, contactName);
    },
    [followCallMemo],
  );

  const value = useMemo<DesktopMeeting>(
    () => ({
      available,
      phase,
      elapsed,
      paused,
      pause,
      resume,
      levels,
      error,
      warning,
      turns,
      notes,
      setNotes,
      pending,
      savedOnDevice,
      contact,
      callType: shownCallType,
      callMode,
      liveHelpOverride,
      start: startMeeting,
      startHere,
      startCall,
      followCall,
      stop,
      retryPending,
    }),
    [available, phase, elapsed, paused, pause, resume, levels, error, warning, turns, notes, setNotes, pending, savedOnDevice, contact, shownCallType, callMode, liveHelpOverride, startMeeting, startHere, startCall, followCall, stop, retryPending],
  );

  return <DesktopMeetingContext.Provider value={value}>{children}</DesktopMeetingContext.Provider>;
}

/** A recording is on (desktop app only): a Vocify call must not start on top of it. Safe outside the provider. */
export function useRecordingBusy(): boolean {
  const ctx = useContext(DesktopMeetingContext);
  return Boolean(ctx && ctx.phase !== "idle");
}

export function useDesktopMeeting(): DesktopMeeting {
  const ctx = useContext(DesktopMeetingContext);
  if (!ctx) throw new Error("useDesktopMeeting must be used inside DesktopMeetingProvider");
  return ctx;
}
