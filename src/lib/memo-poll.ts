/**
 * Keep fetching a memo until processing finishes, and a bit longer after
 * pending_review so background transcript polish can replace the cheap STT text.
 */

export const TRANSCRIPT_POLISH_WINDOW_MS = 25_000;

type Stage = { name?: string; at?: string };
type MemoLike = {
  status?: string | null;
  processedAt?: string | null;
  processed_at?: string | null;
  pipelineMeta?: { stages?: Stage[] } | null;
  pipeline_meta?: { stages?: Stage[] } | null;
};

function latestStageAt(stages: Stage[] | undefined, name: string): number {
  let best = 0;
  for (const stage of stages || []) {
    if (stage?.name !== name) continue;
    const t = Date.parse(stage.at || "") || 0;
    if (t > best) best = t;
  }
  return best;
}

export function transcriptPolishSettled(memo: MemoLike | null | undefined): boolean {
  const meta = memo?.pipelineMeta || memo?.pipeline_meta || {};
  const stages = meta.stages || [];
  const extractAt = latestStageAt(stages, "extract");
  const sanitizeAt = latestStageAt(stages, "sanitize");
  return extractAt > 0 && sanitizeAt >= extractAt;
}

export function shouldPollMemo(
  memo: MemoLike | null | undefined,
  now = Date.now(),
  polishWindowMs = TRANSCRIPT_POLISH_WINDOW_MS,
): boolean {
  const status = memo?.status || "";
  if (["uploading", "transcribing", "extracting", "pending_transcript"].includes(status)) {
    return true;
  }
  if (status !== "pending_review") return false;
  if (transcriptPolishSettled(memo)) return false;
  const processed = Date.parse(memo?.processedAt || memo?.processed_at || "") || 0;
  if (!processed) return true;
  return now - processed < polishWindowMs;
}
