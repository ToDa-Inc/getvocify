import { useCallback, useEffect, useState } from "react";
import { Check, Mic, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useRealtimeTranscription } from "@/features/recording";
import {
  deleteVoiceEnrollment,
  fetchVoiceEnrollmentStatus,
  saveVoiceEnrollment,
  type VoiceEnrollmentStatus,
} from "../api/voiceEnrollment";

interface VoiceEnrollmentPanelProps {
  userId: string;
  onEnrollmentChange?: (enrolled: boolean) => void;
}

/**
 * One-script voice enrollment: user reads a short text alone (~15–25s).
 * Speechmatics returns speaker identifiers; we store them with explicit consent.
 */
export function VoiceEnrollmentPanel({
  userId,
  onEnrollmentChange,
}: VoiceEnrollmentPanelProps) {
  const [status, setStatus] = useState<VoiceEnrollmentStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [consent, setConsent] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState<"idle" | "recording" | "captured">("idle");
  const [capturedIds, setCapturedIds] = useState<string[] | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await fetchVoiceEnrollmentStatus();
      setStatus(next);
      onEnrollmentChange?.(next.enrolled);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar el estado de la voz");
    } finally {
      setLoading(false);
    }
  }, [onEnrollmentChange]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const {
    isTranscribing,
    isConnected,
    error: sttError,
    fullTranscript,
    pendingSpeakerIdentifiers,
    start,
    stop,
    reset,
  } = useRealtimeTranscription(userId, "multi", { mode: "enroll" });

  useEffect(() => {
    if (!pendingSpeakerIdentifiers) return;
    if (!pendingSpeakerIdentifiers.length) {
      setError(
        "No se pudo crear la muestra de voz — prueba en un sitio silencioso y lee el texto completo."
      );
      setPhase("idle");
      return;
    }
    setCapturedIds(pendingSpeakerIdentifiers);
    setPhase("captured");
    stop();
  }, [pendingSpeakerIdentifiers, stop]);

  const handleStart = async () => {
    if (!consent) {
      setError("Confirma el consentimiento antes de grabar tu muestra de voz.");
      return;
    }
    setError(null);
    setCapturedIds(null);
    setPhase("recording");
    reset();
    await start();
  };

  const handleStop = () => {
    // EndOfStream triggers SpeakersResult when get_speakers=true
    stop();
    setPhase("recording");
    setError(null);
  };

  const handleSave = async () => {
    if (!capturedIds?.length) {
      setError("Aún no hay muestra — graba el texto una vez y luego guarda.");
      return;
    }
    if (!consent) {
      setError("El consentimiento es obligatorio para guardar tu voz.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const next = await saveVoiceEnrollment({
        speaker_identifiers: capturedIds,
        consent: true,
        sample_count: 1,
      });
      setStatus(next);
      onEnrollmentChange?.(next.enrolled);
      setPhase("idle");
      setCapturedIds(null);
      reset();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar la voz");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    setSaving(true);
    setError(null);
    try {
      await deleteVoiceEnrollment();
      setCapturedIds(null);
      setPhase("idle");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo eliminar la voz");
    } finally {
      setSaving(false);
    }
  };

  if (loading && !status) {
    return (
      <section className="rounded-3xl border border-border/40 bg-white/70 p-5 text-sm text-muted-foreground">
        Cargando configuración de voz…
      </section>
    );
  }

  return (
    <section className="rounded-3xl border border-border/40 bg-white/70 p-5 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-xs font-black uppercase tracking-widest text-muted-foreground">
            Tu voz (una sola vez)
          </h2>
          <p className="text-sm text-muted-foreground mt-1 max-w-xl leading-relaxed">
            Grábate leyendo el texto de abajo — solo tú, unos 15–25 segundos.
            Así Call Copilot distingue <em>tu</em> voz de la del prospecto con el altavoz.
            No hace falta grabar docenas de llamadas.
          </p>
        </div>
        {status?.enrolled && (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 px-2.5 py-1 text-[10px] font-black uppercase tracking-widest shrink-0">
            <Check className="h-3 w-3" />
            Lista
          </span>
        )}
      </div>

      <div className="rounded-2xl bg-cream/70 p-4 text-sm leading-relaxed text-foreground">
        {status?.script || "Cargando texto…"}
      </div>

      <label className="flex items-start gap-2 text-xs text-muted-foreground cursor-pointer">
        <input
          type="checkbox"
          className="mt-0.5"
          checked={consent}
          onChange={(e) => setConsent(e.target.checked)}
        />
        <span>
          Consiento que Vocify cree una representación de mi voz a partir de esta
          grabación para distinguirla en llamadas en vivo. Puedo eliminarla cuando quiera.
        </span>
      </label>

      {(error || sttError) && (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {error || sttError}
        </div>
      )}

      {phase === "recording" && (
        <p className="text-xs text-muted-foreground">
          {isTranscribing
            ? isConnected
              ? "Escuchando — lee el texto con naturalidad y pulsa Parar al terminar…"
              : "Conectando…"
            : "Terminando la muestra — un segundo…"}
          {fullTranscript ? (
            <span className="block mt-1 text-foreground/80 line-clamp-2">{fullTranscript}</span>
          ) : null}
        </p>
      )}

      {phase === "captured" && (
        <p className="text-xs text-emerald-700 font-medium">
          Muestra capturada. Guárdala para usarla en la siguiente llamada.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {!isTranscribing ? (
          <Button
            size="sm"
            className="rounded-full text-xs font-bold gap-1.5"
            onClick={() => void handleStart()}
            disabled={!consent || saving}
          >
            <Mic className="h-3.5 w-3.5" />
            {status?.enrolled ? "Volver a grabar" : "Grabar muestra"}
          </Button>
        ) : (
          <Button
            size="sm"
            variant="outline"
            className="rounded-full text-xs font-bold"
            onClick={handleStop}
          >
            Parar
          </Button>
        )}

        {phase === "captured" && (
          <Button
            size="sm"
            className="rounded-full text-xs font-bold"
            onClick={() => void handleSave()}
            disabled={saving || !consent}
          >
            {saving ? "Guardando…" : "Guardar voz"}
          </Button>
        )}

        {status?.enrolled && (
          <Button
            size="sm"
            variant="ghost"
            className="rounded-full text-xs font-bold text-red-600 gap-1"
            onClick={() => void handleDelete()}
            disabled={saving || isTranscribing}
          >
            <Trash2 className="h-3.5 w-3.5" />
            Eliminar
          </Button>
        )}
      </div>
    </section>
  );
}
