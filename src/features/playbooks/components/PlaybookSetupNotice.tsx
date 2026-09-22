import { playbookNotice, type MotionStatus, type PlaybookRole } from "@/lib/playbook-setup";

export function PlaybookSetupNotice({
  role,
  motions,
}: {
  role: PlaybookRole;
  motions: Record<string, MotionStatus>;
}) {
  const notice = playbookNotice(role, motions);
  if (!notice.showNotice) return null;
  return (
    <section className="mb-6 rounded-2xl border border-border bg-card p-5" role="status">
      <p className="text-sm text-muted-foreground">{notice.message}</p>
      {notice.canEdit ? (
        <ol className="mt-3 list-decimal pl-5 text-sm">
          <li>Elegir tipología</li>
          <li>Aportar texto, PDF o audio</li>
          <li>Revisar</li>
          <li>Publicar</li>
        </ol>
      ) : null}
    </section>
  );
}
