export type PlaybookRole = "owner" | "admin" | "member";
export type MotionStatus = "missing" | "draft" | "importing" | "published" | "paused";

export type PlaybookNotice = {
  showNotice: boolean;
  canEdit: boolean;
  message: string;
  publishedKeys: string[];
};

export function playbookNotice(
  role: PlaybookRole,
  motions: Record<string, MotionStatus>,
): PlaybookNotice {
  const publishedKeys = Object.entries(motions)
    .filter(([, status]) => status === "published")
    .map(([key]) => key);
  const anyDraft = Object.values(motions).some((status) => status === "draft" || status === "importing");
  const anyMissing = Object.values(motions).some((status) => status === "missing");
  const none = Object.keys(motions).length === 0 || Object.values(motions).every((status) => status === "missing");
  const showNotice = none || anyDraft || anyMissing;
  const canEdit = role === "owner" || role === "admin";
  let message = "";
  if (!canEdit) {
    message = "playbookNoticeAdmin";
  } else if (none) {
    message = "playbookNoticeStart";
  } else if (anyDraft) {
    message = "playbookNoticeDraft";
  } else if (anyMissing) {
    message = "playbookNoticeMissing";
  }
  return {
    showNotice,
    canEdit,
    message,
    publishedKeys,
  };
}

export type PublishResult = {
  ok: boolean;
  salesMotionKey?: string;
  status?: MotionStatus;
};

export function applyPublishResult(
  motions: Record<string, MotionStatus>,
  key: string,
  result: PublishResult,
): Record<string, MotionStatus> {
  if (!result.ok || result.salesMotionKey !== key || result.status !== "published") {
    return motions;
  }
  return { ...motions, [key]: "published" };
}

export function motionAfterImport(
  status: MotionStatus,
  record: { status: string; published: boolean; reason?: string | null },
): { status: MotionStatus; error: string | null } {
    if (record.status === "failed") {
    const error = record.reason === "pdf_encrypted"
      ? "playbookPdfEncrypted"
      : record.reason === "pdf_has_no_text"
        ? "playbookPdfNoText"
        : "playbookImportFailed";
    return { status, error };
  }
  if (record.status === "ready" && record.published === false && status !== "published") {
    return { status: "draft", error: null };
  }
  return { status, error: null };
}

/** How a fetched `/playbooks` response is merged into local state. With the flag off, the
 * server always returns every motion, so merging onto the local defaults is safe. With the
 * flag on, the server has already dropped the motions this member's sales_role cannot see
 * (D5) — merging would leave those defaults ("missing") behind and show a flow the member
 * should not see, so the fetched map replaces local state outright. */
export function applyFetchedMotions(
  current: Record<string, MotionStatus>,
  fetched: Record<string, MotionStatus>,
  salesRolesEnabled: boolean,
): Record<string, MotionStatus> {
  return salesRolesEnabled ? { ...fetched } : { ...current, ...fetched };
}

/** D4: which motion keys the editor shows. With the flag off, unchanged (base keys + whatever
 * the company has). With it on, qualification only shows once it has a published version;
 * discovery/closing (already role-filtered by the API) always show. */
export function visiblePlaybookKeys(
  defaultKeys: readonly string[],
  motions: Record<string, MotionStatus>,
  salesRolesEnabled: boolean,
): string[] {
  if (!salesRolesEnabled) {
    return Array.from(new Set<string>([...defaultKeys, ...Object.keys(motions)]));
  }
  return Object.keys(motions).filter((key) => key !== "qualification" || motions[key] === "published");
}

/** D4: "Prospección (SDR)" / "Demo y cierre (AE)" once the flag is on; the plain motion name
 * (and any custom type) otherwise. */
export function flowLabel(
  key: string,
  fallback: string,
  flowLabels: Record<string, string>,
  salesRolesEnabled: boolean,
): string {
  if (salesRolesEnabled && flowLabels[key]) return flowLabels[key];
  return fallback;
}

export function importReview(record: {
  status: string;
  published: boolean;
  draft?: { text?: string; contradictions?: string[] } | null;
}): { status: MotionStatus; warning: string | null; text: string; canPublish: boolean } {
  const contradictions = record.draft?.contradictions ?? [];
  if (record.status === "ready" && contradictions.length > 0) {
    return {
      status: "draft",
      warning: "playbookContradiction",
      text: record.draft?.text || "",
      canPublish: false,
    };
  }
  if (record.status === "ready" && record.published === false) {
    return {
      status: "draft",
      warning: null,
      text: record.draft?.text || "",
      canPublish: true,
    };
  }
  return { status: "missing", warning: null, text: "", canPublish: false };
}
