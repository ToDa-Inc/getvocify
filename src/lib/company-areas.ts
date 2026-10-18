/**
 * Pure helpers of the Playbook windows: the company as six plain texts (what the Head of Sales reads and edits) and back to
 * what Vocify keeps, and the funnel stage of each interaction (decided by its place, never asked).
 */

import type { Competitor, Knowledge, Proof } from "./playbook-knowledge.ts";
import type { DraftType } from "./sales-process.ts";

export type AreaId = "company" | "product" | "offer" | "competition" | "icp" | "cases";
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

/** The six areas as the window shows them. The product is the product-and-offer text live help already reads. */
export function areasFromKnowledge(knowledge: Knowledge | null | undefined, productContext: string | null | undefined): Areas {
  const k = knowledge ?? {};
  return {
    company: (k.notes ?? "").trim(),
    product: (productContext ?? "").trim(),
    offer: (k.pricing ?? "").trim(),
    competition: lines<Competitor>(k.competitors, "name", "how_to_talk"),
    icp: (k.icp ?? "").trim(),
    cases: lines<Proof>(k.proofs, "customer", "change"),
  };
}

/** The six texts written back: lists one item per line ("Nombre — lo que importa"); everything else Vocify knows is kept. */
export function knowledgeFromAreas(knowledge: Knowledge | null | undefined, areas: Areas): { knowledge: Knowledge; productContext: string } {
  const next: Knowledge = { ...(knowledge ?? {}) };
  const set = (key: "notes" | "pricing" | "icp", value: string) => {
    if (value.trim()) next[key] = value.trim();
    else delete next[key];
  };
  set("notes", areas.company);
  set("pricing", areas.offer);
  set("icp", areas.icp);
  next.competitors = parse(areas.competition).map(([name, how]) => (how ? { name, how_to_talk: how } : { name }));
  next.proofs = parse(areas.cases).map(([customer, change]) => (change ? { customer, change } : { customer }));
  if (!next.competitors.length) delete next.competitors;
  if (!next.proofs.length) delete next.proofs;
  return { knowledge: next, productContext: areas.product.trim() };
}

/** The first interaction of the funnel is the first contact; the ones after it move the deal. Calls outside the funnel keep theirs. */
export function withFunnelStages(list: DraftType[]): DraftType[] {
  let seen = 0;
  return list.map((item) => (item.stage === "other" ? item : { ...item, stage: seen++ === 0 ? "first_contact" : "deal" }));
}
