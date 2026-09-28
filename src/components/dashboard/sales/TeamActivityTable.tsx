import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ActivityStats, MemberActivity, TeamMedian } from "@/features/team/types";
import { SALES_ROLE_LABEL, countDelta, formatCount, formatMedian, formatPercent } from "./format";

interface TeamActivityTableProps {
  members: MemberActivity[];
  total: ActivityStats;
  median: TeamMedian;
  usefulCallSeconds: number;
  periodLabel: string;
}

const HEAD = "px-4 py-3 text-left text-[12px] font-normal text-muted-foreground whitespace-nowrap";
const CELL = "px-4 py-3 text-sm text-foreground tabular-nums whitespace-nowrap";

function otherOutcomes(s: ActivityStats) {
  return s.failed + s.unknown;
}

function Results({ s }: { s: ActivityStats }) {
  if (!s.calls) return <span className="text-muted-foreground">—</span>;
  return (
    <span className="text-[13px]">
      <span className="text-foreground">{formatCount(s.connected)} connected</span>
      <span className="block text-xs text-muted-foreground">
        {formatCount(s.voicemail)} voicemail · {formatCount(s.noAnswer)} no answer
        {otherOutcomes(s) ? ` · ${formatCount(otherOutcomes(s))} other` : ""}
      </span>
    </span>
  );
}

function csvCell(value: string | number | null): string {
  const text = value == null ? "" : String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function downloadCsv(members: MemberActivity[], periodLabel: string) {
  const header = ["Person", "Email", "Position", "Calls", "Connected", "Voicemail", "No answer", "Other", "Connection rate", "Useful conversations"];
  const rows = members.map((m) => [
    m.name,
    m.email,
    SALES_ROLE_LABEL[m.salesRole],
    m.current.calls,
    m.current.connected,
    m.current.voicemail,
    m.current.noAnswer,
    otherOutcomes(m.current),
    m.current.connectionRate == null ? null : Math.round(m.current.connectionRate * 1000) / 10,
    m.current.useful,
  ]);
  const csv = [header, ...rows].map((r) => r.map(csvCell).join(",")).join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `team-activity-${periodLabel.replace(/\s+/g, "")}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

export function TeamActivityTable({ members, total, median, usefulCallSeconds, periodLabel }: TeamActivityTableProps) {
  return (
    <div>
      <div className="flex items-center justify-end px-4 pb-3">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="rounded-full text-muted-foreground"
          onClick={() => downloadCsv(members, periodLabel)}
          disabled={!members.length}
        >
          <Download className="h-3.5 w-3.5" />
          Download CSV
        </Button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px]" data-testid="team-activity-table">
          <thead className="border-y border-border/60">
            <tr>
              <th className={HEAD}>Person</th>
              <th className={`${HEAD} text-right`}>Calls</th>
              <th className={HEAD}>Call results</th>
              <th className={`${HEAD} text-right`} title="Connected calls ÷ calls">
                Connection
              </th>
              <th
                className={`${HEAD} text-right`}
                title={`Connected calls lasting at least ${usefulCallSeconds} seconds`}
              >
                Useful conversations
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40">
            {members.map((m) => {
              const delta = countDelta(m.current.calls, m.previous.calls);
              return (
                <tr key={m.userId} data-testid="team-activity-row">
                  <td className={CELL}>
                    <span className="block truncate max-w-[14rem]">{m.name}</span>
                    <span className="text-xs text-muted-foreground">{SALES_ROLE_LABEL[m.salesRole]}</span>
                  </td>
                  <td className={`${CELL} text-right`}>
                    {formatCount(m.current.calls)}
                    {delta && <span className="block text-xs text-muted-foreground">{delta.text}</span>}
                  </td>
                  <td className={CELL}>
                    <Results s={m.current} />
                  </td>
                  <td className={`${CELL} text-right`}>{formatPercent(m.current.connectionRate)}</td>
                  <td className={`${CELL} text-right`}>{formatCount(m.current.useful)}</td>
                </tr>
              );
            })}
          </tbody>
          <tfoot className="border-t border-border/60 bg-secondary/20">
            <tr>
              <td className={`${CELL} text-muted-foreground`} title="Per-person median over people who placed at least one call">
                Median{median.people ? ` (${median.people} active)` : ""}
              </td>
              <td className={`${CELL} text-right text-muted-foreground`}>{formatMedian(median.calls)}</td>
              <td className={`${CELL} text-muted-foreground`}>
                {median.connected == null ? "—" : `${formatMedian(median.connected)} connected`}
              </td>
              <td className={`${CELL} text-right text-muted-foreground`}>{formatPercent(median.connectionRate)}</td>
              <td className={`${CELL} text-right text-muted-foreground`}>{formatMedian(median.useful)}</td>
            </tr>
            <tr data-testid="team-activity-total">
              <td className={CELL}>Team total</td>
              <td className={`${CELL} text-right`}>{formatCount(total.calls)}</td>
              <td className={CELL}>
                <Results s={total} />
              </td>
              <td className={`${CELL} text-right`}>{formatPercent(total.connectionRate)}</td>
              <td className={`${CELL} text-right`}>{formatCount(total.useful)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
