import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
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

  return (
    <div className="flex flex-wrap items-center gap-2">
      {view.composer_state === "recording" ? (
        <span className="text-sm text-muted-foreground" role="status">
          {t.product.askRecording.replace("{seconds}", String(seconds))}
        </span>
      ) : null}
      {view.composer_state === "transcribing" ? (
        <span className="text-sm text-muted-foreground" role="status">{t.product.askTranscribing}</span>
      ) : null}
      {view.composer_state === "permission_denied" ? (
        <span className="text-sm text-muted-foreground" role="status">
          {t.product.askNoMic}
        </span>
      ) : null}
      {view.composer_state !== "recording" ? (
        <Button type="button" variant="outline" size="sm" onClick={() => void record()}>
          {t.product.askRecord}
        </Button>
      ) : (
        <>
          <Button type="button" variant="outline" size="sm" onClick={() => void stop()}>
            {t.product.askStop}
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={cancel}>
            {t.product.cancelAction}
          </Button>
        </>
      )}
    </div>
  );
}
