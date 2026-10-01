import "@shared/ui/components/v-review-tabs.js";
import { useCallback, useMemo, useState } from "react";
import { activeReviewTab, reviewTabs, type ReviewTab } from "@shared/ui/components/review-tabs.js";
import { hasCoaching } from "@shared/ui/components/debrief.js";
import { useMemoScore } from "@/features/coaching/hooks/useMemoScore";
import { usePostInteractionBrief } from "@/features/coaching/hooks/usePostInteractionBrief";
import type { ScoreView } from "@/lib/coaching-score";
import { useVElement, type VAction } from "@/hooks/use-v-element";
import { useLanguage } from "@/lib/i18n";
import { htmlLang } from "@/lib/app-language";

/** Coaching earns a tab once there is a score, an unscored read, or a setup the viewer can do. An
 * internal memo keeps it too: it says the memo is not scored and holds the way back to a real type. */
function scoreReadable(score: ScoreView | undefined, role: string): boolean {
  if (!score) return false;
  if (score.reason === "missing_playbook") return role === "owner" || role === "admin";
  if (score.reason === "not_scored") return false;
  return true;
}

/** The post-call review tabs for one memo. Email and coaching belong to the memo's author. */
export function useReviewTabs({ memoId, own, role }: { memoId: string; own: boolean; role: string }) {
  const [picked, setPicked] = useState<string>("note");
  const [counts, setCounts] = useState({ fields: 0, tasks: 0 });
  const [followupStatus, setFollowupStatus] = useState<string | null>(null);
  const enabled = own && Boolean(memoId);
  const score = useMemoScore(memoId, { enabled });
  const brief = usePostInteractionBrief(memoId, { enabled });
  const coaching = enabled && (scoreReadable(score.data, role) || hasCoaching(brief.data));

  const tabs = useMemo(
    () =>
      reviewTabs({
        fieldCount: counts.fields,
        taskCount: counts.tasks,
        followupStatus: own ? followupStatus : null,
        coaching,
      }),
    [counts.fields, counts.tasks, own, followupStatus, coaching],
  );
  const onTabCounts = useCallback((next: { fields: number; tasks: number }) => {
    setCounts((prev) => (prev.fields === next.fields && prev.tasks === next.tasks ? prev : next));
  }, []);

  return {
    tabs,
    active: activeReviewTab(tabs, picked),
    select: setPicked,
    onTabCounts,
    onFollowupStatus: setFollowupStatus,
  };
}

export function ReviewTabBar({
  tabs,
  active,
  onSelect,
}: {
  tabs: ReviewTab[];
  active: string;
  onSelect: (tab: string) => void;
}) {
  const { language } = useLanguage();
  const view = useMemo(() => ({ tabs, active }), [tabs, active]);
  const onAction = useCallback(
    ({ action, value }: VAction) => {
      if (action === "tab" && value) onSelect(value);
    },
    [onSelect],
  );
  const bind = useVElement(view, onAction);
  return <v-review-tabs ref={bind} lang={htmlLang(language)} />;
}

/** A page-owned panel: hidden, never unmounted, so a half-written email survives a tab switch. */
export function ReviewPanel({ id, active, children }: { id: string; active: string; children: React.ReactNode }) {
  return (
    <div id={`review-panel-${id}`} role="tabpanel" aria-labelledby={`review-tab-${id}`} hidden={active !== id}>
      {children}
    </div>
  );
}
