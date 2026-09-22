export type PlaybookRole = "owner" | "admin" | "member";
export type MotionStatus = "missing" | "draft" | "importing" | "published";

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
    message = "Tu administrador debe configurar el proceso.";
  } else if (none) {
    message = "Define vuestro proceso para activar el coaching.";
  } else if (anyDraft) {
    message = "Tienes un playbook pendiente de publicar.";
  } else if (anyMissing) {
    message = "Falta publicar el proceso de las tipologías pendientes.";
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
      ? "El PDF está protegido. Pega el texto o sube un archivo sin contraseña."
      : record.reason === "pdf_has_no_text"
        ? "El PDF no tiene texto. Prueba con otro archivo o pega el texto."
        : "No se ha podido importar.";
    return { status, error };
  }
  if (record.status === "ready" && record.published === false && status !== "published") {
    return { status: "draft", error: null };
  }
  return { status, error: null };
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
      warning: "Hay pasos contradictorios. Edita el borrador antes de publicar.",
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
