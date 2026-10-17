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
    <div role="radiogroup" aria-label={c.stageLabel} className="flex flex-wrap gap-1.5">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          disabled={disabled}
          onClick={() => onChange(option.value)}
          className={cn(
            "rounded-full border px-3 py-1 text-xs transition-colors duration-150 motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            value === option.value ? "border-beige/40 bg-beige/10 text-foreground" : "border-border text-muted-foreground hover:text-foreground",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

/**
 * "Tu proceso de venta": the company's own interaction types as one ordered list. Each row is a name, what it aims for (get a
 * meeting, or move the deal forward) and, if wanted, how to recognise it. Add, rename, reorder and remove freely; one save
 * sends the whole list. A company with nothing defined is asked the one question and can start from a suggestion.
 */
export function SalesProcessEditorView(props: SalesProcessEditorViewProps) {
  const { status, first, list, saving, problem, onChange, onSave, onCancel, onRetry } = props;
  const { t } = useLanguage();
  const c = t.product.pb2.process;
  const [open, setOpen] = useState<Set<number>>(new Set());
  const update = (index: number, patch: Partial<DraftType>) => onChange(list.map((item, at) => (at === index ? { ...item, ...patch } : item)));
  const suggestion = suggestedProcess(c.suggestNames.split("|"));
  const ok = canSave(list);

  let body;
  if (status === "loading") {
    body = (
      <div className={cn(card, "space-y-3 p-6")} role="status" aria-busy="true">
        <Skeleton className="h-10 w-full motion-reduce:animate-none" />
        <Skeleton className="h-10 w-full motion-reduce:animate-none" />
      </div>
    );
  } else if (status === "not_activated") {
    body = <p className={cn(card, "p-5", THEME_TOKENS.typography.body)}>{c.errors.not_activated}</p>;
  } else if (status === "error") {
    body = (
      <div className={cn(card, "flex flex-wrap items-center gap-3 p-5")} role="alert">
        <p className={THEME_TOKENS.typography.body}>{t.product.pb2.improve.loadFailed}</p>
        <Button type="button" variant="outline" size="sm" onClick={onRetry}>
          {t.product.pb2.improve.retry}
        </Button>
      </div>
    );
  } else {
    body = (
      <div className="space-y-4">
        {!list.length ? (
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => onChange(suggestion)}>
              {c.suggest}
            </Button>
            <span className="text-xs text-muted-foreground">{suggestion.map((item) => item.label).join(" → ")}</span>
          </div>
        ) : null}
        <ol className="space-y-3">
          {list.map((item, index) => (
            <li key={item.key ?? `new-${index}`} className={cn(card, "space-y-3 p-4", THEME_TOKENS.motion.fadeIn)}>
              <div className="flex items-center gap-3">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-secondary text-xs tabular-nums text-muted-foreground" aria-hidden>
                  {index + 1}
                </span>
                <input
                  value={item.label}
                  maxLength={60}
                  disabled={saving}
                  placeholder={c.namePlaceholder}
                  aria-label={c.namePlaceholder}
                  className={field}
                  onChange={(event) => update(index, { label: event.target.value })}
                />
                <div className="flex shrink-0 items-center">
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
              <div className="space-y-2 pl-10">
                <StageToggle value={item.stage} disabled={saving} onChange={(stage) => update(index, { stage })} />
                {open.has(index) || item.recognize ? (
                  <input
                    value={item.recognize ?? ""}
                    maxLength={300}
                    disabled={saving}
                    placeholder={c.recognizePlaceholder}
                    aria-label={c.recognizeAdd}
                    className={field}
                    onChange={(event) => update(index, { recognize: event.target.value })}
                  />
                ) : (
                  <Button type="button" variant="quiet" size="text" className="text-xs" onClick={() => setOpen(new Set(open).add(index))}>
                    {c.recognizeAdd}
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ol>
        <Button type="button" variant="outline" size="sm" disabled={saving || list.length >= 20} onClick={() => onChange([...list, { label: "", stage: list.length ? "deal" : "first_contact" }])}>
          <Plus aria-hidden strokeWidth={1.5} />
          {c.add}
        </Button>
        <div className="flex flex-wrap items-center gap-3 pt-1">
          <Button type="button" disabled={!ok || saving} onClick={onSave}>
            {saving ? <VocifySpinner size={12} tone="onFill" /> : null}
            {saving ? c.saving : first ? c.saveFirst : c.save}
          </Button>
          {onCancel && !first ? (
            <Button type="button" variant="quiet" size="text" disabled={saving} onClick={onCancel}>
              {t.product.cancelAction}
            </Button>
          ) : null}
          {!ok && list.length === 0 ? <span className="text-xs text-muted-foreground">{c.emptyHint}</span> : null}
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
    <div className="mx-auto w-full max-w-2xl space-y-5">
      <header className="space-y-1">
        <h2 className={THEME_TOKENS.typography.panelTitle}>{first ? c.firstTitle : c.editTitle}</h2>
        <p className="max-w-lg text-[13px] leading-snug text-muted-foreground">{first ? c.firstLead : c.editLead}</p>
      </header>
      {body}
    </div>
  );
}

/** The editor wired to the API. Removing a type that already has steps written asks first. */
export function SalesProcessEditor({ first, onSaved, onCancel }: { first: boolean; onSaved: () => void; onCancel?: () => void }) {
  const { t } = useLanguage();
  const c = t.product.pb2.process;
  const process = useSalesProcess({ onSaved: () => onSaved() });
  const [confirm, setConfirm] = useState(false);
  return (
    <>
      <SalesProcessEditorView
        status={process.status}
        first={first}
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
