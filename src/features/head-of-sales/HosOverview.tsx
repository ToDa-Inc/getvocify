import { Link } from "react-router-dom";
import { Download } from "lucide-react";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import {
  percentText,
  repActivityCsv,
  repActivityRows,
  teamActivityFooter,
  type HosPeriod,
  type HosRep,
} from "@/lib/head-of-sales";
import { repFlowAdherenceText } from "@/lib/team-insights";

const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card}`;
const HEAD = "px-3 py-2.5 text-left text-[12px] font-normal text-muted-foreground whitespace-nowrap";
const CELL = "px-3 py-2.5 text-sm text-foreground tabular-nums whitespace-nowrap";

function count(value: number | null | undefined, digits = 0): string {
  if (value == null) return "—";
  return new Intl.NumberFormat("es-ES", { maximumFractionDigits: digits }).format(value);
}

/** `showRepDetail` only gates the SDR/AE flow-adherence columns (MANAGER_HOME_ENABLED); the name
 * always links to the rep page, carrying the period. `stale` = old numbers under a new filter. */
export function HosPeopleTable({ reps, showRepDetail, csvName, period, stale = false }: {
  reps: HosRep[];
  showRepDetail: boolean;
  csvName: string;
  period: HosPeriod;
  stale?: boolean;
}) {
  const { t } = useLanguage();
  const p = t.product;
  const rows = repActivityRows(reps);
  const { median, total } = teamActivityFooter(rows);
  const showRole = rows.some((row) => row.salesRole);
  const showFocus = rows.some((row) => row.focus !== undefined);
  const showFlows = showRepDetail && rows.some((row) => row.flows);
  const roleLabel = (role: string | null) =>
    role === "sdr" ? p.hosRoleSdr : role === "ae" ? p.hosRoleAe : role ? p.hosRoleGeneral : "—";

  const download = () => {
    if (stale) return;
    const url = URL.createObjectURL(new Blob([repActivityCsv(rows, p)], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = csvName;
    link.click();
    URL.revokeObjectURL(url);
  };

  if (!rows.length) return null;
  return (
    <div className={`${card} overflow-hidden transition-opacity ${stale ? "opacity-50" : ""}`} aria-busy={stale}>
      <div className="flex items-start justify-between gap-3 px-4 pt-4 pb-3">
        <div>
          <h3 className={THEME_TOKENS.typography.sectionTitle}>{p.hosPeopleHeading}</h3>
          <p className="text-xs text-muted-foreground mt-1">{p.hosPeopleSubtitle}</p>
        </div>
        <button
          type="button"
          onClick={download}
          disabled={stale}
          className="shrink-0 inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground disabled:opacity-50 disabled:pointer-events-none"
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
              {showFocus ? <th scope="col" className={HEAD}>{p.hosColFocusWeek}</th> : null}
              {showFlows ? <th scope="col" className={`${HEAD} text-right`}>{p.teamRepFlowSdr}</th> : null}
              {showFlows ? <th scope="col" className={`${HEAD} text-right`}>{p.teamRepFlowAe}</th> : null}
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40">
            {rows.map((row) => (
              <tr key={row.userId} data-testid="hos-people-row">
                <th scope="row" className={`${CELL} font-normal text-left`}>
                  <Link className="underline-offset-2 hover:underline" to={`/dashboard/insights/rep/${row.userId}?period=${period}`}>
                    {row.name}
                  </Link>
                </th>
                {showRole ? <td className={`${CELL} text-muted-foreground`}>{roleLabel(row.salesRole)}</td> : null}
                <td className={`${CELL} text-right`}>{count(row.attempts)}</td>
                <td className={`${CELL} text-right`}>{count(row.connected)}</td>
                <td className={`${CELL} text-right`}>{percentText(row.connectionRate)}</td>
                <td className={`${CELL} text-right`}>{count(row.meetings)}</td>
                {showFocus ? <td className={CELL}>{row.focus?.label ?? "—"}</td> : null}
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
              {showFocus ? <td className={CELL} /> : null}
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
              {showFocus ? <td className={CELL} /> : null}
              {showFlows ? <td className={CELL} /> : null}
              {showFlows ? <td className={CELL} /> : null}
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
