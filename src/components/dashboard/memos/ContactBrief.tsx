import { useQuery } from "@tanstack/react-query";
import { visibleBrief } from "@shared/ui/brief.js";
import { api } from "@/shared/lib/api-client";

type BriefPayload = { text?: string | null; lines?: { text?: string | null }[] };

export function ContactBrief({ contactId }: { contactId: string }) {
  const query = useQuery({
    queryKey: ["brief", contactId],
    queryFn: () =>
      api.get<BriefPayload>(`/briefs?contact_id=${encodeURIComponent(contactId)}&connection_id=hubspot`),
  });
  if (!query.data) return null;
  const lines = visibleBrief(query.data);
  if (lines.length === 0) return null;
  return (
    <section aria-label="Antes de llamar" className="space-y-1">
      {lines.map((line, index) => (
        <p key={`${index}-${line}`}>{line}</p>
      ))}
    </section>
  );
}
