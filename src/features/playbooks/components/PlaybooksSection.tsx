import { useEffect, useState } from "react";
import { useAuth } from "@/features/auth";
import { PlaybookSetupNotice } from "@/features/playbooks/components/PlaybookSetupNotice";
import {
  applyPublishResult,
  importReview,
  motionAfterImport,
  playbookNotice,
  type MotionStatus,
  type PlaybookRole,
} from "@/lib/playbook-setup";
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
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [warnings, setWarnings] = useState<Record<string, string>>({});
  const [canPublish, setCanPublish] = useState<Record<string, boolean>>({});
  const [typeKey, setTypeKey] = useState("");
  const [resumeId, setResumeId] = useState("");
  const notice = playbookNotice(role, motions);
  const keys = Array.from(new Set<string>([...MOTIONS, ...Object.keys(motions)]));

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

  async function saveDraft(key: string, kind: "text" | "pdf", payload: string) {
    const body = payload.trim();
    if (!body) return;
    const record = await api.post<{
      status: string;
      published: boolean;
      reason?: string | null;
      draft?: { text?: string; contradictions?: string[] } | null;
    }>(
      "/playbooks/imports",
      {
        import_id: crypto.randomUUID(),
        kind,
        payload: body,
        sales_motion_key: key,
      },
    );
    const next = motionAfterImport(motions[key] || "missing", record);
    const review = importReview(record);
    setErrors((current) => {
      const copy = { ...current };
      if (next.error) copy[key] = next.error;
      else delete copy[key];
      return copy;
    });
    setWarnings((current) => {
      const copy = { ...current };
      if (review.warning) copy[key] = review.warning;
      else delete copy[key];
      return copy;
    });
    setCanPublish((current) => ({ ...current, [key]: review.canPublish }));
    if (review.text) {
      setText((current) => ({ ...current, [key]: review.text }));
    }
    if (next.status !== (motions[key] || "missing")) {
      setMotions((current) => ({ ...current, [key]: next.status }));
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

  async function addType() {
    const key = typeKey.trim();
    if (!key) return;
    const data = await api.post<{ motions: Record<string, MotionStatus> }>("/playbooks/types", {
      type_key: key,
      name: key,
    });
    setMotions((current) => ({ ...current, ...data.motions }));
    setTypeKey("");
  }

  return (
    <div>
      <h2 className="text-lg font-medium mb-2">Proceso comercial</h2>
      <PlaybookSetupNotice role={role} motions={motions} />
      {notice.canEdit ? (
        <form
          className="mb-4 flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void addType();
          }}
        >
          <input
            className="rounded-lg border border-border bg-transparent px-3 py-1 text-sm"
            value={typeKey}
            placeholder="Nueva tipología"
            onChange={(event) => setTypeKey(event.target.value)}
          />
          <button type="submit" className="rounded-full border border-border px-3 py-1 text-sm">
            Añadir tipología
          </button>
        </form>
      ) : null}
      {notice.canEdit ? (
        <form
          className="mb-4 flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            const id = resumeId.trim();
            if (!id) return;
            void api
              .get<{
                status: string;
                published: boolean;
                sales_motion_key?: string;
                draft?: { text?: string; contradictions?: string[] } | null;
              }>(`/playbooks/imports/${id}`)
              .then((record) => {
                const key = record.sales_motion_key;
                if (!key || record.published) return;
                const review = importReview(record);
                setMotions((current) => ({
                  ...current,
                  [key]: review.status === "draft" ? "draft" : current[key] || "missing",
                }));
                if (review.text) setText((current) => ({ ...current, [key]: review.text }));
                setWarnings((current) => {
                  const copy = { ...current };
                  if (review.warning) copy[key] = review.warning;
                  else delete copy[key];
                  return copy;
                });
                setCanPublish((current) => ({ ...current, [key]: review.canPublish }));
                setResumeId("");
              })
              .catch(() => undefined);
          }}
        >
          <input
            className="rounded-lg border border-border bg-transparent px-3 py-1 text-sm"
            value={resumeId}
            placeholder="ID de importación"
            onChange={(event) => setResumeId(event.target.value)}
          />
          <button type="submit" className="rounded-full border border-border px-3 py-1 text-sm">
            Continuar importación
          </button>
        </form>
      ) : null}
      <ul className="space-y-3">
        {keys.map((key) => (
          <li key={key} className="rounded-xl border border-border px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <span className="capitalize">{key}</span>
              <span className="text-sm text-muted-foreground">{LABEL[motions[key] || "missing"]}</span>
            </div>
            {errors[key] ? <p className="mt-2 text-sm text-muted-foreground">{errors[key]}</p> : null}
            {warnings[key] ? <p className="mt-2 text-sm text-muted-foreground">{warnings[key]}</p> : null}
            {notice.canEdit && motions[key] !== "published" ? (
              <div className="mt-3 space-y-2">
                <textarea
                  className="w-full rounded-lg border border-border bg-transparent px-3 py-2 text-sm"
                  rows={3}
                  value={text[key] || ""}
                  placeholder="Pega cómo vendéis en esta tipología"
                  onChange={(event) => setText((current) => ({ ...current, [key]: event.target.value }))}
                />
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="rounded-full border border-border px-3 py-1 text-sm"
                    onClick={() => void saveDraft(key, "text", text[key] || "")}
                  >
                    Guardar borrador
                  </button>
                  <label className="rounded-full border border-border px-3 py-1 text-sm">
                    Importar PDF
                    <input
                      type="file"
                      accept="application/pdf,.pdf"
                      className="sr-only"
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        if (!file) return;
                        const reader = new FileReader();
                        reader.onload = () => {
                          const value = String(reader.result || "");
                          const comma = value.indexOf(",");
                          void saveDraft(key, "pdf", comma >= 0 ? value.slice(comma + 1) : value);
                        };
                        reader.readAsDataURL(file);
                      }}
                    />
                  </label>
                  {motions[key] === "draft" && canPublish[key] !== false ? (
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
