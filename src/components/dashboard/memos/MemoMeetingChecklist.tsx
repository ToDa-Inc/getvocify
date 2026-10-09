import { useQuery } from "@tanstack/react-query";
import { useLanguage } from "@/lib/i18n";
import {
  memoMeetingChecklistView,
  type MeetingChecklistPayload,
} from "@/lib/memo-meeting-checklist";
import { api } from "@/shared/lib/api-client";
import { Check, Circle } from "lucide-react";

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

/** The playbook steps of this call, inside the coaching "Process" card. `showProgress` is off when
 * the score line above already says "Pasos 4/5", so the count is never said twice. */
export function MemoMeetingChecklist({ memoId, showProgress = true }: { memoId: string; showProgress?: boolean }) {
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
  if (!view || !view.steps.length) return null;

  return (
    <div className="space-y-2">
      {showProgress ? <p className="text-[15px] tabular-nums text-foreground">{view.progress}</p> : null}
      <ul className="space-y-1.5">
        {view.steps.map((step) => (
          <li key={step.label} className="flex items-center gap-2.5 text-sm">
            {step.kind === "met" ? (
              <Check className="h-3.5 w-3.5 shrink-0 text-success" aria-label={step.doneLabel} />
            ) : (
              <Circle className="h-3.5 w-3.5 shrink-0 text-muted-foreground/40" aria-hidden />
            )}
            <span className={step.kind === "met" ? "text-foreground" : "text-muted-foreground"}>{step.label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
