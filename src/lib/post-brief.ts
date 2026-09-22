/** Six brief states. A failed retry keeps the sections that already exist. */

export type BriefHighlight = {
  highlight_mode: "immediate" | "deferred" | "end_of_day";
  highlight_at: string;
  timezone: string;
};

export type BriefView = {
  status: "pending" | "partial" | "ready" | "skipped" | "unavailable" | "failed";
  reason: string | null;
  input_revision: string;
  sections: Array<{ kind: string; evidence_refs: string[]; quote?: string | null; offset_ms?: number | null }>;
  audio_available: boolean;
  strength: string | null;
  improvement: string | null;
  waiting: boolean;
  highlight?: BriefHighlight;
};

export type BriefSurface = {
  title: string;
  revision: string;
  waiting: boolean;
  strength: string | null;
  improvement: string | null;
  sections: BriefView["sections"];
  playable: boolean;
  audioNote: string | null;
  highlightNote: string | null;
};

export function highlightScheduleLine(highlight: BriefHighlight | undefined): string | null {
  if (!highlight || highlight.highlight_mode === "immediate") return null;
  const when = new Date(highlight.highlight_at);
  if (Number.isNaN(when.getTime())) return null;
  const tz = highlight.timezone || "Europe/Madrid";
  const hour = new Intl.DateTimeFormat("es-ES", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: tz,
  }).format(when);
  return `Se destaca a las ${hour}`;
}

const TITLES: Record<BriefView["status"], string> = {
  pending: "Preparando el resumen",
  partial: "Resumen parcial",
  ready: "Resumen de la conversación",
  skipped: "No hay conversación que resumir",
  unavailable: "Falta configurar el proceso",
  failed: "No se pudo completar el resumen",
};

export function briefSurface(brief: BriefView): BriefSurface {
  const sections = brief.sections.map((section) => ({ ...section }));
  const quoteWithoutAudio = sections.some((section) => section.quote && !brief.audio_available);
  return {
    title: brief.reason === "not_started" ? "El resumen todavía no está listo" : TITLES[brief.status],
    revision: brief.input_revision,
    waiting: brief.status === "pending" && brief.waiting,
    strength: brief.strength,
    improvement: brief.improvement,
    sections,
    playable: brief.audio_available && sections.some((section) => section.offset_ms != null),
    audioNote: quoteWithoutAudio ? "Audio no disponible" : null,
    highlightNote: highlightScheduleLine(brief.highlight),
  };
}

export function retryBrief(current: BriefView): BriefView {
  if (current.status !== "failed") return current;
  return {
    ...current,
    status: "partial",
    reason: "retry",
    waiting: false,
  };
}

/** Seek/play hook for a brief evidence section (memo page audio). */
export function requestBriefSectionPlay(
  playable: boolean,
  offsetMs: number | null | undefined,
  onPlay: ((offsetMs: number) => void) | undefined,
): void {
  if (!playable || offsetMs == null || !onPlay) return;
  onPlay(offsetMs);
}
