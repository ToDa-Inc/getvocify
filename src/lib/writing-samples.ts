// Limits mirror backend clean_pasted; the server stays the source of truth.
export const MAX_SAMPLES = 3;
export const MIN_CHARS = 40;
export const MAX_CHARS = 1500;

export const samplesPayload = (drafts: string[]): string[] =>
  drafts.map((draft) => draft.trim()).filter(Boolean);

export const slotsFor = (samples: string[]): string[] =>
  Array.from({ length: MAX_SAMPLES }, (_, i) => samples[i] ?? "");

export const tooShort = (drafts: string[]): boolean =>
  samplesPayload(drafts).some((sample) => sample.length < MIN_CHARS);

export const shortWarning = (drafts: string[], checked: boolean): boolean => checked && tooShort(drafts);

export const isDirty = (drafts: string[], saved: string[]): boolean => {
  const next = samplesPayload(drafts);
  return next.length !== saved.length || next.some((sample, i) => sample !== saved[i]);
};

export const countLabel = (count: number, one: string, many: string): string | null => {
  if (count <= 0) return null;
  return count === 1 ? one : many.replace("{count}", String(count));
};
