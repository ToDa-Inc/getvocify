/** Review of one interaction. A missing analysis is not "there were no objections". */

import type { ProductTranslations } from "./product-catalog";

export type ReviewPattern = {
  pattern_id: string;
  category: string;
  kind: "objection" | "obstacle" | "unknown";
  resolution: "resolved" | "open" | "unknown";
  response: string | null;
  prospect_quotes: string[];
};

type PatternProductLabels = Pick<
  ProductTranslations,
  | "objections"
  | "kindObjection"
  | "kindObstacle"
  | "kindUnknown"
  | "resolutionResolved"
  | "resolutionOpen"
  | "resolutionUnknown"
>;

/** Display label for a stored category key; unknown keys pass through unchanged. */
export function patternCategoryLabel(category: string, labels: PatternProductLabels): string {
  const key = category.trim().toLowerCase();
  return labels.objections[key as keyof ProductTranslations["objections"]] ?? category;
}

export function patternKindLabel(kind: ReviewPattern["kind"], labels: PatternProductLabels): string {
  if (kind === "objection") return labels.kindObjection;
  if (kind === "obstacle") return labels.kindObstacle;
  return labels.kindUnknown;
}

export function patternResolutionLabel(
  resolution: ReviewPattern["resolution"],
  labels: PatternProductLabels,
): string {
  if (resolution === "resolved") return labels.resolutionResolved;
  if (resolution === "open") return labels.resolutionOpen;
  return labels.resolutionUnknown;
}

export type ReviewNote = {
  annotation_id: string;
  text: string;
  offset_ms: number;
  author_id: string;
  turn_id?: string | null;
};

export type ObjectionReviewCopy = Pick<
  ProductTranslations,
  "objectionsNoneDetected" | "objectionsPartialAnalysis" | "noteLabel"
>;

export type NoteFieldCopy = Pick<ProductTranslations, "noteSaving" | "noteSaved" | "noteSaveFailed">;

export type ObjectionReview = {
  title: string | null;
  claimNone: boolean;
  patterns: ReviewPattern[];
  notes: Array<ReviewNote & { playable: boolean; label: string }>;
};

export function objectionReview(input: {
  coverage: "complete" | "partial" | "unavailable";
  patterns: ReviewPattern[];
  notes: ReviewNote[];
  canPlaySpan: boolean;
  copy: ObjectionReviewCopy;
}): ObjectionReview {
  const notes = input.notes.map((note) => ({
    ...note,
    label: input.copy.noteLabel,
    playable: Boolean(input.canPlaySpan && note.turn_id),
  }));
  const objections = input.patterns.filter((pattern) => pattern.kind === "objection");
  if (input.coverage === "complete" && objections.length === 0 && notes.length === 0 && input.patterns.length === 0) {
    return { title: input.copy.objectionsNoneDetected, claimNone: true, patterns: [], notes: [] };
  }
  if (input.coverage !== "complete") {
    return {
      title: input.copy.objectionsPartialAnalysis,
      claimNone: false,
      patterns: input.patterns,
      notes,
    };
  }
  return { title: null, claimNone: false, patterns: input.patterns, notes };
}

export function mergeNotes(stored: ReviewNote[], added: ReviewNote[]): ReviewNote[] {
  const ids = new Set(stored.map((note) => note.annotation_id));
  return [...stored, ...added.filter((note) => !ids.has(note.annotation_id))];
}

export function noteFieldLabel(status: "idle" | "syncing" | "saved" | "error", copy: NoteFieldCopy): string | null {
  if (status === "syncing") return copy.noteSaving;
  if (status === "saved") return copy.noteSaved;
  if (status === "error") return copy.noteSaveFailed;
  return null;
}
