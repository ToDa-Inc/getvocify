import { useLanguage } from "@/lib/i18n";
import { fill, type CoachCalls } from "@/lib/rep-coaching";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { CallRecord } from "./CallRecord";
import { ImproveTables } from "./ImproveTables";

function SectionHead({ id, title, meta }: { id: string; title: string; meta?: string }) {
  return (
    <div className="space-y-0.5">
      <h2 id={id} className={THEME_TOKENS.typography.sectionTitle}>{title}</h2>
      {meta ? <p className="text-[13px] text-muted-foreground">{meta}</p> : null}
    </div>
  );
}

/** Progreso: what to improve (steps and objections), then the record of the rep's calls. Only the rep
 * against their own playbook; the type is the page's dropdown, so this only reads what it is given. */
export function CoachingCalls({ data }: { data: CoachCalls }) {
  const { t } = useLanguage();
  const p = t.product;
  const weeks = data.window_weeks;
  return (
    <div className="space-y-14" data-testid="coach-calls">
      <section aria-labelledby="coach-improve" className="space-y-5 px-3">
        <SectionHead id="coach-improve" title={p.coachImproveHeading} meta={fill(p.coachImproveWindow, { weeks, count: data.conversations })} />
        {!data.conversations ? (
          <p className="text-[14.5px] text-muted-foreground">{fill(p.coachImproveNoCalls, { weeks })}</p>
        ) : data.slipped_steps && data.objections ? (
          <ImproveTables type={data.type ?? ""} steps={data.slipped_steps} objections={data.objections} />
        ) : (
          // A backend older than the tables (the web deploys before it): never say "nothing slipped".
          <p className="text-[14.5px] text-muted-foreground">{p.coachImproveUpdating}</p>
        )}
      </section>
      {data.calls.length ? (
        <section aria-labelledby="coach-calls-heading" className="space-y-2">
          <div className="px-3">
            <SectionHead id="coach-calls-heading" title={p.coachCallsHeading} meta={fill(p.coachCallsMeta, { count: data.calls.length })} />
          </div>
          <CallRecord calls={data.calls} type={data.type ?? ""} />
        </section>
      ) : null}
    </div>
  );
}
