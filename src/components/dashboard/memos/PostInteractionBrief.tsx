import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { debriefCopy, debriefView, type DebriefBar } from "@shared/ui/components/debrief.js";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { useAuth } from "@/features/auth";
import { reportKeys, reportsApi } from "@/lib/api/reports";
import { briefSurface, requestBriefSectionPlay, type BriefView } from "@/lib/post-brief";
import { usePostInteractionBrief } from "@/features/coaching/hooks/usePostInteractionBrief";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const CARD = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} mb-6 space-y-4 p-5`;

export function PostInteractionBrief({
  memoId,
  onPlay,
  markSeen = false,
}: {
  memoId: string;
  onPlay?: (offsetMs: number) => void;
  /** The rep reading their own ready debrief here clears it from the bell's Feedback. */
  markSeen?: boolean;
}) {
  const { t, language } = useLanguage();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const query = usePostInteractionBrief(memoId);
  const ready = query.data?.status === "ready";
  const bellTasks = Boolean(user?.company?.features?.includes("BELL_TASKS_ENABLED"));
  const markedFor = useRef<string | null>(null);
  useEffect(() => {
    if (!markSeen || !bellTasks || !ready || markedFor.current === memoId) return;
    markedFor.current = memoId;
    void reportsApi
      .markFeedbackSeen(memoId)
      .catch(() => undefined)
      .finally(() => queryClient.invalidateQueries({ queryKey: reportKeys.notifications }));
  }, [markSeen, bellTasks, ready, memoId, queryClient]);

  if (query.isError) {
    return (
      <section aria-labelledby="post-brief-title" className={CARD}>
        <h2 id="post-brief-title" className="text-[14px] font-medium tracking-tight text-foreground">{t.product.briefReadFailed}</h2>
      </section>
    );
  }
  // The v2 debrief carries `coach` (null or not); without it the company is on the first brief.
  if (query.data && "coach" in query.data) {
    return <CoachCard brief={query.data} lang={language === "EN" ? "en" : "es"} title={t.product.briefCoachTitle} />;
  }
  return <LegacyBrief brief={query.data} onPlay={onPlay} />;
}

/** One thing done well, one to change with the playbook's phrase, and the trend. */
function CoachCard({ brief, lang, title }: { brief: BriefView; lang: "es" | "en"; title: string }) {
  const view = debriefView(brief, lang);
  if (view.state === "hidden") return null;
  const copy = debriefCopy(lang);
  const caps = "text-[11px] uppercase tracking-[0.06em] text-muted-foreground";

  return (
    <section aria-labelledby="post-brief-title" className={`${CARD} ${THEME_TOKENS.motion.fadeIn}`}>
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="post-brief-title" className="text-[14px] font-medium tracking-tight text-foreground">{title}</h2>
        {view.state === "ready" && view.bars.length > 0 ? <Trend bars={view.bars} label={copy.debriefTrend} /> : null}
      </div>

      {view.state === "pending" ? (
        <p role="status" className={`flex items-center gap-2 ${THEME_TOKENS.typography.capsLabel}`}>
          <VocifySpinner size={12} />
          {copy.debriefPreparing}
        </p>
      ) : null}
      {view.state === "no_playbook" ? <p className={THEME_TOKENS.typography.capsLabel}>{copy.debriefNoPlaybook}</p> : null}
      {view.state === "empty" ? <p className={THEME_TOKENS.typography.capsLabel}>{copy.debriefEmpty}</p> : null}

      {view.state === "ready" ? (
        <>
          {view.kept ? (
            <div className="space-y-0.5">
              <p className={caps}>{copy.debriefKept}</p>
              <p className="text-sm text-foreground">
                {view.kept.label}
                {view.kept.quote ? <q className="ml-1 italic text-muted-foreground">{view.kept.quote}</q> : null}
              </p>
            </div>
          ) : null}
          {view.fix ? (
            <div className="space-y-0.5">
              <p className={`flex items-center gap-2 ${caps}`}>
                {copy.debriefFix}
                {view.fix.focus ? (
                  <span className={`${THEME_TOKENS.radius.pill} ${THEME_TOKENS.colors.highlight} px-2 py-px normal-case tracking-normal`}>
                    {copy.debriefFocus}
                  </span>
                ) : null}
              </p>
              <p className="text-[13.5px] text-foreground">{view.fix.label}</p>
              {view.fix.criterion ? <p className="text-sm text-muted-foreground">{view.fix.criterion}</p> : null}
              {view.fix.say ? (
                <p className="pt-0.5 text-sm text-foreground">
                  {copy.debriefTry} <q className="italic">{view.fix.say}</q>
                </p>
              ) : null}
            </div>
          ) : null}
          {view.outcome ? (
            <p className={THEME_TOKENS.typography.capsLabel}>
              {view.outcome.label} · {view.outcome.value ? copy.debriefYes : copy.debriefNo}
            </p>
          ) : null}
          {view.missed.length > 0 || view.moments.length > 0 ? (
            <details className="group space-y-2">
              <summary className="w-fit cursor-pointer list-none text-[13px] text-muted-foreground hover:text-foreground [&::-webkit-details-marker]:hidden">
                {copy.debriefDetail} <span aria-hidden className="inline-block transition-transform group-open:rotate-90">›</span>
              </summary>
              {view.missed.length > 0 ? (
                <div className="space-y-1 pt-2">
                  <p className={caps}>{copy.debriefMissed}</p>
                  <ul className="list-disc space-y-0.5 pl-4 text-sm text-muted-foreground">
                    {view.missed.map((item) => <li key={item.id}>{item.label}</li>)}
                  </ul>
                </div>
              ) : null}
              {view.moments.length > 0 ? (
                <div className="space-y-1 pt-2">
                  <p className={caps}>{copy.debriefMoments}</p>
                  <ul className="list-disc space-y-0.5 pl-4 text-sm text-muted-foreground">
                    {view.moments.map((line) => <li key={line}>{line}</li>)}
                  </ul>
                </div>
              ) : null}
            </details>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

/** This call last and in beige; the percentage on hover. No number on the surface, no ranking. */
function Trend({ bars, label }: { bars: DebriefBar[]; label: string }) {
  return (
    <span role="img" aria-label={label} className="inline-flex h-4 items-end gap-[3px]">
      {bars.map((bar, index) => (
        <span
          key={index}
          title={bar.value == null ? "—" : `${Math.round(bar.value * 100)} %`}
          className={`w-[5px] rounded-sm ${bar.current ? "bg-beige" : "bg-border"} ${bar.value == null ? "opacity-50" : ""}`}
          style={{ height: `${Math.max(0.12, bar.value ?? 0.12) * 100}%` }}
        />
      ))}
    </span>
  );
}

/** Companies without the v2 debrief: the first brief, unchanged in content. */
function LegacyBrief({ brief, onPlay }: { brief: BriefView | undefined; onPlay?: (offsetMs: number) => void }) {
  const { t } = useLanguage();
  const surface = brief ? briefSurface(brief, t.product) : null;
  const title = surface?.title ?? t.product.briefNotReady;
  return (
    <section aria-labelledby="post-brief-title" className={CARD}>
      <h2 id="post-brief-title" className="text-[14px] font-medium tracking-tight text-foreground">{title}</h2>
      {!surface ? null : (
        <div className="space-y-2 text-sm text-foreground">
          {surface.highlightNote ? <p className={THEME_TOKENS.typography.capsLabel}>{surface.highlightNote}</p> : null}
          {surface.waiting ? <p className={THEME_TOKENS.typography.capsLabel}>{t.product.briefPreparing}</p> : null}
          {surface.strength ? <p>{t.product.coachingStrength}: {surface.strength}</p> : null}
          {surface.improvement ? <p>{t.product.coachingImprovement}: {surface.improvement}</p> : null}
          {surface.sections.map((section) => (
            <div key={section.evidence_refs.join("-")} className="space-y-1">
              {section.quote ? <p className="italic text-muted-foreground">{section.quote}</p> : null}
              {surface.playable && section.offset_ms != null ? (
                <button
                  type="button"
                  className="text-[13px] text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                  onClick={() => requestBriefSectionPlay(surface.playable, section.offset_ms, onPlay)}
                >
                  {t.product.briefPlaySection}
                </button>
              ) : null}
            </div>
          ))}
          {surface.audioNote ? <p className={THEME_TOKENS.typography.capsLabel}>{surface.audioNote}</p> : null}
        </div>
      )}
    </section>
  );
}
