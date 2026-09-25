/** Six brief states. A failed retry keeps the sections that already exist. */

import type { ProductTranslations } from "./product-catalog";

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

export type BriefProductCopy = Pick<
  ProductTranslations,
  | "hourLocale"
  | "briefNotReady"
  | "briefReadFailed"
  | "briefTitlePending"
  | "briefTitlePartial"
  | "briefTitleReady"
  | "briefTitleSkipped"
  | "briefTitleUnavailable"
  | "briefTitleFailed"
  | "briefHighlightAt"
  | "briefAudioUnavailable"
>;

export function highlightScheduleLine(
  highlight: BriefHighlight | undefined,
  copy: Pick<ProductTranslations, "hourLocale" | "briefHighlightAt">,
): string | null {
  if (!highlight || highlight.highlight_mode === "immediate") return null;
  const when = new Date(highlight.highlight_at);
  if (Number.isNaN(when.getTime())) return null;
  const tz = highlight.timezone || "Europe/Madrid";
  const hour = new Intl.DateTimeFormat(copy.hourLocale, {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: tz,
  }).format(when);
  return copy.briefHighlightAt.replace("{hour}", hour);
}

export function postBriefFetchTitle(
  phase: "loading" | "error",
  copy: Pick<ProductTranslations, "briefNotReady" | "briefReadFailed">,
): string {
  if (phase === "error") return copy.briefReadFailed;
  return copy.briefNotReady;
}

const TITLE_KEYS: Record<BriefView["status"], keyof BriefProductCopy> = {
  pending: "briefTitlePending",
  partial: "briefTitlePartial",
  ready: "briefTitleReady",
  skipped: "briefTitleSkipped",
  unavailable: "briefTitleUnavailable",
  failed: "briefTitleFailed",
};

export function briefSurface(brief: BriefView, copy: BriefProductCopy): BriefSurface {
  const sections = brief.sections.map((section) => ({ ...section }));
  const quoteWithoutAudio = sections.some((section) => section.quote && !brief.audio_available);
  return {
    title: brief.reason === "not_started" ? copy.briefNotReady : copy[TITLE_KEYS[brief.status]],
    revision: brief.input_revision,
    waiting: brief.status === "pending" && brief.waiting,
    strength: brief.strength,
    improvement: brief.improvement,
    sections,
    playable: brief.audio_available && sections.some((section) => section.offset_ms != null),
    audioNote: quoteWithoutAudio ? copy.briefAudioUnavailable : null,
    highlightNote: highlightScheduleLine(brief.highlight, copy),
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
