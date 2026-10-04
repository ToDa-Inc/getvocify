/**
 * The playbook as steps and objection answers (PUT /playbooks/{key}/draft). Pure helpers:
 * templates, turning pasted text into steps (deterministic, no model call) and the same
 * validation the backend applies (services/playbooks/structured.py), so the Head of Sales
 * sees what is wrong before saving.
 */

export const OBJECTION_CATEGORIES = [
  "price",
  "timing",
  "authority",
  "competitor",
  "status_quo",
  "trust",
  "other",
] as const;
export type ObjectionCategory = (typeof OBJECTION_CATEGORIES)[number];

export const MAX_STEPS = 15;
export const MAX_LABEL = 80;
export const MAX_CRITERION = 400;
export const MAX_EXAMPLE = 300;
export const MAX_GUIDANCE = 600;

export type EditorStep = {
  /** Client-side key for React lists; never sent. */
  key: string;
  step_id?: string | null;
  label: string;
  criterion: string;
  example?: string;
};

// Plan §15: the company's own objections, and what each answer is made of.
export const MAX_CUSTOM_OBJECTIONS = 12;
export const MAX_OBJECTION_LABEL = 60;
export const MAX_TRIGGER = 200;
export const MAX_CRITERIA = 8;
export const MAX_CRITERION_LABEL = 60;
export const MAX_CRITERION_FIELD = 200;

export type ObjectionKind = ObjectionCategory | "custom";

/** An objection is what the prospect says, its kind and the answer. Nothing else. */
export type EditorObjection = {
  category: ObjectionKind;
  /** The answer the rep sees. */
  guidance: string;
  /** Custom objections only: the stable slug. */
  id?: string;
  /** Custom objections only: its name. */
  label?: string;
  /** How the prospect says it ("Ahora mismo no tenemos presupuesto"), for any kind. */
  trigger?: string;
};

/** "Qué tiene que salir de la llamada": what the rep has to find out, and how a good answer sounds. */
export type EditorCriterion = {
  /** Client-side key for React lists; never sent. */
  key: string;
  criterion_id?: string | null;
  label: string;
  good?: string;
};

type ObjectionSnapshot = {
  category: string;
  guidance: string;
  id?: string;
  label?: string;
  trigger?: string;
};

export type EditorSnapshot = {
  source: "draft" | "published" | "empty";
  version_id: string | null;
  steps: { step_id: string; label: string; criterion: string; example?: string }[];
  objections: ObjectionSnapshot[];
  qualification?: { criterion_id: string; label: string; good?: string }[];
};

/** One key per objection row: the category, or the custom objection's own id. */
export function objectionKey(item: Pick<EditorObjection, "category" | "id">): string {
  return item.category === "custom" ? `custom:${item.id ?? ""}` : item.category;
}

export type StepError =
  | "empty_label"
  | "label_too_long"
  | "criterion_too_long"
  | "example_too_long";

let counter = 0;
export function newStepKey(): string {
  counter += 1;
  return `s${Date.now().toString(36)}${counter}`;
}

function tidy(value: string): string {
  return value.split(/\s+/).filter(Boolean).join(" ");
}

type Lang = "es" | "en";
type TemplateStep = { step_id: string; es: [string, string]; en: [string, string] };

const TEMPLATES: Record<string, TemplateStep[]> = {
  discovery: [
    { step_id: "opening", es: ["Apertura", "Se presenta, dice por qué llama y pide un momento para hablar."], en: ["Opening", "Introduces themselves, says why they are calling and asks for a moment to talk."] },
    { step_id: "reason", es: ["Motivo de la llamada", "Conecta la llamada con algo concreto del prospecto: su sector, su rol o algo que haya hecho."], en: ["Reason for the call", "Ties the call to something specific about the prospect: their industry, role or something they did."] },
    { step_id: "pain", es: ["Descubrir el dolor", "Pregunta cómo lo hacen hoy y repregunta por lo que no les funciona."], en: ["Find the pain", "Asks how they do it today and follows up on what isn't working."] },
    { step_id: "qualify", es: ["Cualificar", "Confirma quién decide, cuándo quieren resolverlo y si es una prioridad."], en: ["Qualify", "Confirms who decides, when they want to solve it and whether it is a priority."] },
    { step_id: "meeting", es: ["Agendar la reunión", "Propone una reunión con un día y una hora concretos."], en: ["Book the meeting", "Proposes a meeting with a specific day and time."] },
  ],
  closing: [
    { step_id: "agenda", es: ["Agenda y objetivo", "Abre con la agenda y con lo que se quiere decidir al final de la reunión."], en: ["Agenda and goal", "Opens with the agenda and what should be decided by the end of the meeting."] },
    { step_id: "recap_pain", es: ["Repasar el dolor", "Confirma con el prospecto el problema que se habló antes."], en: ["Recap the pain", "Confirms with the prospect the problem discussed before."] },
    { step_id: "demo", es: ["Demo enfocada", "Enseña solo lo que resuelve el problema confirmado."], en: ["Focused demo", "Shows only what solves the confirmed problem."] },
    { step_id: "objections", es: ["Resolver dudas", "Responde cada duda del prospecto y comprueba si queda resuelta."], en: ["Handle concerns", "Answers each of the prospect's concerns and checks it is resolved."] },
    { step_id: "next_step", es: ["Siguiente paso", "Propone el siguiente paso con fecha: propuesta, prueba o firma."], en: ["Next step", "Proposes the next step with a date: proposal, trial or signature."] },
  ],
};

TEMPLATES.qualification = [TEMPLATES.discovery[2], TEMPLATES.discovery[3], TEMPLATES.discovery[4]];

/** A starting point per flow; any other motion gets the prospecting one. */
export function templateSteps(motion: string, lang: Lang): EditorStep[] {
  const template = TEMPLATES[motion] ?? TEMPLATES.discovery;
  return template.map((step) => {
    const [label, criterion] = lang === "en" ? step.en : step.es;
    return { key: newStepKey(), step_id: step.step_id, label, criterion };
  });
}

const MARKER = /^\s*(?:(?:paso|step)\s*)?(?:\d{1,2}[.)\-:]|[-•*·]|#{1,6})\s+/i;
const HEADING = /^\s*#{1,6}\s+/;
const NUMBER = /^\s*(?:(?:paso|step)\s*)?\d{1,2}[.)\-:]\s+/i;
const BULLET = /^\s*[-•*·]\s+/;
const SPLIT = /\s*(?::|—|–|\s-\s)\s*/;
const EMPHASIS = /\*\*|__|`/g;
const SHORT_LABEL = 60;
/** Words a cut label must not end on ("…equipo comercial activo y"). */
const DANGLING = new Set(
  "y o e u de del con en a al para por que la el los las un una sin and or of with to for in on the a an that".split(" "),
);

/** Bold and code marks a document carries: never shown in a step. */
export function stripMarkdown(value: string): string {
  return (value || "").replace(EMPHASIS, "");
}

function clip(text: string, limit: number): string {
  if (text.length <= limit) return text;
  let cut = text.slice(0, limit);
  const space = cut.lastIndexOf(" ");
  if (space >= limit * 0.6) cut = cut.slice(0, space);
  return cut.replace(/[\s,;:\-—–]+$/, "");
}

/** The name of a step from a sentence: its first clause when long, never cut mid-word. */
export function shortLabel(text: string): string {
  const sentence = (tidy(text).split(/(?<=[.!?])\s+/)[0] ?? "").replace(/[.!?:]+$/, "").trim();
  if (sentence.length <= SHORT_LABEL) return sentence;
  for (const mark of [", ", " (", "; ", " — ", " – "]) {
    const at = sentence.indexOf(mark);
    if (at >= 12 && at <= SHORT_LABEL) return sentence.slice(0, at).trim();
  }
  const words = clip(sentence, SHORT_LABEL).split(" ");
  while (words.length > 1 && DANGLING.has(words[words.length - 1].toLowerCase())) words.pop();
  return words.join(" ");
}

/** A long description keeps whole sentences when it has to be cut. */
function clipSentences(text: string, limit: number): string {
  if (text.length <= limit) return text;
  const cut = text.slice(0, limit);
  const end = Math.max(cut.lastIndexOf(". "), cut.lastIndexOf("! "), cut.lastIndexOf("? "));
  return end >= limit * 0.5 ? cut.slice(0, end + 1) : clip(text, limit);
}

function stepFromLine(line: string): EditorStep {
  const body = tidy(line.replace(MARKER, ""));
  const match = body.match(SPLIT);
  if (match && match.index !== undefined && match.index > 0 && match.index <= MAX_LABEL) {
    const label = tidy(body.slice(0, match.index));
    const criterion = tidy(body.slice(match.index + match[0].length));
    return { key: newStepKey(), label, criterion: criterion || label };
  }
  return { key: newStepKey(), label: shortLabel(body), criterion: body };
}

/** Lines under a step become its description; each list item reads as its own sentence. */
function join(previous: string, piece: string, item: boolean): string {
  if (!previous) return piece;
  return `${item && !/[.!?:;]$/.test(previous) ? `${previous}.` : previous} ${piece}`;
}

type LineKind = { heading: boolean; numbered: boolean; body: string };

/**
 * A document with an outline ("### 1. Elegir la cuenta" and bullets under it): the numbered
 * headings are the steps and everything under one is its description. Headings without a
 * number ("## Objetivo del rol") are context, not steps. Null when there is no outline.
 */
function outlineSteps(lines: string[]): { label: string; criterion: string }[] | null {
  const kinds: LineKind[] = lines.map((line) => {
    const heading = HEADING.test(line);
    const body = line.replace(HEADING, "");
    const numbered = NUMBER.test(body);
    return { heading, numbered, body: tidy(numbered ? body.replace(NUMBER, "") : body) };
  });
  const follows = (index: number) => {
    const next = kinds.slice(index + 1).find((kind) => kind.body);
    return Boolean(next && !next.numbered && !next.heading);
  };

  let isStep: (kind: LineKind) => boolean;
  const closes = (kind: LineKind) => kind.heading;
  if (kinds.some((kind) => kind.heading && kind.numbered)) {
    isStep = (kind) => kind.heading && kind.numbered;
  } else if (kinds.filter((kind) => kind.heading && kind.body).length >= 2 && kinds.some((kind) => !kind.heading && kind.body)) {
    isStep = (kind) => kind.heading;
  } else if (
    kinds.some(
      (kind, index) =>
        kind.numbered && !kind.heading && kind.body && !SPLIT.test(kind.body) && kind.body.length <= SHORT_LABEL && follows(index),
    )
  ) {
    isStep = (kind) => kind.numbered && !kind.heading;
  } else {
    return null;
  }

  let steps: { label: string; criterion: string }[] = [];
  let current: { label: string; criterion: string } | null = null;
  lines.forEach((raw, index) => {
    const kind = kinds[index];
    if (!kind.body) return;
    if (isStep(kind)) {
      const label = kind.body.replace(/[:.]+$/, "").trim();
      current = { label: label.length <= MAX_LABEL ? label : shortLabel(label), criterion: "" };
      steps.push(current);
    } else if (closes(kind)) {
      current = null;
    } else if (current) {
      const item = BULLET.test(raw) || NUMBER.test(raw);
      const piece = item ? tidy(raw.replace(MARKER, "")) : kind.body;
      current.criterion = join(current.criterion, piece, item);
    }
  });
  // A title heading with nothing under it is not a step.
  steps = steps.filter((step, index) => step.criterion || steps.length === 1 || index !== 0);
  return steps.map((step) => ({ ...step, criterion: clipSentences(step.criterion, MAX_CRITERION) || step.label }));
}

/**
 * Pasted process text -> steps. An outline (numbered headings with lines under them) gives
 * one step per heading. Otherwise numbered, bulleted or heading lines start a step
 * ("1. Apertura: se presenta…", "- Cualificar — quién decide") and lines under one are added
 * to its description; without any marker, each paragraph is a step. Markdown is dropped and
 * long sentences get a short name. Never more than MAX_STEPS; same as the backend's
 * parse_playbook_text.
 */
export function parsePlaybookText(text: string): EditorStep[] {
  const lines = (text || "")
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .map((line) => stripMarkdown(line).replace(/^>\s*/, "").trimEnd());
  const outline = outlineSteps(lines);
  if (outline) {
    return outline
      .filter((step) => step.label)
      .slice(0, MAX_STEPS)
      .map((step) => ({ key: newStepKey(), ...step }));
  }
  const marked = lines.some((line) => MARKER.test(line));
  const steps: EditorStep[] = [];
  if (marked) {
    for (const raw of lines) {
      const line = raw.trim();
      if (!line) continue;
      if (MARKER.test(raw)) {
        steps.push(stepFromLine(line));
      } else if (steps.length > 0) {
        const last = steps[steps.length - 1];
        last.criterion = tidy(`${last.criterion === last.label ? "" : last.criterion} ${line}`);
      }
    }
  } else {
    for (const paragraph of lines.join("\n").split(/\n\s*\n/)) {
      if (paragraph.trim()) steps.push(stepFromLine(paragraph.trim()));
    }
  }
  return steps.filter((step) => step.label).slice(0, MAX_STEPS);
}

/**
 * How many steps look badly split by an import: a name that is only a number ("1"), a
 * description that still starts with its numbering ("1. Elegir la cuenta"), or a long name cut
 * mid-word from its own description ("…alta frecuencia de l").
 */
export function messySteps(steps: { label: string; criterion: string }[]): number {
  return steps.filter((step) => {
    const label = step.label.trim();
    const criterion = step.criterion.trim();
    if (/^[\d.)\s-]+$/.test(label)) return true;
    if (/^\d{1,2}[.)]\s/.test(criterion)) return true;
    const cut = label.length >= 50 && criterion.startsWith(label) && /\w/.test(criterion.charAt(label.length));
    return cut && /\w$/.test(label);
  }).length;
}

/** The steps as text for Vocify to structure again: "- name: description", or the description alone when the name is noise. */
export function stepsAsText(steps: { label: string; criterion: string }[]): string {
  return steps
    .map((step) => {
      const label = step.label.trim();
      const criterion = step.criterion.trim();
      if (!criterion || criterion === label) return `- ${label}`;
      if (/^[\d.)\s-]+$/.test(label) || criterion.startsWith(label)) return `- ${criterion}`;
      return `- ${label}: ${criterion}`;
    })
    .join("\n");
}

/** A version imported before steps existed: one step holding the whole document. */
export function isLegacyBlob(steps: { step_id?: string | null; criterion: string }[]): boolean {
  return steps.length === 1 && (steps[0].step_id === "imported" || steps[0].criterion.length > MAX_CRITERION);
}

export function stepError(step: EditorStep): StepError | null {
  const label = tidy(step.label);
  if (!label) return "empty_label";
  if (label.length > MAX_LABEL) return "label_too_long";
  if (tidy(step.criterion).length > MAX_CRITERION) return "criterion_too_long";
  if (tidy(step.example ?? "").length > MAX_EXAMPLE) return "example_too_long";
  return null;
}

export function draftError(
  steps: EditorStep[],
  objections: EditorObjection[],
  qualification: EditorCriterion[] = [],
): string | null {
  if (steps.length === 0) return "no_steps";
  if (steps.length > MAX_STEPS) return "too_many_steps";
  const stepProblem = steps.map(stepError).find(Boolean);
  if (stepProblem) return stepProblem;
  if (objections.some((item) => tidy(item.guidance).length > MAX_GUIDANCE)) return "guidance_too_long";
  const custom = objections.filter((item) => item.category === "custom");
  if (custom.length > MAX_CUSTOM_OBJECTIONS) return "too_many_custom_objections";
  if (custom.some((item) => !tidy(item.label ?? ""))) return "custom_objection_label_empty";
  if (custom.some((item) => tidy(item.label ?? "").length > MAX_OBJECTION_LABEL)) return "field_too_long";
  const tooLong = (value: string | undefined, max: number) => tidy(value ?? "").length > max;
  if (objections.some((item) => tooLong(item.trigger, MAX_TRIGGER))) return "field_too_long";
  if (qualification.length > MAX_CRITERIA) return "too_many_criteria";
  if (qualification.some((item) => !tidy(item.label))) return "criterion_label_empty";
  if (qualification.some((item) => tidy(item.label).length > MAX_CRITERION_LABEL)) return "criterion_label_too_long";
  if (qualification.some((item) => tooLong(item.good, MAX_CRITERION_FIELD))) return "field_too_long";
  return null;
}

function optional(fields: Record<string, string | undefined>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [name, value] of Object.entries(fields)) {
    const clean = tidy(value ?? "");
    if (clean) out[name] = clean;
  }
  return out;
}

/** PUT /draft body. A fixed objection without an answer isn't sent; a custom one is (it can be
 * detected before it has an answer). Qualification is sent only when the caller has it. */
export function draftPayload(steps: EditorStep[], objections: EditorObjection[], qualification?: EditorCriterion[]) {
  return {
    steps: steps.map((step) => ({
      ...(step.step_id ? { step_id: step.step_id } : {}),
      label: tidy(step.label),
      criterion: tidy(step.criterion),
      ...(tidy(step.example ?? "") ? { example: tidy(step.example ?? "") } : {}),
    })),
    objections: objections
      .filter((item) => (item.category === "custom" ? tidy(item.label ?? "") : tidy(item.guidance)))
      .map((item) => ({
        category: item.category,
        guidance: tidy(item.guidance),
        ...(item.category === "custom" ? { ...(item.id ? { id: item.id } : {}), label: tidy(item.label ?? "") } : {}),
        ...optional({ trigger: item.trigger }),
      })),
    ...(qualification
      ? {
          qualification: qualification
            .filter((item) => tidy(item.label))
            .map((item) => ({
              ...(item.criterion_id ? { criterion_id: item.criterion_id } : {}),
              label: tidy(item.label),
              ...optional({ good: item.good }),
            })),
        }
      : {}),
  };
}

export function stepsFromSnapshot(snapshot: EditorSnapshot | null | undefined): EditorStep[] {
  return (snapshot?.steps ?? []).map((step) => ({
    key: newStepKey(),
    step_id: step.step_id,
    // Imported before markdown was dropped at import: never show the marks.
    label: stripMarkdown(step.label),
    criterion: stripMarkdown(step.criterion),
    example: step.example ?? "",
  }));
}

export function objectionsFromSnapshot(snapshot: EditorSnapshot | null | undefined): EditorObjection[] {
  return (snapshot?.objections ?? [])
    .filter((item) => item.category === "custom" || (OBJECTION_CATEGORIES as readonly string[]).includes(item.category))
    // Older answers may carry meaning / question / proof: not kept, so the next save drops them.
    .map((item) => ({
      category: item.category as ObjectionKind,
      guidance: item.guidance ?? "",
      ...(item.id ? { id: item.id } : {}),
      ...(item.label ? { label: item.label } : {}),
      ...(item.trigger ? { trigger: item.trigger } : {}),
    }));
}

export function criteriaFromSnapshot(snapshot: EditorSnapshot | null | undefined): EditorCriterion[] {
  return (snapshot?.qualification ?? []).map((item) => ({
    key: newStepKey(),
    criterion_id: item.criterion_id,
    label: stripMarkdown(item.label),
    good: item.good ?? "",
  }));
}

export function moveStep(steps: EditorStep[], index: number, delta: -1 | 1): EditorStep[] {
  const target = index + delta;
  if (target < 0 || target >= steps.length) return steps;
  const next = steps.slice();
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}
