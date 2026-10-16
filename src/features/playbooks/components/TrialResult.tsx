import { Button } from "@/components/ui/button";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import type { Trial } from "@/features/playbooks/assistantApi";
import { SavedBubble } from "@/features/playbooks/components/Bubbles";
import { SegmentMeter, type SegmentTone } from "@/features/playbooks/components/SegmentMeter";
import type { Activation } from "@/features/playbooks/hooks/useTrial";
import { useLanguage } from "@/lib/i18n";
import { rateLabel, trialMeter } from "@/lib/playbook-assistant";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card}`;
const MARK_TONE: Record<string, SegmentTone> = { approved: "success", corrected: "warning", unknown: "muted", pending: "pending" };

/**
 * How the trial went, in plain words: "9 de 12 aprobadas sin cambiar" (a percentage only from three cases on), the topics
 * to strengthen, and ONE main button to turn it on for the team. Below 80% it warns once and still lets the Head of
 * Sales activate: it is their company. Activating publishes the drafts the trial changed.
 */
export function TrialResultView({
  trial,
  weakTopics,
  activation,
  problem,
  onActivate,
  onAgain,
  onResume,
  onBack,
}: {
  trial: Trial;
  /** The weak topics already named in the person's language. */
  weakTopics: string[];
  activation: Activation;
  problem: string | null;
  onActivate: () => void;
  onAgain: () => void;
  /** Back to the cases still undecided; null when there are none. */
  onResume: (() => void) | null;
  onBack: () => void;
}) {
  const { t } = useLanguage();
  const c = t.product.pb2.improve;
  const { result } = trial;
  const rate = rateLabel(result.approved, result.total, { of: c.of });
  const verdicts = trial.cases.map((item) => item.verdict ?? "").filter(Boolean);
  const done = activation.state === "done";
  const names = (keys: string[]) => keys.join(", ");
  return (
    <div className="mx-auto w-full max-w-2xl space-y-5">
      <header className="space-y-0.5">
        <h2 className={THEME_TOKENS.typography.panelTitle}>{c.trialTitle}</h2>
      </header>
      {done ? (
        <SavedBubble title={c.savedTitle}>
          {activation.failed.length ? c.activateFailed.replace("{names}", names(activation.failed)) : c.activated}
        </SavedBubble>
      ) : null}
      <section className={cn(card, "space-y-5 p-5 md:p-6", THEME_TOKENS.motion.fadeIn)} aria-labelledby="trial-result">
        <div className="space-y-2">
          <h3 id="trial-result" className="text-[26px] font-medium leading-tight tracking-tight text-foreground">
            {c.resultLine.replace("{good}", String(result.approved)).replace("{total}", String(result.total))}
          </h3>
          <div className="flex items-center gap-3">
            <SegmentMeter className="w-48" segments={trialMeter(verdicts, trial.total).map((mark) => MARK_TONE[mark])} label={rate.text} />
            {rate.kind === "rate" ? (
              <span className={cn(THEME_TOKENS.radius.pill, "bg-secondary px-2.5 py-0.5 text-sm tabular-nums text-foreground")}>{rate.text}</span>
            ) : null}
          </div>
          <p className={cn("text-[14.5px] leading-relaxed", result.warn ? "text-warning" : "text-muted-foreground")}>
            {result.percent === null ? c.resultFew : result.warn ? c.resultWarn : c.resultGood}
          </p>
        </div>
        {weakTopics.length ? (
          <div className="space-y-2">
            <h4 className={THEME_TOKENS.typography.groupTitle}>{c.resultWeak}</h4>
            <ul className="space-y-1">
              {weakTopics.map((topic) => (
                <li key={topic} className="flex items-center gap-2.5 text-[14.5px] text-foreground">
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-warning" aria-hidden />
                  {topic}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {problem ? (
          <p className="text-sm text-destructive" role="alert">
            {problem}
          </p>
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          {done ? (
            <Button type="button" onClick={onBack}>
              {c.doneBack}
            </Button>
          ) : (
            <Button type="button" disabled={activation.state === "working" || result.total === 0} onClick={onActivate}>
              {activation.state === "working" ? <VocifySpinner size={12} tone="onFill" /> : null}
              {activation.state === "working" ? c.activating : c.activate}
            </Button>
          )}
          <Button type="button" variant="outline" disabled={activation.state === "working"} onClick={onAgain}>
            {c.again}
          </Button>
          {onResume && !done ? (
            <Button type="button" variant="quiet" size="text" onClick={onResume}>
              {c.trialResume}
            </Button>
          ) : null}
        </div>
      </section>
    </div>
  );
}
