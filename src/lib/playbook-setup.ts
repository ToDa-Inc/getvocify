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
