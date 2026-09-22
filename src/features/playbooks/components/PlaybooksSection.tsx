import { useEffect, useState } from "react";
import { useAuth } from "@/features/auth";
import { PlaybookSetupNotice } from "@/features/playbooks/components/PlaybookSetupNotice";
import { applyPublishResult, playbookNotice, type MotionStatus, type PlaybookRole } from "@/lib/playbook-setup";
import { api } from "@/shared/lib/api-client";

const MOTIONS = ["discovery", "qualification", "closing"] as const;

const LABEL: Record<MotionStatus, string> = {
  missing: "Sin proceso publicado",
  draft: "Borrador",
  importing: "Preparando contenido",
  published: "Activo",
};

function roleOf(value: string | null | undefined): PlaybookRole {
  if (value === "owner" || value === "admin" || value === "member") return value;
  return "member";
}

export default function PlaybooksSection() {
  const { user } = useAuth();
  const role = roleOf(user?.company?.role);
  const [motions, setMotions] = useState<Record<string, MotionStatus>>({
    discovery: "missing",
    qualification: "missing",
    closing: "missing",
  });
  const [text, setText] = useState<Record<string, string>>({});
  const notice = playbookNotice(role, motions);

  useEffect(() => {
    let cancelled = false;
    api
      .get<{ motions: Record<string, MotionStatus> }>("/playbooks")
      .then((data) => {
        if (cancelled) return;
        setMotions((current) => ({ ...current, ...data.motions }));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  async function saveDraft(key: string) {
    const payload = (text[key] || "").trim();
    if (!payload) return;
    const record = await api.post<{ status: string; published: boolean }>("/playbooks/imports", {
      import_id: crypto.randomUUID(),
      kind: "text",
      payload,
      sales_motion_key: key,
    });
    if (record.status === "ready" && record.published === false) {
      setMotions((current) => (current[key] === "published" ? current : { ...current, [key]: "draft" }));
    }
  }

  async function publish(key: string) {
    if (motions[key] !== "draft") return;
    try {
      const data = await api.post<{ motions: Record<string, MotionStatus> }>(`/playbooks/${key}/publish`);
      setMotions((current) =>
        applyPublishResult(current, key, {
          ok: data.motions[key] === "published",
          salesMotionKey: key,
          status: data.motions[key],
        }),
      );
    } catch {
      setMotions((current) => applyPublishResult(current, key, { ok: false }));
    }
  }

  return (
    <div>
      <h2 className="text-lg font-medium mb-2">Proceso comercial</h2>
      <PlaybookSetupNotice role={role} motions={motions} />
      <ul className="space-y-3">
        {MOTIONS.map((key) => (
          <li key={key} className="rounded-xl border border-border px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <span className="capitalize">{key}</span>
              <span className="text-sm text-muted-foreground">{LABEL[motions[key]]}</span>
            </div>
            {notice.canEdit && motions[key] !== "published" ? (
              <div className="mt-3 space-y-2">
                <textarea
                  className="w-full rounded-lg border border-border bg-transparent px-3 py-2 text-sm"
                  rows={3}
                  value={text[key] || ""}
                  placeholder="Pega cómo vendéis en esta tipología"
                  onChange={(event) => setText((current) => ({ ...current, [key]: event.target.value }))}
                />
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="rounded-full border border-border px-3 py-1 text-sm"
                    onClick={() => void saveDraft(key)}
                  >
                    Guardar borrador
                  </button>
                  {motions[key] === "draft" ? (
                    <button
                      type="button"
                      className="rounded-full border border-border px-3 py-1 text-sm"
                      onClick={() => void publish(key)}
                    >
                      Publicar
                    </button>
                  ) : null}
                </div>
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
