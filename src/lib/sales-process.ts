/** Pure helpers of the sales-process editor: the list the Head of Sales edits, before it is sent. No React, no I/O. */

/** `other` is a call outside the sales funnel: not scored in coaching, no objective or description needed. */
export type Stage = "first_contact" | "deal" | "other";
/** One row of the list being edited. `key` is set for a type the company already has. */
export type DraftType = { key?: string; label: string; stage: Stage; goal?: string; recognize?: string };
export type SavedType = { key: string; label: string; stage: Stage; step_count?: number; goal?: string | null; recognize?: string | null };

/** The list with the type at `index` moved by `delta` places; the same list when it cannot move. */
export function moveItem<T>(list: T[], index: number, delta: -1 | 1): T[] {
  const target = index + delta;
  if (index < 0 || index >= list.length || target < 0 || target >= list.length) return list;
  const next = [...list];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

/** A process needs at least one type, each with a name and no two with the same one; every interaction of the funnel also needs its objective. */
export function canSave(list: DraftType[]): boolean {
  const names = list.map((item) => item.label.trim().toLowerCase());
  const complete = list.every((item) => item.stage === "other" || Boolean(item.goal?.trim()));
  return names.length > 0 && names.every(Boolean) && new Set(names).size === names.length && complete;
}

export type RowProblem = "empty_name" | "duplicate_name" | "goal_required";

/** What stops one row of a window from being saved, or null. Names are compared across the whole process (`all`): a call
 * outside the funnel cannot take the name of an interaction of it. */
export function rowProblem(row: DraftType, all: DraftType[]): RowProblem | null {
  const name = row.label.trim().toLowerCase();
  if (!name) return "empty_name";
  if (all.filter((item) => item.label.trim().toLowerCase() === name).length > 1) return "duplicate_name";
  if (row.stage !== "other" && !row.goal?.trim()) return "goal_required";
  return null;
}

/** A window saves only its own part, so only that part is checked: the other part travels as it is saved, even when it is
 * incomplete (a funnel saved before a goal was asked for must not block saving the calls outside it). */
export function scopeProblem(part: DraftType[], all: DraftType[]): RowProblem | null {
  if (!part.length) return "empty_name";
  return part.map((row) => rowProblem(row, all)).find(Boolean) ?? null;
}

export type Scope = "funnel" | "other";
const inScope = (item: { stage: Stage }, scope: Scope) => (scope === "other") === (item.stage === "other");

/** The whole list after editing one scope: the funnel comes first and the other calls after, each part in its own order. */
export function mergeScope(all: DraftType[], scope: Scope, edited: DraftType[]): DraftType[] {
  const rest = all.filter((item) => !inScope(item, scope));
  return scope === "funnel" ? [...edited, ...rest] : [...rest, ...edited];
}

/** The part of the list a window edits. */
export function scoped(all: DraftType[], scope: Scope): DraftType[] {
  return all.filter((item) => inScope(item, scope));
}

/** The body of PUT /sales-process: trimmed names, keys of the existing types, no empty descriptions. */
export function toRequest(list: DraftType[]) {
  return {
    types: list.map((item) => ({
      ...(item.key ? { key: item.key } : {}),
      label: item.label.trim(),
      stage: item.stage,
      ...(item.goal?.trim() ? { goal: item.goal.trim() } : {}),
      ...(item.recognize?.trim() ? { recognize: item.recognize.trim() } : {}),
    })),
  };
}

/** The names of the types that the new list drops and that already have steps written, to ask before archiving them. */
export function removedWithContent(original: SavedType[], draft: DraftType[]): string[] {
  const kept = new Set(draft.map((item) => item.key).filter(Boolean));
  return original.filter((item) => !kept.has(item.key) && (item.step_count ?? 0) > 0).map((item) => item.label);
}

/** A starting list for a company with no process: the first two aim at a meeting, the rest at the deal. Only a suggestion. */
export function suggestedProcess(names: string[]): DraftType[] {
  return names.map((label, index) => ({ label, stage: index < 2 ? "first_contact" : "deal" }));
}

/** "Todas" or the names of what the person runs, short enough for a chip: two names, else how many. */
export function typesSummary(value: string[] | null, types: { key: string; label: string }[], all: string, manyTemplate: string): string {
  const chosen = types.filter((item) => value?.includes(item.key));
  if (!value || !chosen.length || chosen.length === types.length) return all;
  return chosen.length <= 2 ? chosen.map((item) => item.label).join(", ") : manyTemplate.replace("{count}", String(chosen.length));
}

/** A saved list as a draft to edit. */
export function draftOf(types: SavedType[]): DraftType[] {
  return types.map((item) => ({ key: item.key, label: item.label, stage: item.stage, goal: item.goal ?? undefined, recognize: item.recognize ?? undefined }));
}

/** The body of PUT /sales-process from one window: its own part as edited, the other part exactly as it is saved (never from a
 * draft that may not hold it), and the scope so the server keeps that other part even if the list came without it. */
export function requestFor(saved: SavedType[], scope: Scope, edited: DraftType[]) {
  return { scope, types: toRequest(mergeScope(draftOf(saved), scope, edited)).types };
}
