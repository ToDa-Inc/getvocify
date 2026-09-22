const MOTION_LABELS: Record<string, string> = {
  discovery: "Descubrimiento",
  qualification: "Calificación",
  closing: "Cierre",
};

/** Display label for a sales motion key; unknown keys pass through unchanged. */
export function motionLabel(key: string): string {
  return MOTION_LABELS[key] ?? key;
}
