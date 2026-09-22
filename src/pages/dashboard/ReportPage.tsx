import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useLanguage } from "@/lib/i18n";
import { reportSurface, type ReportSnapshot } from "@/lib/report-snapshot";
import { api } from "@/shared/lib/api-client";

export default function ReportPage() {
  const { t } = useLanguage();
  const { id } = useParams();
  const query = useQuery({
    queryKey: ["report", id],
    queryFn: () => api.get<{ snapshot: ReportSnapshot }>(`/reports/${id}`),
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

  const surface = reportSurface(query.data.snapshot, t.product.unavailable);
  const coachingText = surface.coaching?.trim();
  return (
    <main className="max-w-5xl mx-auto space-y-6 p-6">
      <h1>Informe</h1>
      <table>
        <tbody>
          <tr><th>Intentos</th><td>{surface.attempts}</td></tr>
          <tr><th>Conversaciones</th><td>{surface.connected}</td></tr>
          <tr><th>Reuniones acordadas</th><td>{surface.meetings}</td></tr>
          <tr><th>Cierres</th><td>{surface.wonLabel}</td></tr>
          <tr><th>Adherencia</th><td>{surface.adherenceLabel}</td></tr>
        </tbody>
      </table>
      {coachingText ? <p>{coachingText}</p> : null}
    </main>
  );
}
