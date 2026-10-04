import { useEffect, useRef, useState } from "react";
import { Mic, Square, X } from "lucide-react";
import { IconAction } from "@/components/ui/icon-action";
import { useLanguage } from "@/lib/i18n";
import {
  cancelVoice,
  idleVoice,
  permissionDenied,
  startRecording,
  stopRecording,
  transcriptionReady,
  type VoiceComposerState,
} from "@/lib/ask-voice";

export default function VoiceComposer({
  onText,
  transcribe,
}: {
  onText: (text: string) => void;
  transcribe?: (blob: Blob) => Promise<string>;
}) {
  const { t } = useLanguage();
  const [view, setView] = useState<VoiceComposerState>(idleVoice());
  const started = useRef<number | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);

  const [seconds, setSeconds] = useState(0);

  function releaseTracks() {
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
    recorder.current = null;
  }

  useEffect(() => () => releaseTracks(), []);

  useEffect(() => {
    if (view.composer_state !== "recording") return;
    const timer = window.setInterval(() => {
      if (!started.current) return;
      setSeconds(Math.floor((Date.now() - started.current) / 1000));
    }, 250);
    return () => window.clearInterval(timer);
  }, [view.composer_state]);

  async function record() {
    if (!navigator.mediaDevices?.getUserMedia) {
      setView((current) => permissionDenied(current));
      return;
    }
    try {
      const live = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.current = live;
      chunks.current = [];
      const media = new MediaRecorder(live);
      recorder.current = media;
      media.ondataavailable = (event) => {
        if (event.data.size > 0) chunks.current.push(event.data);
      };
      media.start();
      started.current = Date.now();
      setSeconds(0);
      setView((current) => startRecording(current));
    } catch {
      releaseTracks();
      setView((current) => permissionDenied(current));
    }
  }

  function cancel() {
    if (recorder.current && recorder.current.state !== "inactive") recorder.current.stop();
    releaseTracks();
    started.current = null;
    setView((current) => cancelVoice(current));
  }

  function stop() {
    const elapsed = started.current ? Date.now() - started.current : view.elapsed_ms;
    started.current = null;
    const media = recorder.current;
    const finish = (blob: Blob) => {
      releaseTracks();
      setView((current) => stopRecording(current, elapsed));
      if (!transcribe) return;
      void transcribe(blob)
        .then((spoken) => {
          const text = spoken.trim();
          if (!text) {
            setView((current) => cancelVoice(current, { silence: true }));
            return;
          }
          setView((current) => {
            const ready = transcriptionReady(current, text);
            onText(ready.text);
            return ready;
          });
        })
        .catch(() => {
          setView((current) => permissionDenied(current));
        });
    };
    if (media && media.state !== "inactive") {
      media.onstop = () => finish(new Blob(chunks.current, { type: "audio/webm" }));
      media.stop();
      return;
    }
    finish(new Blob(chunks.current, { type: "audio/webm" }));
  }

  const status =
    view.composer_state === "recording"
      ? t.product.askRecording.replace("{seconds}", String(seconds))
      : view.composer_state === "transcribing"
        ? t.product.askTranscribing
        : view.composer_state === "permission_denied"
          ? t.product.askNoMic
          : null;

  return (
    <div className="flex shrink-0 items-center gap-0.5">
      {status ? (
        <span className="sr-only" role="status">
          {status}
        </span>
      ) : null}
      {view.composer_state === "recording" ? (
        <span className="ask-enter mr-1 inline-flex items-center gap-1.5 text-[12.5px] tabular-nums text-foreground" aria-hidden="true">
          <span className="animate-recording-pulse h-2 w-2 rounded-full bg-destructive" />
          {`${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`}
        </span>
      ) : null}
      {view.composer_state === "transcribing" ? (
        <span className="ask-shimmer mr-1 text-[12.5px]" aria-hidden="true">
          {t.product.askTranscribing}
        </span>
      ) : null}
      {view.composer_state !== "recording" && view.composer_state !== "transcribing" ? (
        <IconAction label={t.product.askRecord} onClick={() => void record()}>
          <Mic size={17} strokeWidth={1.5} />
        </IconAction>
      ) : null}
      {view.composer_state === "recording" ? (
        <>
          <IconAction label={t.product.cancelAction} tone="danger" onClick={cancel}>
            <X size={16} strokeWidth={1.5} />
          </IconAction>
          <IconAction label={t.product.askStop} onClick={() => void stop()}>
            <Square size={14} strokeWidth={1.5} fill="currentColor" />
          </IconAction>
        </>
      ) : null}
      {view.composer_state === "transcribing" ? (
        <IconAction label={t.product.askTranscribing} disabled pending onClick={() => undefined}>
          <Mic size={17} strokeWidth={1.5} />
        </IconAction>
      ) : null}
    </div>
  );
}
