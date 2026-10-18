import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { useAuth } from "@/features/auth";
import { authApi, authKeys } from "@/features/auth/api";
import type { User } from "@/features/auth/types";
import { playbooksApi } from "@/features/playbooks/api";
import { WindowShell } from "@/features/playbooks/components/home/WindowShell";
import { PlaybookStart, type SourceInput } from "@/features/playbooks/components/PlaybookStart";
import { areasFromKnowledge, knowledgeFromAreas, type AreaId, type Areas } from "@/lib/company-areas";
import { useLanguage } from "@/lib/i18n";
import { COMPANY_AREAS } from "@/lib/playbook-home";
import { cleanKnowledge, type Knowledge } from "@/lib/playbook-knowledge";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

type Step = "start" | "review";
const field = cn(
  THEME_TOKENS.radius.control,
  "block w-full resize-none border border-border bg-background px-3 py-2 text-[14px] leading-relaxed text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-beige/40",
);

/**
 * "Vuestra empresa" in one window. With nothing written it starts by asking for whatever the company has (web, brochure,
 * deck) and Vocify sorts it into the six areas; then, or straight away when something is there, the six areas as plain texts
 * to correct or complete. One save keeps them (the product text is the one live help already reads).
 */
export function CompanyWindow({ open, onOpenChange, canEdit }: { open: boolean; onOpenChange: (open: boolean) => void; canEdit: boolean }) {
  const { t } = useLanguage();
  const c = t.product.pb2.home;
  const labels = c as unknown as Record<string, string>;
  const { user } = useAuth();
  const client = useQueryClient();
  const [step, setStep] = useState<Step>("start");
  const [loading, setLoading] = useState(true);
  const [knowledge, setKnowledge] = useState<Knowledge>({});
  const [base, setBase] = useState<string | null>(null);
  const [areas, setAreas] = useState<Areas>(areasFromKnowledge(null, null));
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setProblem(false);
    void playbooksApi
      .company()
      .then((doc) => {
        if (cancelled) return;
        const read = areasFromKnowledge(doc.knowledge, user?.productContext);
        setKnowledge(doc.knowledge ?? {});
        setBase(doc.updated_at);
        setAreas(read);
        setStep(Object.values(read).some((value) => value.trim()) ? "review" : "start");
      })
      .catch(() => !cancelled && setStep("start"))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // The window reads what is saved each time it opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const read = async (source: SourceInput) => {
    const done = await playbooksApi.fillCompany(source, base);
    setKnowledge(done.knowledge ?? {});
    setBase(done.updated_at);
    setAreas((now) => ({ ...areasFromKnowledge(done.knowledge, now.product), product: now.product }));
    void client.invalidateQueries({ queryKey: ["playbook-company"] });
    setStep("review");
  };

  const save = async () => {
    setSaving(true);
    setProblem(false);
    try {
      const next = knowledgeFromAreas(knowledge, areas);
      await playbooksApi.saveCompany(cleanKnowledge(next.knowledge), base);
      if (next.productContext !== (user?.productContext ?? "").trim()) {
        const updated = await authApi.updateProfile({ productContext: next.productContext });
        client.setQueryData<User>(authKeys.me(), updated);
      }
      void client.invalidateQueries({ queryKey: ["playbook-company"] });
      onOpenChange(false);
    } catch {
      setProblem(true);
    } finally {
      setSaving(false);
    }
  };

  const footer =
    step === "start" ? (
      <>
        <Button type="button" variant="quiet" size="text" onClick={() => setStep("review")}>
          {c.writeMyself}
        </Button>
        <span />
      </>
    ) : (
      <>
        <Button type="button" variant="quiet" size="text" onClick={() => setStep("start")}>
          <ArrowLeft aria-hidden strokeWidth={1.5} />
          {c.backStep}
        </Button>
        {canEdit ? (
          <Button type="button" disabled={saving} onClick={() => void save()}>
            {saving ? <VocifySpinner size={12} tone="onFill" /> : null}
            {saving ? c.saving : c.save}
          </Button>
        ) : null}
      </>
    );

  return (
    <WindowShell open={open} onOpenChange={onOpenChange} title={c.companyTitle} lead={step === "start" ? c.companyStart : c.companyReview} footer={loading ? undefined : footer}>
      {loading ? (
        <div className="space-y-3" role="status" aria-busy="true">
          <Skeleton className="h-24 w-full motion-reduce:animate-none" />
          <Skeleton className="h-24 w-full motion-reduce:animate-none" />
        </div>
      ) : step === "start" ? (
        <PlaybookStart minHeight="min-h-[180px]" placeholder={c.companyPh} readingLabel={c.reading}
        submitLabel={c.read} submit={read} />
      ) : (
        <div className="space-y-5">
          {COMPANY_AREAS.map((area) => (
            <label key={area.id} className="block space-y-1.5">
              <span className="flex flex-wrap items-baseline gap-x-2">
                <span className="text-[14px] font-medium text-foreground">{labels[`area_${area.id}`]}</span>
                <span className="text-[12px] text-muted-foreground">{labels[`hint_${area.id}`]}</span>
              </span>
              <textarea
                rows={area.id === "product" || area.id === "company" ? 3 : 2}
                value={areas[area.id as AreaId]}
                readOnly={!canEdit}
                maxLength={area.id === "product" ? 8000 : 4000}
                placeholder={c.emptyArea}
                onChange={(event) => setAreas({ ...areas, [area.id]: event.target.value })}
                className={field}
              />
            </label>
          ))}
          {problem ? (
            <p className="text-sm text-destructive" role="alert">
              {c.saveFailed}
            </p>
          ) : null}
        </div>
      )}
    </WindowShell>
  );
}
