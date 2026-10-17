import type { Intake } from "@/features/playbooks/hooks/useIntake";
import { PlaybookStart } from "@/features/playbooks/components/PlaybookStart";
import { Button } from "@/components/ui/button";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

/**
 * "Dale a Vocify vuestro playbook": the one box for the whole company. On an empty page it is
 * the page; later it opens from "Añadir desde un documento". When Vocify can't split the
 * document, it asks which call it is for.
 */
export function IntakePanel({
  intake,
  alone,
  name,
  onTemplate,
  assistant = false,
}: {
  intake: Intake;
  /** Nothing created yet: the box is the whole section (no cancel, template link below). */
  alone: boolean;
  name: (key: string) => string;
  onTemplate: () => void;
  /** The playbook assistant is on: several files at once and the sales script first. */
  assistant?: boolean;
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const c = copy.improve;
  return (
    <div className={cn("space-y-4", alone && "py-6", THEME_TOKENS.motion.fadeIn)}>
      <div className="space-y-1">
        <h3 className={THEME_TOKENS.typography.sectionTitle}>{copy.intakeTitle}</h3>
        <p className="text-sm text-muted-foreground">{assistant ? c.intakeScriptHint : copy.intakeHint}</p>
      </div>
      <PlaybookStart
        submit={intake.submit}
        minHeight="min-h-[320px]"
        placeholder={copy.intakePlaceholder}
        readingLabel={copy.intakeReading}
        onTemplate={alone ? onTemplate : undefined}
        onCancel={alone ? undefined : intake.close}
        multiple={assistant}
        submitMany={assistant ? intake.submitMany : undefined}
        manyReadingLabel={c.reading}
      />
      {intake.failedFiles.length ? (
        <ul className="space-y-1" role="alert">
          {intake.failedFiles.map((file) => (
            <li key={file.name} className="text-[13px] text-destructive">
              {c.fileFailed.replace("{name}", file.name)} {(file.code && copy.readErrors[file.code]) || ""}
            </li>
          ))}
        </ul>
      ) : null}
      {intake.notice ? (
        <p className="text-sm text-destructive" role="alert">
          {intake.notice}
        </p>
      ) : null}
      {intake.fallback ? (
        <div className={cn("space-y-2", THEME_TOKENS.motion.fadeIn)}>
          <p className="text-sm text-foreground">{copy.fallbackAsk}</p>
          <div className="flex flex-wrap gap-2">
            {intake.fallback.candidates.map((candidate) => (
              <Button
                key={candidate.key}
                type="button"
                variant="outline"
                size="sm"
                disabled={intake.picking !== null}
                onClick={() => void intake.pick(candidate.key)}
              >
                {intake.picking === candidate.key ? <VocifySpinner size={12} /> : null}
                <span className={intake.picking === candidate.key ? "ml-1.5" : undefined}>{name(candidate.key)}</span>
              </Button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
