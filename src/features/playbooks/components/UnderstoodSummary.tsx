import { Button } from "@/components/ui/button";
import { useLanguage } from "@/lib/i18n";
import type { IntakeSummary } from "@/lib/playbook-assistant";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card}`;

export type FailedFile = { name: string; code: string | null };

function count(template: { one: string; many: string }, n: number) {
  return n === 1 ? template.one : template.many.replace("{count}", String(n));
}

/**
 * "Esto es lo que he entendido": what the documents left in the playbook, in a few numbers, with the files Vocify could
 * not read named, and ONE next step (the guided questions) beside a quiet "Más tarde". Everything stays a draft.
 */
export function UnderstoodSummary({
  summary,
  failed,
  conflicts,
  readError,
  onNext,
  onLater,
}: {
  summary: IntakeSummary;
  failed: FailedFile[];
  conflicts: boolean;
  /** The words for a file that could not be read, by its code. */
  readError: (code: string | null) => string;
  onNext: () => void;
  onLater: () => void;
}) {
  const { t } = useLanguage();
  const c = t.product.pb2.improve;
  const parts = [
    summary.types ? count({ one: c.understoodTypesOne, many: c.understoodTypesMany }, summary.types) : null,
    summary.steps ? count({ one: c.understoodStepsOne, many: c.understoodStepsMany }, summary.steps) : null,
    summary.objections ? count({ one: c.understoodObjectionsOne, many: c.understoodObjectionsMany }, summary.objections) : null,
    summary.questions ? count({ one: c.understoodQuestionsOne, many: c.understoodQuestionsMany }, summary.questions) : null,
    summary.proofs ? count({ one: c.understoodProofsOne, many: c.understoodProofsMany }, summary.proofs) : null,
  ].filter((part): part is string => Boolean(part));
  return (
    <section className={cn(card, "space-y-4 p-5 md:p-6", THEME_TOKENS.motion.fadeIn)} aria-labelledby="understood-title" role="status">
      <h3 id="understood-title" className={THEME_TOKENS.typography.panelTitle}>
        {c.understoodTitle}
      </h3>
      {parts.length ? (
        <ul className="flex flex-wrap gap-2">
          {parts.map((part) => (
            <li key={part} className={cn(THEME_TOKENS.radius.pill, "bg-secondary/60 px-3 py-1 text-[13px] text-foreground")}>
              {part}
            </li>
          ))}
        </ul>
      ) : (
        <p className={THEME_TOKENS.typography.body}>{c.understoodNone}</p>
      )}
      <p className="text-[13px] text-muted-foreground">{c.understoodDraft}</p>
      {conflicts ? (
        <p className="flex items-start gap-2 text-[13px] text-foreground">
          <span className="mt-[6px] h-1.5 w-1.5 shrink-0 rounded-full bg-warning" aria-hidden />
          {c.understoodConflicts}
        </p>
      ) : null}
      {failed.length ? (
        <ul className="space-y-1" role="alert">
          {failed.map((file) => (
            <li key={file.name} className="text-[13px] text-destructive">
              {c.fileFailed.replace("{name}", file.name)} {readError(file.code)}
            </li>
          ))}
        </ul>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" onClick={onNext}>
          {c.understoodNext}
        </Button>
        <Button type="button" variant="quiet" size="text" onClick={onLater}>
          {c.understoodLater}
        </Button>
      </div>
    </section>
  );
}
