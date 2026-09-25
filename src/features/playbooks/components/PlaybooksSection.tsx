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
import { Button } from "@/components/ui/button";
import { useLanguage } from "@/lib/i18n";
import { motionLabel } from "@/lib/motion-label";
import { productText } from "@/lib/product-catalog";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { api } from "@/shared/lib/api-client";

const MOTIONS = ["discovery", "qualification", "closing"] as const;
const field = "block w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground";

function roleOf(value: string | null | undefined): PlaybookRole {
  if (value === "owner" || value === "admin" || value === "member") return value;
  return "member";
}

export default function PlaybooksSection() {
  const { t } = useLanguage();
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
  const [versions, setVersions] = useState<Record<string, string>>({});
  const [typeKey, setTypeKey] = useState("");
  const [resumeId, setResumeId] = useState("");
  const [openKey, setOpenKey] = useState<string | null>(null);
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
      const data = await api.post<{ motions: Record<string, MotionStatus>; activated?: Record<string, string> }>(
        `/playbooks/${key}/publish`,
      );
      setMotions((current) =>
        applyPublishResult(current, key, {
          ok: data.motions[key] === "published",
          salesMotionKey: key,
          status: data.motions[key],
        }),
      );
      if (data.activated?.[key]) {
        setVersions((current) => ({ ...current, [key]: data.activated?.[key] || "" }));
      }
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

  const statusLabel: Record<MotionStatus, string> = {
    missing: t.product.playbookStatusMissing,
    draft: t.product.playbookStatusDraft,
    importing: t.product.playbookStatusImporting,
    published: t.product.playbookStatusPublished,
  };

  return (
    <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} space-y-5 p-6 md:p-8`}>
      <h2 className={THEME_TOKENS.typography.sectionTitle}>{t.product.playbookTitle}</h2>
      <PlaybookSetupNotice role={role} motions={motions} />
      {notice.canEdit ? (
        <details>
          <summary className={`${THEME_TOKENS.typography.capsLabel} cursor-pointer`}>{t.product.playbookAddType}</summary>
        <form
          className="mt-3 flex flex-wrap gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void addType();
          }}
        >
          <input
            className={`${field} max-w-xs`}
            value={typeKey}
            placeholder={t.product.playbookNewTypePlaceholder}
            onChange={(event) => setTypeKey(event.target.value)}
          />
          <Button type="submit" variant="outline" size="sm">
            {t.product.playbookAddType}
          </Button>
        </form>
        <form
          className="mt-3 flex flex-wrap gap-2"
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
            className={`${field} max-w-xs`}
            value={resumeId}
            placeholder={t.product.playbookImportIdPlaceholder}
            onChange={(event) => setResumeId(event.target.value)}
          />
          <Button type="submit" variant="outline" size="sm">
            {t.product.playbookResumeImport}
          </Button>
        </form>
        </details>
      ) : null}
      <ul className="space-y-3">
        {keys.map((key) => (
          <li key={key} className="rounded-lg bg-secondary/40 px-4 py-4">
            <button
              type="button"
              className="flex w-full items-center justify-between gap-3 text-left"
              onClick={() => setOpenKey((current) => (current === key ? null : key))}
            >
              <span className="text-[15px] text-foreground">{motionLabel(key, t.product.motions)}</span>
              <span className={THEME_TOKENS.typography.capsLabel}>
                {statusLabel[motions[key] || "missing"]}
                {versions[key] ? ` · ${t.product.playbookVersion.replace("{id}", versions[key])}` : ""}
              </span>
            </button>
            {errors[key] ? <p className="mt-2 text-sm text-muted-foreground">{productText(errors[key], t.product)}</p> : null}
            {warnings[key] ? <p className="mt-2 text-sm text-muted-foreground">{productText(warnings[key], t.product)}</p> : null}
            {notice.canEdit && motions[key] !== "published" && openKey === key ? (
              <div className="mt-3 space-y-3">
                <textarea
                  className={field}
                  rows={3}
                  value={text[key] || ""}
                  placeholder={t.product.playbookPastePlaceholder}
                  onChange={(event) => setText((current) => ({ ...current, [key]: event.target.value }))}
                />
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => void saveDraft(key, "text", text[key] || "")}
                  >
                    {t.product.playbookSaveDraft}
                  </Button>
                  <Button type="button" variant="outline" size="sm" asChild>
                    <label>
                      {t.product.playbookImportPdf}
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
                  </Button>
                  {motions[key] === "draft" && canPublish[key] !== false ? (
                    <Button
                      type="button"
                      size="sm"
                      onClick={() => void publish(key)}
                    >
                      {t.product.playbookPublish}
                    </Button>
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
