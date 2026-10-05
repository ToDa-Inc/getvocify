import { useQuery } from "@tanstack/react-query";
import { CalendarClock } from "lucide-react";
import { api } from "@/shared/lib/api-client";
import { useLanguage } from "@/lib/i18n";
import { detectedMeeting, meetingWhen } from "@/lib/meeting-proposal-review";

/** The meeting agreed on this call, as information only: no buttons, nothing written to the CRM. */
export function MeetingProposalReview({
  memoId,
  extractionPending = false,
}: {
  memoId: string;
  extractionPending?: boolean;
}) {
  const { t } = useLanguage();
  const query = useQuery({
    queryKey: ["meeting-proposal", memoId],
    queryFn: () => api.get<{ proposal: Record<string, unknown> | null }>(`/memos/${memoId}/meeting-proposal`),
    enabled: !extractionPending,
  });
  const meeting = detectedMeeting(query.data?.proposal);
  const when = meeting ? meetingWhen(meeting.startsAt, meeting.timezone, t.product.hourLocale) : null;
  if (!when) return null;
  return (
    <div className="flex items-start gap-3 rounded-xl border border-border/50 bg-card px-3.5 py-3 shadow-xs">
      <CalendarClock aria-hidden="true" strokeWidth={1.5} className="mt-0.5 h-4 w-4 shrink-0 text-beige" />
      <div className="min-w-0 flex-1 space-y-0.5">
        <p className="text-[11.5px] font-medium text-muted-foreground">{t.product.meetingDetected}</p>
        <p className="text-[13px] leading-relaxed text-foreground first-letter:uppercase">{when}</p>
      </div>
    </div>
  );
}
