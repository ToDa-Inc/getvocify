import { useQuery } from "@tanstack/react-query";
import { useLanguage } from "@/lib/i18n";
import {
  memoMeetingChecklistView,
  type MeetingChecklistPayload,
} from "@/lib/memo-meeting-checklist";
import { api } from "@/shared/lib/api-client";
import { THEME_TOKENS } from "@/lib/theme/tokens";

async function fetchMeetingChecklist(memoId: string): Promise<MeetingChecklistPayload | null> {
  try {
    return await api.post<MeetingChecklistPayload>("/copilot/checklist", {
      call_mode: "meeting",
      capture_id: memoId,
    });
  } catch {
    return null;
  }
}

export function MemoMeetingChecklist({ memoId }: { memoId: string }) {
  const { t } = useLanguage();
  const p = t.product;
  const query = useQuery({
    queryKey: ["memo-meeting-checklist", memoId],
    queryFn: () => fetchMeetingChecklist(memoId),
    retry: false,
  });

  const view = memoMeetingChecklistView(query.data, {
    progressTemplate: p.teamAdherenceOf,
    doneLabel: p.checklistDone,
  });
  if (!view) return null;

  return (
    <section aria-labelledby="meeting-checklist-title" className="mb-6 space-y-3">
      <h2 id="meeting-checklist-title" className={THEME_TOKENS.typography.capsLabel}>
        {p.coachingProcessHeading}
      </h2>
      <p className="text-sm text-muted-foreground">{view.progress}</p>
      <ul className="space-y-2">
        {view.steps.map((step) => (
          <li key={step.label} className="text-sm text-foreground">
            {step.kind === "met" ? (
              <>
                {step.label}{" "}
                <span className="text-muted-foreground">{step.doneLabel}</span>
              </>
            ) : (
              step.label
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
