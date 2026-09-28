/** Ask's tool steps as the user reads them ("Buscando contactos · Marc"). The backend sends
 * the tool name, never an id; the words live in product-catalog (askStepLabels). */

export type AskStep = { tool: string; state: "running" | "done" | "error"; detail?: string };

export function askStepsFrom(value: unknown): AskStep[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is AskStep =>
      Boolean(item) && typeof item === "object" && typeof (item as AskStep).tool === "string",
    )
    .map((item) => ({
      tool: item.tool,
      state: item.state === "done" || item.state === "error" ? item.state : "running",
      detail: typeof item.detail === "string" ? item.detail : "",
    }));
}

export function askStepLabel(step: AskStep, labels: Record<string, string>, fallback: string): string {
  const base = labels[step.tool] ?? fallback;
  return step.detail ? `${base} · ${step.detail}` : base;
}

/** "Consultado en 3 pasos": the folded summary under a finished answer. */
export function askStepsSummary(steps: AskStep[], template: string, templateOne: string): string | null {
  if (steps.length === 0) return null;
  return steps.length === 1 ? templateOne : template.replace("{count}", String(steps.length));
}
