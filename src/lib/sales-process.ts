/** Pure helpers of the sales-process editor: the list the Head of Sales edits, before it is sent. No React, no I/O. */

export type Stage = "first_contact" | "deal";
/** One row of the list being edited. `key` is set for a type the company already has. */
export type DraftType = { key?: string; label: string; stage: Stage; recognize?: string };
export type SavedType = { key: string; label: string; stage: Stage; step_count?: number; recognize?: string | null };

/** The list with the type at `index` moved by `delta` places; the same list when it cannot move. */
export function moveItem<T>(list: T[], index: number, delta: -1 | 1): T[] {
  const target = index + delta;
  if (index < 0 || index >= list.length || target < 0 || target >= list.length) return list;
  const next = [...list];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

/** A process needs at least one type, each with a name and no two with the same one. */
export function canSave(list: DraftType[]): boolean {
  const names = list.map((item) => item.label.trim().toLowerCase());
  return names.length > 0 && names.every(Boolean) && new Set(names).size === names.length;
}

/** The body of PUT /sales-process: trimmed names, keys of the existing types, no empty descriptions. */
export function toRequest(list: DraftType[]) {
  return {
    types: list.map((item) => ({
      ...(item.key ? { key: item.key } : {}),
      label: item.label.trim(),
      stage: item.stage,
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
