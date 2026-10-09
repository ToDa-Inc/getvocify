/**
 * "Vuestra empresa" (plan §15, layer 2): what Vocify knows about the company, given once and
 * used as context by the copilot, briefs, follow-ups and Ask. Not scored. Pure helpers: which
 * sections have content, the one-line summary on the row, and cleaning before a save.
 */

// Each list item is its name and ONE line: the one the copilot and briefs use.
export type Persona = { name: string; cares_about?: string };
export type Trigger = { signal: string; how_to_use?: string };
export type Proof = { customer: string; change?: string };
export type Competitor = { name: string; how_to_talk?: string };

export type Knowledge = {
  icp?: string;
  bad_fit?: string;
  value_short?: string;
  value_long?: string;
  pricing?: string;
  notes?: string;
  personas?: Persona[];
  triggers?: Trigger[];
  differentiators?: string[];
  proofs?: Proof[];
  competitors?: Competitor[];
};

export type KnowledgeDoc = { knowledge: Knowledge; updated_at: string | null; sections: string[] };

/** The sections on screen, in reading order. Each lists the knowledge keys it owns. */
export const KNOWLEDGE_SECTIONS = {
  audience: ["icp", "bad_fit", "personas"],
  value: ["value_short", "value_long", "differentiators"],
  proofs: ["proofs"],
  competitors: ["competitors"],
  triggers: ["triggers"],
  pricing: ["pricing"],
  notes: ["notes"],
} as const satisfies Record<string, readonly (keyof Knowledge)[]>;

export type KnowledgeSection = keyof typeof KNOWLEDGE_SECTIONS;
export const SECTION_ORDER = Object.keys(KNOWLEDGE_SECTIONS) as KnowledgeSection[];

/**
 * "Vuestra empresa" in five tabs instead of seven stacked sections: who the customer is (and
 * what shows they are ready), the offer (value story and price), customer stories,
 * competitors and anything else. Each tab lists the sections it shows, in order.
 */
export const COMPANY_TABS = {
  customer: ["audience", "triggers"],
  value: ["value", "pricing"],
  proofs: ["proofs"],
  competitors: ["competitors"],
  notes: ["notes"],
} as const satisfies Record<string, readonly KnowledgeSection[]>;

export type CompanyTab = keyof typeof COMPANY_TABS;
export const COMPANY_TAB_ORDER = Object.keys(COMPANY_TABS) as CompanyTab[];

export function tabFilled(knowledge: Knowledge | null | undefined, tab: CompanyTab): boolean {
  return COMPANY_TABS[tab].some((section) => sectionFilled(knowledge, section));
}

/** The number on a list tab ("Casos 3"): named items only. Null for the text tabs. */
export function tabCount(knowledge: Knowledge | null | undefined, tab: CompanyTab): number | null {
  if (tab === "proofs") return count(knowledge?.proofs, "customer");
  if (tab === "competitors") return count(knowledge?.competitors, "name");
  return null;
}

/**
 * Competitors the team's calls mention that "Vuestra empresa" doesn't list yet, most mentioned
 * first. `known` holds the listed names, lower-cased.
 */
export function suggestedCompetitors(
  mentions: readonly { name: string; count: number }[] | null | undefined,
  known: ReadonlySet<string>,
): { name: string; count: number }[] {
  return (mentions ?? [])
    .filter((mention) => mention.name?.trim() && !known.has(mention.name.trim().toLowerCase()))
    .sort((a, b) => b.count - a.count);
}

/** The field a list item is named by. */
export const ITEM_TITLE = { personas: "name", triggers: "signal", proofs: "customer", competitors: "name" } as const;
export type KnowledgeList = keyof typeof ITEM_TITLE;
/** The one line under an item's name: what a persona cares about, what to do on a signal, what a customer achieved, how to win. */
export const ITEM_LINE = { personas: "cares_about", triggers: "how_to_use", proofs: "change", competitors: "how_to_talk" } as const;

function filled(value: unknown): boolean {
  if (typeof value === "string") return value.trim().length > 0;
  if (Array.isArray(value)) return value.some((item) => (typeof item === "string" ? item.trim() : item && Object.values(item).some(filled)));
  return false;
}

export function sectionFilled(knowledge: Knowledge | null | undefined, section: KnowledgeSection): boolean {
  return KNOWLEDGE_SECTIONS[section].some((key) => filled(knowledge?.[key]));
}

export function isEmptyKnowledge(knowledge: Knowledge | null | undefined): boolean {
  return SECTION_ORDER.every((section) => !sectionFilled(knowledge, section));
}

const count = (list: unknown[] | undefined, title: string) =>
  (list ?? []).filter((item) => item && typeof item === "object" && String((item as Record<string, unknown>)[title] ?? "").trim()).length;

/** "Relato de valor · 2 casos · 3 competidores" for the row; null when there is nothing yet. */
export function knowledgeSummary(
  knowledge: Knowledge | null | undefined,
  copy: {
    audience: string;
    value: string;
    proofs: string;
    proofOne: string;
    competitors: string;
    competitorOne: string;
    triggers: string;
    pricing: string;
  },
): string | null {
  if (!knowledge) return null;
  const parts: string[] = [];
  if (sectionFilled(knowledge, "value")) parts.push(copy.value);
  if (sectionFilled(knowledge, "audience")) parts.push(copy.audience);
  const proofs = count(knowledge.proofs, "customer");
  if (proofs) parts.push(proofs === 1 ? copy.proofOne : copy.proofs.replace("{count}", String(proofs)));
  const competitors = count(knowledge.competitors, "name");
  if (competitors) parts.push(competitors === 1 ? copy.competitorOne : copy.competitors.replace("{count}", String(competitors)));
  if (sectionFilled(knowledge, "triggers")) parts.push(copy.triggers);
  if (sectionFilled(knowledge, "pricing")) parts.push(copy.pricing);
  return parts.length ? parts.join(" · ") : null;
}

const tidy = (value: unknown) => (typeof value === "string" ? value.split(/\s+/).filter(Boolean).join(" ") : "");
/** Long texts keep their line breaks (a 3-minute value story has paragraphs). */
const trimBlock = (value: unknown) => (typeof value === "string" ? value.trim() : "");

/** What is sent on save: trimmed, list items without a name dropped, empty keys left out. */
export function cleanKnowledge(knowledge: Knowledge): Knowledge {
  const out: Knowledge = {};
  for (const key of ["icp", "bad_fit", "value_short", "value_long", "pricing", "notes"] as const) {
    const value = trimBlock(knowledge[key]);
    if (value) out[key] = value;
  }
  const differentiators = (knowledge.differentiators ?? []).map(tidy).filter(Boolean);
  if (differentiators.length) out.differentiators = differentiators;
  for (const list of Object.keys(ITEM_TITLE) as KnowledgeList[]) {
    const title = ITEM_TITLE[list];
    const line = ITEM_LINE[list];
    // Only the name and its line are kept: older extra fields are dropped on this save.
    const items = ((knowledge[list] ?? []) as Record<string, unknown>[])
      .map((item) => {
        const clean: Record<string, string> = {};
        const name = tidy(item[title]);
        const text = trimBlock(item[line]);
        if (name) clean[title] = name;
        if (text) clean[line] = text;
        return clean;
      })
      .filter((item) => item[title]);
    if (items.length) (out as Record<string, unknown>)[list] = items;
  }
  return out;
}

/** A blank item for "+ Añadir" in a list section. */
export function blankItem(list: KnowledgeList): Record<string, string> {
  return { [ITEM_TITLE[list]]: "" };
}
