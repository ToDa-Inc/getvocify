import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { reportSurface, type ReportSnapshot } from "@/lib/report-snapshot";
import { api } from "@/shared/lib/api-client";

export default function ReportPage() {
  const { id } = useParams();
  const query = useQuery({
    queryKey: ["report", id],
    queryFn: () => api.get<{ snapshot: ReportSnapshot }>(`/reports/${id}`),
    enabled: Boolean(id),
    retry: false,
  });
  if (!query.data) return <main className="max-w-5xl mx-auto p-6"><h1>Informe</h1></main>;
  const surface = reportSurface(query.data.snapshot);
  return (
    <main className="max-w-5xl mx-auto space-y-6 p-6">
      <h1>Informe</h1>
      <table>
        <tbody>
          <tr><th>Intentos</th><td>{surface.attempts}</td></tr>
          <tr><th>Conversaciones</th><td>{surface.connected}</td></tr>
          <tr><th>Reuniones acordadas</th><td>{surface.meetings}</td></tr>
          <tr><th>Cierres</th><td>{surface.wonLabel}</td></tr>
        </tbody>
      </table>
    </main>
  );
}
