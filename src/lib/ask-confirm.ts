export type AskConfirmBody = {
  status?: string;
  text?: string;
  applied?: boolean;
  replayed?: boolean;
  operation_id?: string;
};

export type ConfirmApplyOutcome = {
  clearPending: boolean;
  text: string | null;
};

function confirmSucceeded(body: AskConfirmBody): boolean {
  return body.status === "succeeded" || body.applied === true || body.replayed === true;
}

export function confirmResult(body: AskConfirmBody | null | undefined): ConfirmApplyOutcome {
  if (!body || !confirmSucceeded(body)) {
    return { clearPending: false, text: null };
  }
  const text = typeof body.text === "string" && body.text.trim() ? body.text.trim() : null;
  return { clearPending: true, text };
}

export function confirmErrorDetail(data: unknown): string | null {
  if (!data || typeof data !== "object") return null;
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) return detail.trim();
  return null;
}
