import { Link } from "react-router-dom";
import { ArrowDownRight, ArrowUpRight, Download, Minus } from "lucide-react";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import {
  countDelta,
  percentText,
  rateDelta,
  repActivityCsv,
  repActivityRows,
  shareOf,
  teamActivityFooter,
  type Delta,
  type HosRep,
} from "@/lib/head-of-sales";
import { repFlowAdherenceText } from "@/lib/team-insights";

export type ManagerTotals = {
  attempts: number | null;
  connected: number | null;
  meetings: number | null;
  adherence: number | null;
};

const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card}`;
const HEAD = "px-3 py-2.5 text-left text-[12px] font-normal text-muted-foreground whitespace-nowrap";
const CELL = "px-3 py-2.5 text-sm text-foreground tabular-nums whitespace-nowrap";

function count(value: number | null | undefined, digits = 0): string {
  if (value == null) return "—";
  return new Intl.NumberFormat("es-ES", { maximumFractionDigits: digits }).format(value);
}

function Tile({ label, value, delta, hint, testId }: { label: string; value: string; delta: Delta; hint?: string; testId: string }) {
  const { t } = useLanguage();
  const p = t.product;
  const Icon = delta?.direction === "up" ? ArrowUpRight : delta?.direction === "down" ? ArrowDownRight : Minus;
  return (
    <div className={`${card} p-4 flex flex-col gap-1.5`} data-testid={testId}>
      <p className={THEME_TOKENS.typography.capsLabel}>{label}</p>
      <p className="text-[1.75rem] leading-none tracking-tight text-foreground tabular-nums">{value}</p>
      <p className="text-xs text-muted-foreground">
        {delta ? (
          <>
            <span className="inline-flex items-center gap-0.5 text-foreground">
              <Icon className="h-3.5 w-3.5" aria-hidden />
              {delta.text === "new" ? p.hosNew : delta.text}
            </span>{" "}
            {p.hosVsPrevious}
          </>
        ) : (
          p.hosNoComparison
        )}
      </p>
      {hint ? <p className="text-xs text-muted-foreground/80">{hint}</p> : null}
    </div>
  );
}

export function HosKpiTiles({ current, previous }: { current: ManagerTotals; previous: ManagerTotals | null }) {
  const { t } = useLanguage();
  const p = t.product;
  const connectedShare = current.attempts != null && current.connected != null ? shareOf(current.connected, current.attempts) : null;
  const meetingShare = current.connected != null && current.meetings != null ? shareOf(current.meetings, current.connected) : null;
  return (
    <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
      <Tile testId="hos-kpi-attempts" label={p.teamActivityAttempts} value={count(current.attempts)} delta={countDelta(current.attempts, previous?.attempts)} />
      <Tile
        testId="hos-kpi-connected"
        label={p.teamActivityConnected}
        value={count(current.connected)}
        delta={countDelta(current.connected, previous?.connected)}
        hint={connectedShare == null ? undefined : p.hosOfAttempts.replace("{rate}", percentText(connectedShare))}
      />
      <Tile
        testId="hos-kpi-meetings"
        label={p.teamActivityMeetings}
        value={count(current.meetings)}
        delta={countDelta(current.meetings, previous?.meetings)}
        hint={meetingShare == null ? undefined : p.hosOfConversations.replace("{rate}", percentText(meetingShare))}
      />
      <Tile testId="hos-kpi-adherence" label={p.hosAdherence} value={percentText(current.adherence)} delta={rateDelta(current.adherence, previous?.adherence)} />
    </div>
  );
}

/** Plan §3.1: attempts → conversations → meetings, each bar a share of the first step. */
export function HosFunnel({ current }: { current: ManagerTotals }) {
  const { t } = useLanguage();
  const p = t.product;
  const steps = [
    { label: p.teamActivityAttempts, value: current.attempts ?? 0 },
    { label: p.teamActivityConnected, value: current.connected ?? 0 },
    { label: p.teamActivityMeetings, value: current.meetings ?? 0 },
  ];
  const top = steps[0].value;
  return (
    <section className={`${card} p-5`} aria-labelledby="hos-funnel" data-testid="hos-funnel">
      <h2 id="hos-funnel" className={THEME_TOKENS.typography.sectionTitle}>{p.hosFunnelHeading}</h2>
      <ol className="mt-4 space-y-3">
        {steps.map((step, index) => {
          const width = top ? Math.max((step.value / top) * 100, step.value ? 2 : 0) : 0;
          const prev = index ? steps[index - 1].value : null;
          return (
            <li key={step.label} className="grid grid-cols-[8.5rem_minmax(0,1fr)_4rem] items-center gap-3">
              <span className="text-[13px] text-muted-foreground truncate">{step.label}</span>
              <div className="h-6 rounded-md bg-secondary/40 overflow-hidden" aria-hidden>
                <div className="h-full rounded-r-[4px] bg-beige" style={{ width: `${width}%` }} />
              </div>
              <span className="text-right text-sm tabular-nums text-foreground">
                {count(step.value)}
                {index > 0 ? (
                  <span className="block text-[11px] text-muted-foreground">{percentText(shareOf(step.value, prev ?? 0))}</span>
                ) : null}
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

export function HosPeopleTable({ reps, showRepDetail, csvName }: { reps: HosRep[]; showRepDetail: boolean; csvName: string }) {
  const { t } = useLanguage();
  const p = t.product;
  const rows = repActivityRows(reps);
  const { median, total } = teamActivityFooter(rows);
  const showRole = rows.some((row) => row.salesRole);
  const showFlows = showRepDetail && rows.some((row) => row.flows);
  const roleLabel = (role: string | null) =>
    role === "sdr" ? p.hosRoleSdr : role === "ae" ? p.hosRoleAe : role ? p.hosRoleGeneral : "—";

  const download = () => {
    const url = URL.createObjectURL(new Blob([repActivityCsv(rows, p)], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = csvName;
    link.click();
    URL.revokeObjectURL(url);
  };

  if (!rows.length) return null;
  return (
    <div className={`${card} overflow-hidden`}>
      <div className="flex items-start justify-between gap-3 px-4 pt-4 pb-3">
        <div>
          <h3 className={THEME_TOKENS.typography.sectionTitle}>{p.hosPeopleHeading}</h3>
          <p className="text-xs text-muted-foreground mt-1">{p.hosPeopleSubtitle}</p>
        </div>
        <button
          type="button"
          onClick={download}
          className="shrink-0 inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground"
        >
          <Download className="h-3.5 w-3.5" aria-hidden />
          {p.hosDownloadCsv}
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px]" data-testid="hos-people-table">
          <thead className="border-y border-border/60">
            <tr>
              <th scope="col" className={HEAD}>{p.hosColName}</th>
              {showRole ? <th scope="col" className={HEAD}>{p.hosColRole}</th> : null}
              <th scope="col" className={`${HEAD} text-right`}>{p.hosColAttempts}</th>
              <th scope="col" className={`${HEAD} text-right`}>{p.hosColConversations}</th>
              <th scope="col" className={`${HEAD} text-right`}>{p.hosColConnection}</th>
              <th scope="col" className={`${HEAD} text-right`}>{p.hosColMeetings}</th>
              {showFlows ? <th scope="col" className={`${HEAD} text-right`}>{p.teamRepFlowSdr}</th> : null}
              {showFlows ? <th scope="col" className={`${HEAD} text-right`}>{p.teamRepFlowAe}</th> : null}
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40">
            {rows.map((row) => (
              <tr key={row.userId} data-testid="hos-people-row">
                <th scope="row" className={`${CELL} font-normal text-left`}>
                  {showRepDetail ? (
                    <Link className="underline-offset-2 hover:underline" to={`/dashboard/insights/rep/${row.userId}`}>
                      {row.name}
                    </Link>
                  ) : (
                    row.name
                  )}
                </th>
                {showRole ? <td className={`${CELL} text-muted-foreground`}>{roleLabel(row.salesRole)}</td> : null}
                <td className={`${CELL} text-right`}>{count(row.attempts)}</td>
                <td className={`${CELL} text-right`}>{count(row.connected)}</td>
                <td className={`${CELL} text-right`}>{percentText(row.connectionRate)}</td>
                <td className={`${CELL} text-right`}>{count(row.meetings)}</td>
                {showFlows ? <td className={`${CELL} text-right`}>{repFlowAdherenceText(row.flows?.sdr ?? null, p.teamRepFlowNoData)}</td> : null}
                {showFlows ? <td className={`${CELL} text-right`}>{repFlowAdherenceText(row.flows?.ae ?? null, p.teamRepFlowNoData)}</td> : null}
              </tr>
            ))}
          </tbody>
          <tfoot className="border-t border-border/60 bg-secondary/20">
            <tr className="text-muted-foreground">
              <th scope="row" className={`${CELL} font-normal text-left text-muted-foreground`}>
                {p.hosMedian}
                {median.people ? ` (${median.people})` : ""}
              </th>
              {showRole ? <td className={CELL} /> : null}
              <td className={`${CELL} text-right text-muted-foreground`}>{count(median.attempts, 1)}</td>
              <td className={`${CELL} text-right text-muted-foreground`}>{count(median.connected, 1)}</td>
              <td className={`${CELL} text-right text-muted-foreground`}>{percentText(median.connectionRate)}</td>
              <td className={`${CELL} text-right text-muted-foreground`}>{count(median.meetings, 1)}</td>
              {showFlows ? <td className={CELL} /> : null}
              {showFlows ? <td className={CELL} /> : null}
            </tr>
            <tr data-testid="hos-people-total">
              <th scope="row" className={`${CELL} font-normal text-left`}>{p.hosTotal}</th>
              {showRole ? <td className={CELL} /> : null}
              <td className={`${CELL} text-right`}>{count(total.attempts)}</td>
              <td className={`${CELL} text-right`}>{count(total.connected)}</td>
              <td className={`${CELL} text-right`}>{percentText(total.connectionRate)}</td>
              <td className={`${CELL} text-right`}>{count(total.meetings)}</td>
              {showFlows ? <td className={CELL} /> : null}
              {showFlows ? <td className={CELL} /> : null}
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
