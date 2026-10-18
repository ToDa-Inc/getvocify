import { useState } from "react";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmAction } from "@/components/ui/confirm-action";
import { Skeleton } from "@/components/ui/skeleton";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { useSalesProcess } from "@/features/sales-process/useSalesProcess";
import { useLanguage } from "@/lib/i18n";
import { canSave, moveItem, suggestedProcess, type DraftType, type Stage } from "@/lib/sales-process";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card}`;
const field = cn(
  THEME_TOKENS.radius.control,
  "block w-full border border-border bg-background px-3 py-2 text-[15px] text-foreground placeholder:text-muted-foreground/70 focus:outline-none focus:ring-1 focus:ring-beige/40",
);

export type SalesProcessEditorViewProps = {
  status: "loading" | "ready" | "error" | "not_activated";
  /** First time: nothing defined yet. The title asks the question and the button says "Continuar". */
  first: boolean;
  /** The sales funnel (objective and description required) or the calls outside it (neither needed). */
  kind?: "funnel" | "other";
  /** Without its own heading: the window around it already has one. */
  bare?: boolean;
  list: DraftType[];
  saving: boolean;
  /** The code of the last failure, for the screen to word. */
  problem: string | null;
  onChange: (list: DraftType[]) => void;
  onSave: () => void;
  onCancel?: () => void;
  onRetry: () => void;
};

function StageToggle({ value, onChange, disabled }: { value: Stage; onChange: (stage: Stage) => void; disabled: boolean }) {
  const { t } = useLanguage();
  const c = t.product.pb2.process;
  const options: { value: Stage; label: string }[] = [
    { value: "first_contact", label: c.stageFirst },
    { value: "deal", label: c.stageDeal },
  ];
  return (
    <div className="space-y-1.5">
      <p className={THEME_TOKENS.typography.fieldLabel}>{c.stageLabel}</p>
      <div role="radiogroup" aria-label={c.stageLabel} className="flex flex-wrap gap-2">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={value === option.value}
            disabled={disabled}
            onClick={() => onChange(option.value)}
            className={cn(
              "rounded-full border px-3.5 py-1.5 text-[13px] transition-colors duration-150 motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              value === option.value ? "border-beige/40 bg-beige/10 text-foreground" : "border-border text-muted-foreground hover:text-foreground",
            )}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

/**
 * "Tu proceso de venta": the company's own interaction types as one ordered list. Each row is a name, what it aims for (get a
 * meeting, or move the deal forward) and, if wanted, how to recognise it. Add, rename, reorder and remove freely; one save
 * sends the whole list. A company with nothing defined is asked the one question and can start from a suggestion.
 */
export function SalesProcessEditorView(props: SalesProcessEditorViewProps) {
  const { status, first, list, saving, problem, onChange, onSave, onCancel, onRetry, kind = "funnel", bare = false } = props;
  const funnel = kind === "funnel";
  const { t } = useLanguage();
  const c = t.product.pb2.process;
  const update = (index: number, patch: Partial<DraftType>) => onChange(list.map((item, at) => (at === index ? { ...item, ...patch } : item)));
  const suggestion = suggestedProcess(c.suggestNames.split("|"));
  const ok = canSave(list);

  let body;
  if (status === "loading") {
    body = (
      <div className={cn(card, "space-y-4 p-6")} role="status" aria-busy="true">
        <Skeleton className="h-11 w-full motion-reduce:animate-none" />
        <Skeleton className="h-11 w-full motion-reduce:animate-none" />
      </div>
    );
  } else if (status === "not_activated") {
    body = <p className={cn(card, "p-6", THEME_TOKENS.typography.body)}>{c.errors.not_activated}</p>;
  } else if (status === "error") {
    body = (
      <div className={cn(card, "flex flex-wrap items-center gap-4 p-6")} role="alert">
        <p className={THEME_TOKENS.typography.body}>{t.product.pb2.improve.loadFailed}</p>
        <Button type="button" variant="outline" size="sm" onClick={onRetry}>
          {t.product.pb2.improve.retry}
        </Button>
      </div>
    );
  } else {
    body = (
      <div className="space-y-6">
        {!list.length && funnel ? (
          <div className={cn("space-y-3 border border-dashed border-border p-5", THEME_TOKENS.radius.card)}>
            <p className="text-sm text-foreground">{c.suggest}</p>
            <div className="flex flex-wrap items-center gap-2">
              {suggestion.map((item, index) => (
                <span key={item.label} className="flex items-center gap-2 text-[13px] text-muted-foreground">
                  {index ? <span aria-hidden>→</span> : null}
                  <span className="rounded-full bg-secondary px-3 py-1 text-foreground/80">{item.label}</span>
                </span>
              ))}
            </div>
            <Button type="button" variant="outline" size="sm" onClick={() => onChange(suggestion)}>
              {c.suggestUse}
            </Button>
          </div>
        ) : null}
        <ol className={bare ? "space-y-6" : "space-y-4"}>
          {list.map((item, index) => (
            <li key={item.key ?? `new-${index}`} className={cn(bare ? "border-b border-border/50 pb-6" : cn(card, "p-5"), THEME_TOKENS.motion.fadeIn)}>
              <div className="flex items-start gap-4">
                <span className="mt-2.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-secondary text-xs tabular-nums text-muted-foreground" aria-hidden>
                  {index + 1}
                </span>
                <div className="min-w-0 flex-1 space-y-4">
                  <input
                    value={item.label}
                    maxLength={60}
                    disabled={saving}
                    placeholder={funnel ? c.namePlaceholder : c.otherName}
                    aria-label={funnel ? c.namePlaceholder : c.otherName}
                    className={cn(field, "h-11 text-base")}
                    onChange={(event) => update(index, { label: event.target.value })}
                  />
                  {funnel ? (
                    <div className="space-y-1.5">
                      <p className={THEME_TOKENS.typography.fieldLabel}>{c.goalLabel}</p>
                      <input
                        value={item.goal ?? ""}
                        maxLength={160}
                        disabled={saving}
                        placeholder={c.goalPlaceholder}
                        aria-label={c.goalLabel}
                        className={field}
                        onChange={(event) => update(index, { goal: event.target.value })}
                      />
                    </div>
                  ) : null}
                  <div className="space-y-1.5">
                    <p className={THEME_TOKENS.typography.fieldLabel}>{c.descLabel}</p>
                    <input
                      value={item.recognize ?? ""}
                      maxLength={300}
                      disabled={saving}
                      placeholder={funnel ? c.descPlaceholder : c.otherDescPlaceholder}
                      aria-label={c.descLabel}
                      className={field}
                      onChange={(event) => update(index, { recognize: event.target.value })}
                    />
                  </div>
                  {funnel ? <StageToggle value={item.stage} disabled={saving} onChange={(stage) => update(index, { stage })} /> : null}
                </div>
                <div className="-mr-1.5 flex shrink-0 items-center">
                  <Button type="button" variant="quiet" size="icon" aria-label={c.moveUp} disabled={saving || index === 0} onClick={() => onChange(moveItem(list, index, -1))}>
                    <ArrowUp aria-hidden strokeWidth={1.5} />
                  </Button>
                  <Button type="button" variant="quiet" size="icon" aria-label={c.moveDown} disabled={saving || index === list.length - 1} onClick={() => onChange(moveItem(list, index, 1))}>
                    <ArrowDown aria-hidden strokeWidth={1.5} />
                  </Button>
                  <Button type="button" variant="quiet" size="icon" aria-label={c.remove} disabled={saving} onClick={() => onChange(list.filter((_, at) => at !== index))}>
                    <Trash2 aria-hidden strokeWidth={1.5} />
                  </Button>
                </div>
              </div>
            </li>
          ))}
        </ol>
        <div>
          <Button type="button" variant="outline" disabled={saving || list.length >= 20} onClick={() => onChange([...list, { label: "", stage: funnel ? (list.length ? "deal" : "first_contact") : "other" }])}>
            <Plus aria-hidden strokeWidth={1.5} />
            {c.add}
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-4 border-t border-border/50 pt-6">
          <Button type="button" size="lg" disabled={!ok || saving} onClick={onSave}>
            {saving ? <VocifySpinner size={12} tone="onFill" /> : null}
            {saving ? c.saving : first ? c.saveFirst : c.save}
          </Button>
          {onCancel && !first ? (
            <Button type="button" variant="quiet" size="text" disabled={saving} onClick={onCancel}>
              {t.product.cancelAction}
            </Button>
          ) : null}
          {!ok ? <span className="text-[13px] text-muted-foreground">{list.length === 0 ? c.emptyHint : c.needBoth}</span> : null}
        </div>
        {problem ? (
          <p className="text-sm text-destructive" role="alert">
            {c.errors[problem] ?? c.errors.unknown}
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <div className={cn("w-full space-y-8", bare ? "" : "max-w-3xl py-2")}>
      {bare ? null : (
        <header className="space-y-2">
          <h2 className={THEME_TOKENS.typography.panelTitle}>{first ? c.firstTitle : c.editTitle}</h2>
          <p className="max-w-xl text-[15px] leading-relaxed text-muted-foreground">{first ? c.firstLead : c.editLead}</p>
        </header>
      )}
      {body}
    </div>
  );
}

/** The editor wired to the API. Removing a type that already has steps written asks first. */
export function SalesProcessEditor({ first, onSaved, onCancel, kind = "funnel", bare = false }: { first: boolean; onSaved: () => void; onCancel?: () => void; kind?: "funnel" | "other"; bare?: boolean }) {
  const { t } = useLanguage();
  const c = t.product.pb2.process;
  const process = useSalesProcess({ onSaved: () => onSaved(), scope: kind });
  const [confirm, setConfirm] = useState(false);
  return (
    <>
      <SalesProcessEditorView
        status={process.status}
        first={first}
        kind={kind}
        bare={bare}
        list={process.list}
        saving={process.saving}
        problem={process.problem}
        onChange={process.setList}
        onSave={() => (process.removing.length ? setConfirm(true) : void process.save())}
        onCancel={onCancel}
        onRetry={process.reload}
      />
      <ConfirmAction
        open={confirm}
        onOpenChange={setConfirm}
        title={c.removeTitle.replace("{names}", process.removing.join(", "))}
        description={c.removeConfirm}
        confirmLabel={c.removeAction}
        cancelLabel={t.product.cancelAction}
        tone="danger"
        pending={process.saving}
        onConfirm={() => void process.save().then(() => setConfirm(false))}
      />
    </>
  );
}
