import { motionLabel, type MotionLabels } from "./motion-label.ts";

/**
 * A call type's name: a catalog type reads in the app's language, a company's own type keeps its name.
 * `labels` are the app's names for catalog types, `motions` the fallback for the base flows.
 */
export function typeName(
  key: string,
  labels: Record<string, string>,
  details: Record<string, { label: string | null; catalog: boolean } | undefined>,
  motions: MotionLabels,
): string {
  const localized = labels[key];
  if (localized && (details[key]?.catalog ?? true)) return localized;
  return details[key]?.label || localized || motionLabel(key, motions);
}
