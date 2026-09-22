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
  const showNotice = Object.keys(motions).length === 0 || Object.values(motions).some((status) => status !== "published");
  const canEdit = role === "owner" || role === "admin";
  return {
    showNotice,
    canEdit,
    message: canEdit
      ? "Elige una tipología, aporta el contenido, revísalo y publícalo."
      : "El proceso comercial lo configura un administrador. Puedes leerlo cuando esté publicado.",
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
