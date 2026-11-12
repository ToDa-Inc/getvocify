/**
 * Pure helpers of the Playbook windows: the company as six plain texts (what the Head of Sales reads and edits) and back to
 * what Vocify keeps, and the funnel stage of each interaction (decided by its place, never asked).
 */

import type { Competitor, Knowledge, Persona, Proof, Trigger } from "./playbook-knowledge.ts";
import type { DraftType } from "./sales-process.ts";

export type AreaId = "company" | "product" | "offer" | "icp" | "bad_fit" | "personas" | "triggers" | "competition" | "cases";
/** The areas written as a list, one item per line («Nombre — su línea»). */
export const LIST_AREAS: readonly AreaId[] = ["personas", "triggers", "competition", "cases"];
export type Areas = Record<AreaId, string>;

const DASH = /\s+[—–-]\s+|:\s+/;

function lines<T>(items: T[] | undefined, title: keyof T, line: keyof T): string {
  return (items ?? [])
    .map((item) => [item[title], item[line]].map((v) => String(v ?? "").trim()).filter(Boolean).join(" — "))
    .filter(Boolean)
    .join("\n");
}

function parse(text: string): [string, string][] {
  return text
    .split("\n")
    .map((row) => row.trim())
    .filter(Boolean)
    .map((row) => {
      const match = DASH.exec(row);
      return match ? [row.slice(0, match.index).trim(), row.slice(match.index + match[0].length).trim()] : [row, ""];
    });
}

/** The areas as the window shows them. The product is the product-and-offer text live help already reads. */
export function areasFromKnowledge(knowledge: Knowledge | null | undefined, productContext: string | null | undefined): Areas {
  const k = knowledge ?? {};
  return {
    company: (k.notes ?? "").trim(),
    product: (productContext ?? "").trim(),
    offer: (k.pricing ?? "").trim(),
    icp: (k.icp ?? "").trim(),
    bad_fit: (k.bad_fit ?? "").trim(),
    personas: lines<Persona>(k.personas, "name", "cares_about"),
    triggers: lines<Trigger>(k.triggers, "signal", "how_to_use"),
    competition: lines<Competitor>(k.competitors, "name", "how_to_talk"),
    cases: lines<Proof>(k.proofs, "customer", "change"),
  };
}

/** The texts written back: lists one item per line ("Nombre — lo que importa"); everything else Vocify knows is kept. With
 * `only`, just that area is written: the others keep what is stored, so an item whose name holds a «:» or a dash is never
 * split again by saving some other area. */
export function knowledgeFromAreas(
  knowledge: Knowledge | null | undefined,
  areas: Areas,
  only?: AreaId,
): { knowledge: Knowledge; productContext: string } {
  const next: Knowledge = { ...(knowledge ?? {}) };
  const writes = (id: AreaId) => !only || only === id;
  const set = (id: AreaId, key: "notes" | "pricing" | "icp" | "bad_fit") => {
    if (!writes(id)) return;
    const value = areas[id].trim();
    if (value) next[key] = value;
    else delete next[key];
  };
  set("company", "notes");
  set("offer", "pricing");
  set("icp", "icp");
  set("bad_fit", "bad_fit");
  if (writes("personas")) next.personas = parse(areas.personas).map(([name, cares]) => (cares ? { name, cares_about: cares } : { name }));
  if (writes("triggers")) next.triggers = parse(areas.triggers).map(([signal, how]) => (how ? { signal, how_to_use: how } : { signal }));
  if (writes("competition")) next.competitors = parse(areas.competition).map(([name, how]) => (how ? { name, how_to_talk: how } : { name }));
  if (writes("cases")) next.proofs = parse(areas.cases).map(([customer, change]) => (change ? { customer, change } : { customer }));
  for (const key of ["personas", "triggers", "competitors", "proofs"] as const) if (next[key] && !next[key]?.length) delete next[key];
  return { knowledge: next, productContext: areas.product.trim() };
}

/** The first interaction of the funnel is the first contact; the ones after it move the deal. Calls outside the funnel keep theirs. */
export function withFunnelStages(list: DraftType[]): DraftType[] {
  let seen = 0;
  return list.map((item) => (item.stage === "other" ? item : { ...item, stage: seen++ === 0 ? "first_contact" : "deal" }));
}

/** Where Vocify writes a document given for one area: a text field or a whole list of the notes. The product is not in the
 * notes (it is the product text, kept as written), so it has none. */
export function areaFillScope(id: AreaId): { texts: string[] } | { list: string } | null {
  switch (id) {
    case "company":
      return { texts: ["notes"] };
    case "offer":
      return { texts: ["pricing"] };
    case "icp":
      return { texts: ["icp"] };
    case "bad_fit":
      return { texts: ["bad_fit"] };
    case "personas":
      return { list: "personas" };
    case "triggers":
      return { list: "triggers" };
    case "competition":
      return { list: "competitors" };
    case "cases":
      return { list: "proofs" };
    default:
      return null;
  }
}

/** A list area as items to read: each line split into its name and its line, as it is saved. */
export function areaItems(text: string): { title: string; line: string }[] {
  return parse(text).map(([title, line]) => ({ title, line }));
}
