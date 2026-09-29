/**
 * Playbooks v2 (docs/superpowers/plans/2026-09-29-playbooks-v2.md): the playbook as one
 * document. Pure helpers for the list, the start box, the document and the rule line, so
 * the components stay thin and every decision here is unit-tested.
 */

import {
  MAX_STEPS,
  OBJECTION_CATEGORIES,
  draftError,
  stepError,
  type EditorObjection,
  type EditorStep,
  type ObjectionCategory,
  type StepError,
} from "./playbook-editor.ts";
import type { MotionStatus } from "./playbook-setup.ts";

/** Above this many steps coaching loses focus; the hard limit stays MAX_STEPS. */
export const FOCUS_STEPS = 6;
/** Milliseconds of quiet before the draft is saved. */
export const AUTOSAVE_MS = 800;

export type SourceKind = "text" | "pdf" | "audio";
export type PlaybookSource = { id: string; kind: string; name?: string | null };
export type SalesRoleKey = "sdr" | "ae" | "any";
export type Channel = "call" | "meeting" | "visit";
export type ContactRule = "new" | "contacted" | "inbound" | "any";

export type AppliesTo = {
  role: SalesRoleKey;
  channels: Channel[];
  contact: ContactRule;
  deal_stages: string[];
};

export type PlaybookDetail = {
  label: string | null;
  role: SalesRoleKey | null;
  applies_to: AppliesTo | null;
  goal: string | null;
  catalog: boolean;
  /** Of what a manager's editor shows: the pending draft, else the live version. */
  step_count?: number;
  answer_count?: number;
  /** Saved changes the team doesn't have yet. */
  has_draft?: boolean;
};

export type CatalogType = {
  key: string;
  role: "sdr" | "ae";
  goal: string | null;
  applies_to: AppliesTo;
  label: { es: string; en: string };
  template: { es: TemplateStep[]; en: TemplateStep[] };
};

export type TemplateStep = { step_id: string; label: string; criterion: string };

export type StructureResult = {
  sales_motion_key: string;
  steps: { step_id?: string | null; label: string; criterion: string; example?: string }[];
  objections: { category: string; guidance: string }[];
  reason: null | "no_process" | "too_short" | "grouped";
  fallback: boolean;
  source: PlaybookSource | null;
};

export type StepInsight = { step_id: string; met: number; missed: number; rate: number | null };
export type ObjectionInsight = {
  category: string;
  count: number;
  share: number;
  answered: boolean;
  best_example: string | null;
};
export type PlaybookInsights = {
  period: string;
  calls: number;
  steps: StepInsight[];
  objections: ObjectionInsight[];
};

/** What a file dropped or picked in the start box is, or null when Vocify can't read it. */
export function sourceKindForFile(file: { name: string; type: string }): SourceKind | null {
  const type = (file.type || "").toLowerCase();
  const name = (file.name || "").toLowerCase();
  if (type === "application/pdf" || name.endsWith(".pdf")) return "pdf";
  if (type.startsWith("audio/") || /\.(mp3|m4a|wav|webm|ogg|aac|flac|mp4)$/.test(name)) return "audio";
  if (type.startsWith("text/") || /\.(txt|md)$/.test(name)) return "text";
  return null;
}

/** Dictation adds to what is already written, it never replaces it. */
export function appendDictation(current: string, spoken: string): string {
  const text = spoken.trim();
  if (!text) return current;
  const base = current.trimEnd();
  return base ? `${base}\n\n${text}` : text;
}

/** A step shows its problem only once the person has left it. A step without a name is never
 * an error on its own (it is dropped on save); only a blocked publish (`forced`) flags it. */
export function validationToShow(step: EditorStep, touched: boolean, forced = false): StepError | null {
  if (!touched && !forced) return null;
  const error = stepError(step);
  if (error === "empty_label" && !forced) return null;
  return error;
}

export type PublishBlocker = { code: string; stepIndex: number | null };

/** Why Publish is disabled, pointing at the step to fix. */
export function publishBlocker(steps: EditorStep[], objections: EditorObjection[]): PublishBlocker | null {
  const code = draftError(steps, objections);
  if (!code) return null;
  const index = steps.findIndex((step) => stepError(step) !== null);
  return { code, stepIndex: index >= 0 ? index : null };
}

export type ObjectionRow = {
  category: ObjectionCategory;
  guidance: string;
  count: number;
  share: number;
  bestExample: string | null;
};

/** The objections the document shows: every answered one, every one the team hears without
 * an answer, and any the person added by hand. Most frequent first, then catalog order. */
export function visibleObjections(
  answers: EditorObjection[],
  insights: ObjectionInsight[] | null | undefined,
  added: readonly string[] = [],
): ObjectionRow[] {
  const byCategory = new Map((insights ?? []).map((item) => [item.category, item]));
  const guidance = new Map(answers.map((item) => [item.category, item.guidance]));
  const rows: ObjectionRow[] = [];
  for (const category of OBJECTION_CATEGORIES) {
    const text = guidance.get(category) ?? "";
    const data = byCategory.get(category);
    const heard = (data?.count ?? 0) > 0;
    if (!text.trim() && !heard && !added.includes(category) && !guidance.has(category)) continue;
    rows.push({
      category,
      guidance: text,
      count: data?.count ?? 0,
      share: data?.share ?? 0,
      bestExample: data?.best_example ?? null,
    });
  }
  return rows.sort(
    (a, b) => b.count - a.count || OBJECTION_CATEGORIES.indexOf(a.category) - OBJECTION_CATEGORIES.indexOf(b.category),
  );
}

/** Categories not on screen yet, for "+ Objection". */
export function hiddenObjectionCategories(rows: ObjectionRow[]): ObjectionCategory[] {
  const shown = new Set(rows.map((row) => row.category));
  return OBJECTION_CATEGORIES.filter((category) => !shown.has(category));
}

/** "62 %" for a step, or null while there aren't enough calls to say. */
export function stepRate(insights: PlaybookInsights | null | undefined, stepId: string | null | undefined): number | null {
  if (!insights || !stepId) return null;
  const rate = insights.steps.find((step) => step.step_id === stepId)?.rate;
  return typeof rate === "number" ? Math.round(rate * 100) : null;
}

/** The step the team misses most, highlighted in the document. Only among steps with a rate. */
export function weakestStep(insights: PlaybookInsights | null | undefined): string | null {
  const rated = (insights?.steps ?? []).filter((step) => typeof step.rate === "number");
  if (rated.length < 2) return null;
  return rated.reduce((low, step) => ((step.rate as number) < (low.rate as number) ? step : low)).step_id;
}

export function percent(share: number): string {
  return `${Math.round(Math.max(0, Math.min(1, share)) * 100)} %`;
}

export type SaveState = "idle" | "saving" | "saved" | "error" | "stale";

/** Structure result -> editor steps and answers. Keys are client-side only. */
export function editorFromStructure(
  result: Pick<StructureResult, "steps" | "objections">,
  newKey: () => string,
): { steps: EditorStep[]; objections: EditorObjection[] } {
  const steps = (result.steps ?? []).slice(0, MAX_STEPS).map((step) => ({
    key: newKey(),
    step_id: step.step_id ?? null,
    label: step.label ?? "",
    criterion: step.criterion ?? "",
    example: step.example ?? "",
  }));
  const objections = (result.objections ?? []).filter((item): item is EditorObjection =>
    (OBJECTION_CATEGORIES as readonly string[]).includes(item.category) && Boolean(item.guidance?.trim()),
  );
  return { steps, objections };
}

/** A step whose "counts as done" just repeats its name gives C04 nothing to judge. */
export function needsCriterion(step: EditorStep): boolean {
  const criterion = step.criterion.trim().toLowerCase();
  return !criterion || criterion === step.label.trim().toLowerCase();
}

export type PlaybookRow = {
  key: string;
  status: MotionStatus;
  role: SalesRoleKey | null;
  /** A type the company created that no rule sends a call to. */
  unrouted: boolean;
};

const CATALOG_ORDER = ["discovery", "inbound", "ae_discovery", "closing", "negotiation", "qualification"];

/**
 * The rows of "Vuestro proceso". Every motion the API returned (already filtered by role for a
 * rep), qualification only once published (D4), catalog types in catalog order and the
 * company's own types after them. A custom type is "unrouted" while routing is off, or when
 * it has no rule: coaching never applies it, and the row says so.
 */
export function playbookRows(
  motions: Record<string, MotionStatus>,
  details: Record<string, PlaybookDetail> | null | undefined,
  routingEnabled: boolean,
): PlaybookRow[] {
  const keys = Object.keys(motions).filter((key) => key !== "qualification" || motions[key] === "published");
  const rank = (key: string) => {
    const index = CATALOG_ORDER.indexOf(key);
    return index >= 0 ? index : CATALOG_ORDER.length;
  };
  return keys
    .sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))
    .map((key) => {
      const detail = details?.[key];
      const builtIn = key === "discovery" || key === "closing" || key === "qualification";
      const catalog = builtIn || Boolean(detail?.catalog);
      const unrouted = !builtIn && (!routingEnabled || (!catalog && !detail?.applies_to));
      return { key, status: motions[key] ?? "missing", role: detail?.role ?? defaultRole(key), unrouted };
    });
}

function defaultRole(key: string): SalesRoleKey | null {
  if (key === "discovery" || key === "inbound") return "sdr";
  if (key === "closing" || key === "ae_discovery" || key === "negotiation") return "ae";
  return null;
}

export type RowState = "empty" | "pending" | "live";

/** What a row says at a glance: nothing yet, saved changes the team doesn't have, or active. */
export function rowState(status: MotionStatus, detail: PlaybookDetail | null | undefined): RowState {
  if (detail?.has_draft || status === "draft" || status === "importing") return "pending";
  if (status === "published") return "live";
  return (detail?.step_count ?? 0) > 0 ? "pending" : "empty";
}

/** The call types "Activar para el equipo" publishes. */
export function pendingKeys(
  motions: Record<string, MotionStatus>,
  details: Record<string, PlaybookDetail> | null | undefined,
): string[] {
  return Object.keys(motions).filter((key) => rowState(motions[key], details?.[key]) === "pending");
}

/** Nothing created anywhere yet: the whole section is the intake box. */
export function nothingYet(
  motions: Record<string, MotionStatus>,
  details: Record<string, PlaybookDetail> | null | undefined,
): boolean {
  return Object.keys(motions).every((key) => rowState(motions[key], details?.[key]) === "empty");
}

/** "5 comprobaciones · 3 respuestas", singular-aware; null when there is nothing to count. */
export function countLine(
  detail: PlaybookDetail | null | undefined,
  copy: { checks: string; checkOne: string; answers: string; answerOne: string },
): string | null {
  const steps = detail?.step_count ?? 0;
  const answers = detail?.answer_count ?? 0;
  if (!steps) return null;
  const parts = [steps === 1 ? copy.checkOne : copy.checks.replace("{count}", String(steps))];
  if (answers) parts.push(answers === 1 ? copy.answerOne : copy.answers.replace("{count}", String(answers)));
  return parts.join(" · ");
}

/** The "applies to" line only earns its space when a rule decides something: a company's own
 * type, or two playbooks for the same role that calls must be told apart by. */
export function ruleNeeded(rows: PlaybookRow[], key: string, routingEnabled: boolean): boolean {
  if (!routingEnabled) return false;
  const row = rows.find((item) => item.key === key);
  if (!row) return false;
  const custom = !["discovery", "closing", "qualification", "inbound", "ae_discovery", "negotiation"].includes(key);
  if (custom) return true;
  return rows.filter((item) => item.role && item.role === row.role && item.status !== "missing").length > 1;
}

/** The analytics under the playbook show once there is something to read, and stay while the
 * person is filtering (an empty filter result must not hide the filters themselves). */
export function showProcessAnalytics(
  data: { process_health?: { scored: number }[]; objection_categories?: unknown[] } | null | undefined,
  filtered: boolean,
): boolean {
  if (filtered) return true;
  if (!data) return false;
  return (data.process_health ?? []).some((flow) => flow.scored > 0) || (data.objection_categories ?? []).length > 0;
}

export type RuleCopy = {
  roles: Record<SalesRoleKey, string>;
  channels: Record<Channel, string>;
  contacts: Record<ContactRule, string>;
  stages: string;
  join: string;
};

/** "Llamadas de SDR a contactos nuevos" style summary of a rule, one line. */
export function ruleSummary(rule: AppliesTo | null | undefined, copy: RuleCopy): string | null {
  if (!rule) return null;
  const channels = rule.channels.length ? rule.channels.map((channel) => copy.channels[channel]).join(copy.join) : copy.channels.call;
  const parts = [channels];
  if (rule.role !== "any") parts.push(copy.roles[rule.role]);
  if (rule.contact !== "any") parts.push(copy.contacts[rule.contact]);
  if (rule.deal_stages.length) parts.push(copy.stages.replace("{count}", String(rule.deal_stages.length)));
  return parts.join(" · ");
}

export function blankRule(role: SalesRoleKey = "any"): AppliesTo {
  return { role, channels: ["call"], contact: "any", deal_stages: [] };
}

/** Catalog types the company doesn't have yet, for "+ Tipo de llamada". */
export function addableTypes(catalog: CatalogType[], motions: Record<string, MotionStatus>): CatalogType[] {
  return catalog.filter((type) => !(type.key in motions));
}

/** A readable key for a custom type: "Rellamada de cualificación" -> "rellamada_de_cualificacion". */
export function typeKeyFromName(name: string): string {
  return name
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 40);
}
