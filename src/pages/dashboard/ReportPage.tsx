import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useLanguage } from "@/lib/i18n";
import { reportPagePresentation, type ReportSnapshot } from "@/lib/report-snapshot";
import { api } from "@/shared/lib/api-client";

function ActivityBar({ width, label }: { width: number | null; label: string }) {
  if (width == null) return null;
  return (
    <div className="space-y-1">
      <span>{label}</span>
      <div className="h-2 w-full max-w-md rounded bg-muted">
        <div className="h-2 rounded bg-primary" style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

export default function ReportPage() {
  const { t } = useLanguage();
  const { id } = useParams();
  const query = useQuery({
    queryKey: ["report", id],
    queryFn: () =>
      api.get<{ snapshot: ReportSnapshot; report_type: string }>(`/reports/${id}`),
    enabled: Boolean(id),
    retry: false,
  });

  if (query.isPending) {
    return (
      <main className="max-w-5xl mx-auto p-6">
        <h1>Informe</h1>
        <p>{t.product.reportLoading}</p>
      </main>
    );
  }

  if (query.isError) {
    return (
      <main className="max-w-5xl mx-auto p-6">
        <h1>Informe</h1>
        <p>{t.product.reportFailed}</p>
      </main>
    );
  }

  const weekly = query.data.report_type === "weekly";
  const view = reportPagePresentation(query.data.snapshot, {
    weekly,
    unavailable: t.product.unavailable,
  });
  const coachingText = view.coaching?.trim();
  return (
    <main className="max-w-5xl mx-auto space-y-6 p-6">
      <h1>Informe</h1>
      <table>
        <tbody>
          {view.rows.map((row) => (
            <tr key={row.cellKey}>
              <th>{t.product[row.labelKey]}</th>
              <td>{row.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {weekly && view.bars ? (
        <section className="space-y-4">
          <ActivityBar
            width={view.bars.conversationsOfAttempts}
            label={t.product.teamActivityConnected}
          />
          <ActivityBar
            width={view.bars.meetingsOfAttempts}
            label={t.product.teamActivityMeetings}
          />
          {view.activityTable ? (
            <table>
              <tbody>
                {view.activityTable.map((row) => (
                  <tr key={row.cellKey}>
                    <th>{t.product[row.labelKey]}</th>
                    <td>{row.value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </section>
      ) : null}
      {coachingText ? <p>{coachingText}</p> : null}
      {view.exampleLinks.length ? (
        <ul>
          {view.exampleLinks.map((href) => (
            <li key={href}>
              <Link to={href}>{href}</Link>
            </li>
          ))}
        </ul>
      ) : null}
    </main>
  );
}
