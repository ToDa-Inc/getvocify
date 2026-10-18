import { useEffect, useState } from "react";
import { Check, Upload } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { useAuth } from "@/features/auth";
import { authApi, authKeys } from "@/features/auth/api";
import type { User } from "@/features/auth/types";
import { playbooksApi, type CompanyFillScope } from "@/features/playbooks/api";
import { WindowShell } from "@/features/playbooks/components/home/WindowShell";
import { PlaybookStart, type SourceInput } from "@/features/playbooks/components/PlaybookStart";
import { areaFillScope, areasFromKnowledge, knowledgeFromAreas, type AreaId, type Areas } from "@/lib/company-areas";
import { useLanguage } from "@/lib/i18n";
import { COMPANY_AREAS } from "@/lib/playbook-home";
import { cleanKnowledge, type Knowledge } from "@/lib/playbook-knowledge";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";
import { ApiError } from "@/shared/lib/api-client";

const PRODUCT_MAX = 8000;
const field = cn(
  THEME_TOKENS.radius.control,
  "block w-full resize-none border border-border bg-background px-3 py-2 text-[14px] leading-relaxed text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-beige/40",
);

/**
 * "Vuestra empresa" in one window, like the content of the funnel: one document with everything (Vocify splits it into the
 * six areas), or each area on its own with a small box to paste a text or upload a document. Each one saves at once and
 * shows "Listo"; "Editar" corrects what is written. The product is the product text live help already reads: a document
 * given for it is kept as written, the other areas are sorted by Vocify into their part of the notes.
 */
export function CompanyWindow({ open, onOpenChange, canEdit }: { open: boolean; onOpenChange: (open: boolean) => void; canEdit: boolean }) {
  const { t } = useLanguage();
  const c = t.product.pb2.home;
  const labels = c as unknown as Record<string, string>;
  const { user } = useAuth();
  const client = useQueryClient();
  const [loading, setLoading] = useState(true);
  const [knowledge, setKnowledge] = useState<Knowledge>({});
  const [base, setBase] = useState<string | null>(null);
  const [areas, setAreas] = useState<Areas>(areasFromKnowledge(null, null));
  const [writing, setWriting] = useState<AreaId | "whole" | null>(null);
  const [editing, setEditing] = useState<AreaId | null>(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setWriting(null);
    setEditing(null);
    setProblem(false);
    void playbooksApi
      .company()
      .then((doc) => {
        if (cancelled) return;
        setKnowledge(doc.knowledge ?? {});
        setBase(doc.updated_at);
        setAreas(areasFromKnowledge(doc.knowledge, user?.productContext));
      })
      .catch(() => undefined)
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // The window reads what is saved each time it opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const changed = () => void client.invalidateQueries({ queryKey: ["playbook-company"] });
  const saveProduct = async (text: string) => {
    const updated = await authApi.updateProfile({ productContext: text });
    client.setQueryData<User>(authKeys.me(), updated);
  };

  // A document for everything, or for one area: Vocify writes it where it belongs and it is saved at once.
  const fill = async (source: SourceInput, scope?: CompanyFillScope) => {
    const done = await playbooksApi.fillCompany(source, base, scope);
    if (scope && !done.filled.length) throw new ApiError(422, { detail: { code: "nothing_for_area" } });
    setKnowledge(done.knowledge ?? {});
    setBase(done.updated_at);
    setAreas((now) => ({ ...areasFromKnowledge(done.knowledge, now.product), product: now.product }));
    changed();
  };

  const add = async (id: AreaId | "whole", source: SourceInput) => {
    if (id === "whole") await fill(source);
    else if (id === "product") {
      const text = source.kind === "text" ? source.payload.trim() : (await playbooksApi.readCompany(source)).text;
      if (!text) throw new ApiError(422, { detail: { code: "nothing_for_area" } });
      const next = [areas.product.trim(), text].filter(Boolean).join("\n\n").slice(0, PRODUCT_MAX);
      await saveProduct(next);
      setAreas((now) => ({ ...now, product: next }));
    } else await fill(source, areaFillScope(id) ?? undefined);
    setWriting(null);
  };

  const saveEdit = async (id: AreaId) => {
    setSaving(true);
    setProblem(false);
    try {
      const nextAreas = { ...areas, [id]: draft };
      if (id === "product") await saveProduct(draft.trim());
      else {
        const doc = await playbooksApi.saveCompany(cleanKnowledge(knowledgeFromAreas(knowledge, nextAreas).knowledge), base);
        setKnowledge(doc.knowledge ?? {});
        setBase(doc.updated_at);
        changed();
      }
      setAreas(nextAreas);
      setEditing(null);
    } catch {
      setProblem(true);
    } finally {
      setSaving(false);
    }
  };

  const box = (id: AreaId | "whole") => (
    <div className={THEME_TOKENS.motion.fadeIn}>
      <PlaybookStart
        minHeight="min-h-[120px]"
        placeholder={id === "whole" ? c.companyPh : c.areaPh}
        readingLabel={c.reading}
        submitLabel={c.save}
        onCancel={() => setWriting(null)}
        submit={(source) => add(id, source)}
      />
    </div>
  );

  const footer = loading ? undefined : (
    <>
      <span />
      <Button type="button" onClick={() => onOpenChange(false)}>
        {c.close}
      </Button>
    </>
  );

  return (
    <WindowShell open={open} onOpenChange={onOpenChange} title={c.companyTitle} lead={canEdit ? c.companyLead : undefined} footer={footer}>
      {loading ? (
        <div className="space-y-3" role="status" aria-busy="true">
          <Skeleton className="h-16 w-full motion-reduce:animate-none" />
          <Skeleton className="h-16 w-full motion-reduce:animate-none" />
        </div>
      ) : (
        <div className="space-y-5">
          {canEdit ? (
            writing === "whole" ? (
              box("whole")
            ) : (
              <button
                type="button"
                onClick={() => {
                  setEditing(null);
                  setWriting("whole");
                }}
                className={cn(THEME_TOKENS.radius.control, "flex w-full items-center gap-3 border border-dashed border-border px-4 py-3 text-left transition-colors hover:border-beige/40 hover:bg-secondary/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring")}
              >
                <Upload aria-hidden className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.5} />
                <span className="text-[14px] text-foreground">
                  {c.companyWholeBar} <span className="text-muted-foreground">{c.companyWholeHint}</span>
                </span>
              </button>
            )
          ) : null}
          <ul className="divide-y divide-border/50">
            {COMPANY_AREAS.map((area) => {
              const id = area.id as AreaId;
              const text = areas[id].trim();
              return (
                <li key={id} className="space-y-3 py-4">
                  <div className="flex items-center gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="text-[15px] font-medium text-foreground">{labels[`area_${id}`]}</p>
                      <p className="text-[12px] text-muted-foreground">{labels[`hint_${id}`]}</p>
                    </div>
                    {text && editing !== id ? (
                      <span className="flex items-center gap-3">
                        <span className="inline-flex items-center gap-1 text-[13px] text-success">
                          <Check aria-hidden className="h-3.5 w-3.5" strokeWidth={2} />
                          {c.ready}
                        </span>
                        {canEdit ? (
                          <Button
                            type="button"
                            variant="quiet"
                            size="text"
                            onClick={() => {
                              setWriting(null);
                              setProblem(false);
                              setDraft(areas[id]);
                              setEditing(id);
                            }}
                          >
                            {c.edit}
                          </Button>
                        ) : null}
                      </span>
                    ) : !text && canEdit && writing !== id ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setEditing(null);
                          setWriting(id);
                        }}
                      >
                        {c.add}
                      </Button>
                    ) : null}
                  </div>
                  {text && editing !== id ? <p className="line-clamp-2 whitespace-pre-line text-[13px] leading-relaxed text-muted-foreground">{text}</p> : null}
                  {writing === id ? box(id) : null}
                  {editing === id ? (
                    <div className={cn("space-y-2", THEME_TOKENS.motion.fadeIn)}>
                      <textarea
                        autoFocus
                        rows={id === "product" || id === "company" ? 6 : 4}
                        value={draft}
                        maxLength={id === "product" ? PRODUCT_MAX : 4000}
                        aria-label={labels[`area_${id}`]}
                        onChange={(event) => setDraft(event.target.value)}
                        className={field}
                      />
                      {problem ? (
                        <p className="text-sm text-destructive" role="alert">
                          {c.saveFailed}
                        </p>
                      ) : null}
                      <div className="flex justify-end gap-2">
                        <Button type="button" variant="quiet" size="sm" disabled={saving} onClick={() => setEditing(null)}>
                          {c.cancel}
                        </Button>
                        <Button type="button" size="sm" disabled={saving} onClick={() => void saveEdit(id)}>
                          {saving ? <VocifySpinner size={12} tone="onFill" /> : null}
                          {saving ? c.saving : c.save}
                        </Button>
                      </div>
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </WindowShell>
  );
}
