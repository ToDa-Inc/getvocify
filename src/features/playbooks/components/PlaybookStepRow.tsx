import { useState } from "react";
import { ArrowDown, ArrowUp, Plus, Trash } from "@phosphor-icons/react";
import { IconAction } from "@/components/ui/icon-action";
import { InlineTextarea } from "@/features/playbooks/components/InlineField";
import { useLanguage } from "@/lib/i18n";
import { needsCriterion, validationToShow } from "@/lib/playbook-doc";
import { MAX_LABEL, type EditorStep } from "@/lib/playbook-editor";
import { cn } from "@/lib/utils";

/**
 * One grid for reading and editing, so nothing moves when Edit is pressed. Desktop:
 * number · name · "counts as done" · controls. Phone: number · name · controls, and the
 * description full width underneath.
 */
const row =
  "group grid grid-cols-[1.25rem_minmax(0,1fr)_auto] items-start gap-x-3 gap-y-0.5 border-t border-border/40 first:border-t-0 " +
  "md:grid-cols-[1.25rem_minmax(0,13rem)_minmax(0,1fr)_auto] md:gap-x-4";
const cell = {
  number: "col-start-1 row-start-1 text-sm tabular-nums text-muted-foreground",
  name: "col-start-2 row-start-1 min-w-0",
  aside: "col-start-3 row-start-1 flex items-start md:col-start-4",
  detail: "col-start-2 col-span-2 row-start-2 min-w-0 md:col-start-3 md:col-span-1 md:row-start-1",
  message: "col-start-2 col-span-2 md:col-span-2",
};

export function PlaybookStepRow({
  step,
  index,
  total,
  editable,
  touched,
  forced = false,
  rate,
  weakest,
  autoFocus,
  onChange,
  onBlur,
  onMove,
  onRemove,
}: {
  step: EditorStep;
  index: number;
  total: number;
  editable: boolean;
  touched: boolean;
  /** A publish was blocked: every problem shows, an empty name included. */
  forced?: boolean;
  /** Percent of calls where the step is met, or null while there is not enough data. */
  rate: number | null;
  weakest: boolean;
  autoFocus?: boolean;
  onChange: (patch: Partial<EditorStep>) => void;
  onBlur: () => void;
  onMove: (delta: -1 | 1) => void;
  onRemove: () => void;
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const errors = t.product.playbookEditorErrors as Record<string, string>;
  const [exampleOpen, setExampleOpen] = useState(false);
  const error = validationToShow(step, touched, forced);
  const showExample = Boolean(step.example) || exampleOpen;
  // Vocify leaves "counts as done" empty when it only found an attitude: say so on review,
  // without waiting for a touch. A criterion that just repeats the name waits for one.
  const hint =
    editable && !error && step.label.trim() && needsCriterion(step) && (touched || !step.criterion.trim());

  if (!editable) {
    return (
      <li className={cn(row, "py-3")}>
        <span className={cn(cell.number, "pt-px")}>{index + 1}</span>
        <p className={cn(cell.name, "text-[15px] text-foreground")}>{step.label}</p>
        <div className={cn(cell.detail, "space-y-1")}>
          {step.criterion && step.criterion !== step.label ? (
            <p className="text-sm leading-relaxed text-muted-foreground">{step.criterion}</p>
          ) : null}
          {step.example ? <p className="text-sm italic text-muted-foreground">«{step.example}»</p> : null}
        </div>
        <div className={cell.aside}>
          {rate !== null ? (
            <span
              className={cn("pt-px text-sm tabular-nums", weakest ? "text-warning" : "text-muted-foreground")}
              title={copy.stepRate.replace("{rate}", `${rate} %`)}
            >
              {rate} %
            </span>
          ) : null}
        </div>
      </li>
    );
  }

  return (
    <li className={cn(row, "py-2")}>
      <span className={cn(cell.number, "pt-1.5")}>{index + 1}</span>
      {/* Wraps instead of cutting a long name; Enter doesn't break the line. */}
      <InlineTextarea
        className={cn(cell.name, "text-[15px]")}
        value={step.label}
        maxLength={MAX_LABEL + 20}
        placeholder={copy.stepName}
        aria-label={copy.stepName}
        aria-invalid={error === "empty_label" || error === "label_too_long"}
        autoFocus={autoFocus}
        onKeyDown={(event) => {
          if (event.key === "Enter") event.preventDefault();
        }}
        onChange={(event) => onChange({ label: event.target.value.replace(/\n/g, " ") })}
        onBlur={onBlur}
      />
      <div className={cn(cell.detail, "space-y-0.5")}>
        <InlineTextarea
          className="text-sm text-muted-foreground focus:text-foreground"
          value={step.criterion === step.label ? "" : step.criterion}
          placeholder={copy.criterion}
          aria-label={copy.criterion}
          aria-invalid={error === "criterion_too_long"}
          onChange={(event) => onChange({ criterion: event.target.value })}
          onBlur={onBlur}
        />
        {showExample ? (
          <InlineTextarea
            className="text-sm italic text-muted-foreground focus:text-foreground"
            value={step.example ?? ""}
            placeholder={copy.example}
            aria-label={copy.example}
            autoFocus={exampleOpen && !step.example}
            onChange={(event) => onChange({ example: event.target.value })}
            onBlur={() => {
              if (!step.example?.trim()) setExampleOpen(false);
              onBlur();
            }}
          />
        ) : null}
      </div>
      <div
        className={cn(
          cell.aside,
          // Phone: only on the step being edited, so the text keeps the width. Desktop: on hover.
          "-mr-2 hidden transition-opacity group-focus-within:flex md:flex md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100",
        )}
      >
        {!showExample ? (
          <button
            type="button"
            className="mt-1.5 hidden items-center gap-0.5 rounded-full px-2 py-0.5 text-xs text-muted-foreground hover:bg-secondary/60 hover:text-foreground sm:inline-flex"
            onClick={() => setExampleOpen(true)}
          >
            <Plus size={10} weight="light" />
            {copy.addExample}
          </button>
        ) : null}
        <IconAction label={t.product.playbookEditorMoveUp} disabled={index === 0} onClick={() => onMove(-1)}>
          <ArrowUp size={14} weight="light" />
        </IconAction>
        <IconAction label={t.product.playbookEditorMoveDown} disabled={index === total - 1} onClick={() => onMove(1)}>
          <ArrowDown size={14} weight="light" />
        </IconAction>
        <IconAction label={t.product.playbookEditorRemove} tone="danger" onClick={onRemove}>
          <Trash size={14} weight="light" />
        </IconAction>
      </div>
      {error ? (
        <p className={cn(cell.message, "text-xs text-destructive")} role="alert">
          {errors[error]}
        </p>
      ) : null}
      {hint ? <p className={cn(cell.message, "text-xs text-muted-foreground")}>{copy.needsCriterion}</p> : null}
    </li>
  );
}
