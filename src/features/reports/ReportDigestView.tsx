import { useLanguage } from "@/lib/i18n";
import type { ReportActivity, ReportDigest, ReportFeedback } from "@/lib/report-snapshot";
import { THEME_TOKENS } from "@/lib/theme/tokens";

/** A report with REPORT_FEEDBACK_ENABLED: the same blocks as its email (backend digest_email.py). */

const fill = (template: string, values: Record<string, string | number>) =>
  Object.entries(values).reduce((text, [key, value]) => text.replace(`{${key}}`, String(value)), template);

const pct = (value: number | null | undefined) => (value == null ? null : `${Math.round(value * 100)} %`);

function Delta({ now, before, week }: { now: number | null; before: number | null | undefined; week: boolean }) {
  const { t } = useLanguage();
  if (now == null || !before) return null;
  const diff = now - before;
  const text =
    diff === 0
      ? week ? t.product.reportDigestSameWeek : t.product.reportDigestSameDay
      : fill(week ? t.product.reportDigestVsWeek : t.product.reportDigestVsDay, { diff: `${diff > 0 ? "+" : "−"}${Math.abs(diff)}` });
  const tone = diff > 0 ? "text-success" : diff < 0 ? "text-warning" : "text-muted-foreground";
  return <p className={`mt-1 text-[12px] ${tone}`}>{text}</p>;
}

function Card({ label, value, children }: { label: string; value: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border/70 bg-card px-4 py-3">
      <p className="text-[13px] text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl tracking-tight tabular-nums">{value}</p>
      {children}
    </div>
  );
}

function Cards({ digest, week }: { digest: ReportDigest; week: boolean }) {
  const { t } = useLanguage();
  const act: ReportActivity = digest.activity;
  const prev = digest.previous;
  const connect = pct(act.connect_rate);
  const role = digest.sales_role;
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {role !== "ae" || act.calls ? (
        <Card label={t.product.reportDigestCalls} value={String(act.calls)}>
          <Delta now={act.calls} before={prev?.calls} week={week} />
        </Card>
      ) : null}
      <Card label={t.product.reportDigestConversations} value={String(act.conversations)}>
        {connect ? <p className="mt-1 text-[12px] text-muted-foreground">{fill(t.product.reportDigestConnect, { pct: connect })}</p> : null}
        <Delta now={act.conversations} before={prev?.conversations} week={week} />
      </Card>
      {role !== "sdr" && act.meetings_held ? (
        <Card label={t.product.reportDigestMeetingsHeld} value={String(act.meetings_held)}>
          <Delta now={act.meetings_held} before={prev?.meetings_held} week={week} />
        </Card>
      ) : null}
      <Card
        label={t.product.reportDigestMeetingsBooked}
        value={act.meetings_booked == null ? t.product.reportDigestNotMarked : String(act.meetings_booked)}
      >
        <Delta now={act.meetings_booked} before={prev?.meetings_booked} week={week} />
      </Card>
      <Card label={t.product.reportDigestProcess} value={pct(digest.coaching.adherence) ?? "—"}>
        <p className="mt-1 text-[12px] text-muted-foreground">{fill(t.product.reportDigestEvaluated, { n: digest.coaching.evaluated })}</p>
      </Card>
    </div>
  );
}

function Items({ title, items, tone }: { title: string; items: string[]; tone: "good" | "warn" }) {
  if (!items.length) return null;
  const border = tone === "good" ? "border-l-success" : "border-l-warning";
  return (
    <section className="space-y-2">
      <h2 className={THEME_TOKENS.typography.sectionTitle}>{title}</h2>
      <ul className="space-y-2">
        {items.map((item) => (
          <li key={item} className={`rounded-lg border border-border/60 border-l-4 ${border} bg-card px-4 py-3 text-sm leading-relaxed`}>
            {item}
          </li>
        ))}
      </ul>
    </section>
  );
}

function Bar({ label, value, right }: { label: string; value: number | null; right: string }) {
  const width = value == null ? 0 : Math.max(2, Math.min(100, Math.round(value * 100)));
  return (
    <div className="grid grid-cols-[minmax(0,9rem)_1fr_auto] items-center gap-3 text-sm">
      <span className="truncate">{label}</span>
      <span className="h-2 rounded-full bg-muted">
        <span className="block h-2 rounded-full bg-beige" style={{ width: `${width}%` }} />
      </span>
      <span className="text-[13px] tabular-nums text-muted-foreground">{right}</span>
    </div>
  );
}

export default function ReportDigestView({
  digest,
  feedback,
  week,
  team,
}: {
  digest: ReportDigest;
  feedback: ReportFeedback | null | undefined;
  week: boolean;
  team: boolean;
}) {
  const { t } = useLanguage();
  const coach = digest.coaching;
  const types = Object.entries(coach.by_type ?? {}).sort((a, b) => b[1] - a[1]);
  const totalTypes = types.reduce((sum, [, count]) => sum + count, 0);
  const notes = new Map((feedback?.people ?? []).map((person) => [person.name.toLocaleLowerCase(), person.note]));
  return (
    <div className="space-y-6">
      {feedback?.headline ? <p className="max-w-3xl text-xl font-semibold leading-snug">{feedback.headline}</p> : null}
      <Cards digest={digest} week={week} />
      {feedback ? (
        <>
          <Items title={t.product.reportDigestWentWell} items={feedback.went_well ?? []} tone="good" />
          <Items title={t.product.reportDigestToImprove} items={feedback.to_improve ?? []} tone="warn" />
          {feedback.focus ? (
            <section className="space-y-2">
              <h2 className={THEME_TOKENS.typography.sectionTitle}>{t.product.reportDigestFocus}</h2>
              <p className="max-w-3xl rounded-xl bg-foreground px-4 py-3 text-[15px] leading-relaxed text-background">{feedback.focus}</p>
            </section>
          ) : null}
        </>
      ) : null}
      {team && digest.reps?.length ? (
        <section className="space-y-2">
          <h2 className={THEME_TOKENS.typography.sectionTitle}>{t.product.reportDigestByRep}</h2>
          <div className="grid gap-3 md:grid-cols-2">
            {digest.reps.map((rep) => {
              const note = notes.get(rep.name.toLocaleLowerCase()) ?? null;
              return (
                <div key={rep.name} className="rounded-xl border border-border/70 bg-card px-4 py-3">
                  <p className="text-[15px] font-semibold">{rep.name}</p>
                  <p className="mt-1 text-[13px] text-muted-foreground">
                    {fill(t.product.reportDigestRepFacts, { calls: rep.calls, conversations: rep.conversations })}
                    {rep.adherence != null ? ` · ${fill(t.product.reportDigestRepProcess, { pct: pct(rep.adherence) ?? "" })}` : ""}
                  </p>
                  {note ? <p className="mt-2 text-sm leading-relaxed">{note}</p> : null}
                </div>
              );
            })}
          </div>
        </section>
      ) : null}
      {coach.adherence != null || types.length ? (
        <section className="max-w-2xl space-y-3">
          <h2 className={THEME_TOKENS.typography.sectionTitle}>{t.product.reportDigestProcessTitle}</h2>
          {coach.adherence != null && coach.adherence_steps ? (
            <Bar label={t.product.reportDigestProcess} value={coach.adherence} right={fill(t.product.reportDigestSteps, coach.adherence_steps)} />
          ) : null}
          {types.map(([label, count]) => (
            <Bar key={label} label={label} value={totalTypes ? count / totalTypes : null} right={fill(t.product.reportDigestConvShort, { n: count })} />
          ))}
        </section>
      ) : null}
      {coach.objections?.length ? (
        <section className="max-w-md space-y-2">
          <h2 className={THEME_TOKENS.typography.sectionTitle}>{t.product.reportDigestObjections}</h2>
          <ul className="text-sm">
            {coach.objections.map((item) => (
              <li key={item.label} className="flex justify-between gap-4 border-t border-border/60 py-2">
                <span>{item.label}</span>
                <span className="tabular-nums text-muted-foreground">{fill(t.product.reportDigestOpen, { total: item.total, open: item.open })}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
