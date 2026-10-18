/** Pure helpers of the Playbook home (sales funnel, company, other calls): shapes and counts, no React, no I/O. */

import { tabFilled, type CompanyTab, type Knowledge } from "./playbook-knowledge.ts";

const NARROWEST = 0.46;

/** The width of each step of the funnel as a share of the widest: 1 for the first, narrowing evenly to the minimum for the last. */
export function funnelWidths(count: number, min = NARROWEST): number[] {
  if (count <= 0) return [];
  if (count === 1) return [1];
  return Array.from({ length: count }, (_, index) => Math.max(min, 1 - (index / (count - 1)) * (1 - min)));
}

/** The interactions of the sales funnel and, apart, the calls outside it, each list in the order it came. */
export function splitFunnel<T extends { stage: string }>(types: T[]): { funnel: T[]; other: T[] } {
  return { funnel: types.filter((type) => type.stage !== "other"), other: types.filter((type) => type.stage === "other") };
}

/** How many interactions already have something written (any state but empty). */
export function homeProgress(types: { state: string }[]): { total: number; written: number } {
  return { total: types.length, written: types.filter((type) => type.state !== "empty").length };
}

export type CompanyAreaId = "company" | "product" | "offer" | "competition" | "icp" | "cases";
/** Where in the company window an area opens: one of its tabs, or the product and offer text that sits above them. */
export type CompanyOpens = CompanyTab | "offer";

/** What the company block lists, in order. Each area opens the place in the company window where it is written. */
export const COMPANY_AREAS: readonly { id: CompanyAreaId; opens: CompanyOpens }[] = [
  { id: "company", opens: "notes" },
  { id: "product", opens: "value" },
  { id: "offer", opens: "offer" },
  { id: "competition", opens: "competitors" },
  { id: "icp", opens: "customer" },
  { id: "cases", opens: "proofs" },
];

/** Whether each area of the company has something written: its tab of the company knowledge, and the offer text for "Oferta". */
export function companyAreaStates(knowledge: Knowledge | null | undefined, offerText: string | null | undefined): { id: CompanyAreaId; filled: boolean }[] {
  return COMPANY_AREAS.map((area) => ({
    id: area.id,
    filled: area.opens === "offer" ? Boolean(offerText?.trim()) : tabFilled(knowledge, area.opens),
  }));
}
