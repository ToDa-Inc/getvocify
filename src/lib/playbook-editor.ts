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

export type EditorObjection = { category: ObjectionCategory; guidance: string };

export type EditorSnapshot = {
  source: "draft" | "published" | "empty";
  version_id: string | null;
  steps: { step_id: string; label: string; criterion: string; example?: string }[];
  objections: { category: string; guidance: string }[];
};

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
    { step_id: "pain", es: ["Descubrir el dolor", "Pregunta cómo lo hacen hoy y consigue que el prospecto nombre un problema concreto."], en: ["Find the pain", "Asks how they do it today and gets the prospect to name a concrete problem."] },
    { step_id: "qualify", es: ["Cualificar", "Confirma quién decide, cuándo quieren resolverlo y si es una prioridad."], en: ["Qualify", "Confirms who decides, when they want to solve it and whether it is a priority."] },
    { step_id: "meeting", es: ["Agendar la reunión", "Propone una reunión con día y hora y el prospecto la acepta."], en: ["Book the meeting", "Proposes a meeting with a day and time and the prospect accepts it."] },
  ],
  closing: [
    { step_id: "agenda", es: ["Agenda y objetivo", "Abre con la agenda y con lo que se quiere decidir al final de la reunión."], en: ["Agenda and goal", "Opens with the agenda and what should be decided by the end of the meeting."] },
    { step_id: "recap_pain", es: ["Repasar el dolor", "Confirma con el prospecto el problema que se habló antes."], en: ["Recap the pain", "Confirms with the prospect the problem discussed before."] },
    { step_id: "demo", es: ["Demo enfocada", "Enseña solo lo que resuelve el problema confirmado."], en: ["Focused demo", "Shows only what solves the confirmed problem."] },
    { step_id: "objections", es: ["Resolver dudas", "Responde las dudas del prospecto hasta que quedan resueltas o claras."], en: ["Handle concerns", "Answers the prospect's concerns until they are resolved or clear."] },
    { step_id: "next_step", es: ["Siguiente paso", "Acuerda el siguiente paso con fecha: propuesta, prueba o firma."], en: ["Next step", "Agrees the next step with a date: proposal, trial or signature."] },
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

const MARKER = /^\s*(?:(?:paso|step)\s*)?(?:\d{1,2}[.)\-:]|[-•*·]|#{1,4})\s+/i;
const SPLIT = /\s*(?::|—|–|\s-\s)\s*/;

function stepFromLine(line: string): EditorStep {
  const body = line.replace(MARKER, "").trim();
  const match = body.match(SPLIT);
  if (match && match.index !== undefined && match.index > 0 && match.index <= MAX_LABEL) {
    const label = tidy(body.slice(0, match.index));
    const criterion = tidy(body.slice(match.index + match[0].length));
    return { key: newStepKey(), label, criterion: criterion || label };
  }
  const sentence = body.split(/(?<=[.!?])\s+/)[0] ?? body;
  const label = tidy(sentence).replace(/[.!?]+$/, "").slice(0, MAX_LABEL).trim();
  return { key: newStepKey(), label, criterion: tidy(body) };
}

/**
 * Pasted process text -> steps. Numbered, bulleted or heading lines start a step
 * ("1. Apertura: se presenta…", "- Cualificar — quién decide"); lines under one are added
 * to its description. Without any marker, each paragraph is a step. Never more than
 * MAX_STEPS; the Head of Sales reviews the result before saving.
 */
export function parsePlaybookText(text: string): EditorStep[] {
  const lines = (text || "").replace(/\r\n?/g, "\n").split("\n");
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
    for (const paragraph of (text || "").split(/\n\s*\n/)) {
      if (paragraph.trim()) steps.push(stepFromLine(paragraph.trim()));
    }
  }
  return steps.filter((step) => step.label).slice(0, MAX_STEPS);
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

export function draftError(steps: EditorStep[], objections: EditorObjection[]): string | null {
  if (steps.length === 0) return "no_steps";
  if (steps.length > MAX_STEPS) return "too_many_steps";
  const stepProblem = steps.map(stepError).find(Boolean);
  if (stepProblem) return stepProblem;
  if (objections.some((item) => tidy(item.guidance).length > MAX_GUIDANCE)) return "guidance_too_long";
  return null;
}

export function draftPayload(steps: EditorStep[], objections: EditorObjection[]) {
  return {
    steps: steps.map((step) => ({
      ...(step.step_id ? { step_id: step.step_id } : {}),
      label: tidy(step.label),
      criterion: tidy(step.criterion),
      ...(tidy(step.example ?? "") ? { example: tidy(step.example ?? "") } : {}),
    })),
    objections: objections
      .filter((item) => tidy(item.guidance))
      .map((item) => ({ category: item.category, guidance: tidy(item.guidance) })),
  };
}

export function stepsFromSnapshot(snapshot: EditorSnapshot | null | undefined): EditorStep[] {
  return (snapshot?.steps ?? []).map((step) => ({
    key: newStepKey(),
    step_id: step.step_id,
    label: step.label,
    criterion: step.criterion,
    example: step.example ?? "",
  }));
}

export function objectionsFromSnapshot(snapshot: EditorSnapshot | null | undefined): EditorObjection[] {
  return (snapshot?.objections ?? []).filter((item): item is EditorObjection =>
    (OBJECTION_CATEGORIES as readonly string[]).includes(item.category),
  );
}

export function moveStep(steps: EditorStep[], index: number, delta: -1 | 1): EditorStep[] {
  const target = index + delta;
  if (target < 0 || target >= steps.length) return steps;
  const next = steps.slice();
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}
