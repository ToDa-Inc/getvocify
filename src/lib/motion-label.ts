export type MotionLabels = Record<string, string>;

/** Display label for a sales motion key; unknown keys pass through unchanged. */
export function motionLabel(key: string, labels: MotionLabels): string {
  return labels[key] ?? key;
}
