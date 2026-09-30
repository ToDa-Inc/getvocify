import { CompleteButton, DocRow, ItemMenu, NumberMark, type MenuAction } from "@/features/playbooks/components/DocParts";
import { InlineTextarea } from "@/features/playbooks/components/InlineField";
import { itemBody, itemTitle } from "@/features/playbooks/styles";
import { useLanguage } from "@/lib/i18n";
import { needsCriterion, validationToShow } from "@/lib/playbook-doc";
import { MAX_LABEL, type EditorStep } from "@/lib/playbook-editor";
import { cn } from "@/lib/utils";

/**
 * One step: its number, its name in bold and one line with what counts as done, both edited
 * where they are read. When that line is missing it can be typed, or Vocify writes it ("Completar"). Moving and
 * removing live in the step's "···". A line the rep can say, when the step has one, reads as a
 * quote under it.
 */
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
  completing,
  busy,
  onComplete,
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
  /** Vocify is writing this step's line. */
  completing?: boolean;
  /** Vocify is writing something else: this step's button waits. */
  busy?: boolean;
  onComplete?: () => void;
  onChange: (patch: Partial<EditorStep>) => void;
  onBlur: () => void;
  onMove: (delta: -1 | 1) => void;
  onRemove: () => void;
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const errors = t.product.playbookEditorErrors as Record<string, string>;
  const error = validationToShow(step, touched, forced);
  const missing = Boolean(step.label.trim()) && needsCriterion(step);

  const actions: MenuAction[] = [
    ...(index > 0 ? [{ label: t.product.playbookEditorMoveUp, onSelect: () => onMove(-1) }] : []),
    ...(index < total - 1 ? [{ label: t.product.playbookEditorMoveDown, onSelect: () => onMove(1) }] : []),
    { label: t.product.playbookEditorRemove, onSelect: onRemove, danger: true },
  ];

  return (
    <DocRow
      lead={<NumberMark n={index + 1} />}
      title={
        editable ? (
          // Wraps instead of cutting a long name; Enter doesn't break the line.
          <InlineTextarea
            className={itemTitle}
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
        ) : (
          <p className={itemTitle}>{step.label}</p>
        )
      }
      side={
        <>
          {rate !== null ? (
            <span
              className={cn("text-xs tabular-nums", weakest ? "font-semibold text-warning" : "text-muted-foreground")}
              title={copy.stepRate.replace("{rate}", `${rate} %`)}
            >
              {rate} %
            </span>
          ) : null}
          {editable ? <ItemMenu label={copy.itemMenu.replace("{name}", step.label || String(index + 1))} actions={actions} /> : null}
        </>
      }
    >
      {editable ? (
        <InlineTextarea
          className={itemBody}
          value={step.criterion === step.label ? "" : step.criterion}
          placeholder={copy.criterion}
          aria-label={copy.criterion}
          aria-invalid={error === "criterion_too_long"}
          onChange={(event) => onChange({ criterion: event.target.value })}
          onBlur={onBlur}
        />
      ) : step.criterion && step.criterion !== step.label ? (
        <p className={itemBody}>{step.criterion}</p>
      ) : null}
      {editable && missing && onComplete ? (
        <div className="pt-1">
          <CompleteButton label={copy.complete} pending={completing} disabled={busy} onClick={onComplete} />
        </div>
      ) : null}
      {step.example ? <p className={cn(itemBody, "mt-1 border-l-2 border-beige/60 pl-3 italic")}>{step.example}</p> : null}
      {error ? (
        <p className="pt-0.5 text-xs text-destructive" role="alert">
          {errors[error]}
        </p>
      ) : null}
    </DocRow>
  );
}
