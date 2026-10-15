/**
 * One objection in several playbook types. Each type keeps its own copy (its own answer);
 * these helpers only say where an objection also appears and add, remove or equalise it.
 * Two objections are "the same" when `objectionKey` matches. Nothing is mutated.
 */

import {
  criteriaFromSnapshot,
  draftError,
  draftPayload,
  objectionKey,
  stepsFromSnapshot,
  type EditorObjection,
  type EditorSnapshot,
} from "./playbook-editor.ts";

export type ObjectionLibrary = Record<string, EditorObjection[]>;

/** The types whose list holds this objection, in library order. */
export function typesWithObjection(library: ObjectionLibrary, key: string): string[] {
  return Object.keys(library).filter((type) => library[type].some((item) => objectionKey(item) === key));
}

/**
 * Puts the objection in `type` (a copy taken from `sourceType`, unless it is already there) or
 * takes it out. `sourceType` itself is never changed.
 */
export function setInType(library: ObjectionLibrary, key: string, type: string, on: boolean, sourceType: string): ObjectionLibrary {
  if (type === sourceType) return library;
  const list = library[type] ?? [];
  const present = list.some((item) => objectionKey(item) === key);
  if (!on) return present ? { ...library, [type]: list.filter((item) => objectionKey(item) !== key) } : library;
  if (present) return library;
  const source = (library[sourceType] ?? []).find((item) => objectionKey(item) === key);
  return source ? { ...library, [type]: [...list, { ...source }] } : library;
}

/** The answer of `fromType` becomes the answer of every target that has the objection. */
export function copyAnswerTo(library: ObjectionLibrary, key: string, fromType: string, toTypes: string[]): ObjectionLibrary {
  const source = (library[fromType] ?? []).find((item) => objectionKey(item) === key);
  if (!source) return library;
  const next: ObjectionLibrary = { ...library };
  for (const type of toTypes) {
    if (type === fromType || !next[type]) continue;
    next[type] = next[type].map((item) => (objectionKey(item) === key ? { ...item, guidance: source.guidance } : item));
  }
  return next;
}

export type ObjectionAction = { kind: "set"; on: boolean } | { kind: "copy" };

/**
 * The objections `targetType` ends up with after `action` on the objection `key`, taken from
 * `sourceType` (the library holds both), or null when nothing changes there, so no draft is written.
 */
export function objectionsAfter(
  library: ObjectionLibrary,
  key: string,
  sourceType: string,
  targetType: string,
  action: ObjectionAction,
): EditorObjection[] | null {
  const next = action.kind === "set" ? setInType(library, key, targetType, action.on, sourceType) : copyAnswerTo(library, key, sourceType, [targetType]);
  const before = library[targetType] ?? [];
  const after = next[targetType] ?? [];
  return JSON.stringify(after) === JSON.stringify(before) ? null : after;
}

/** The types that hold a playbook: not missing, not still being imported; qualification only once published. */
export function typesWithPlaybook(motions: Record<string, string>): string[] {
  return Object.keys(motions).filter(
    (key) => motions[key] !== "missing" && motions[key] !== "importing" && (key !== "qualification" || motions[key] === "published"),
  );
}

/** "A", "A y B", "A, B y C". */
export function joinNames(names: string[], and: string): string {
  if (names.length < 2) return names.join("");
  return `${names.slice(0, -1).join(", ")} ${and} ${names[names.length - 1]}`;
}

/**
 * The PUT /draft body for a type's editor snapshot with `objections` instead of its own: steps and
 * qualification as the snapshot has them, conflict check on the snapshot's own revision. Null when
 * the result would not pass validation.
 */
export function draftBodyWithObjections(
  doc: EditorSnapshot & { updated_at?: string | null; source_doc?: { id?: string | null } | null },
  objections: EditorObjection[],
) {
  const steps = stepsFromSnapshot(doc);
  const qualification = criteriaFromSnapshot(doc);
  if (draftError(steps, objections, qualification)) return null;
  return {
    ...draftPayload(steps, objections, qualification),
    base_updated_at: doc.updated_at ?? null,
    source_id: doc.source_doc?.id ?? null,
  };
}
