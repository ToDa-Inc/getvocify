import { briefSurface, requestBriefSectionPlay } from "@/lib/post-brief";
import { usePostInteractionBrief } from "@/features/coaching/hooks/usePostInteractionBrief";
import { useLanguage } from "@/lib/i18n";

export function PostInteractionBrief({
  memoId,
  onPlay,
}: {
  memoId: string;
  onPlay?: (offsetMs: number) => void;
}) {
  const { t } = useLanguage();
  const query = usePostInteractionBrief(memoId);
  const surface = query.data ? briefSurface(query.data, t.product) : null;
  const title = query.isError
    ? t.product.briefReadFailed
    : surface?.title ?? t.product.briefNotReady;
  return (
    <section aria-labelledby="post-brief-title" className="mb-6 min-h-24 space-y-2">
      <h2 id="post-brief-title" className="text-lg">{title}</h2>
      {!surface ? null : (
        <>
          {surface.highlightNote ? <p>{surface.highlightNote}</p> : null}
          {surface.waiting ? <p>{t.product.briefPreparing}</p> : null}
          {surface.strength ? <p>{t.product.coachingStrength}: {surface.strength}</p> : null}
          {surface.improvement ? <p>{t.product.coachingImprovement}: {surface.improvement}</p> : null}
          {surface.sections.map((section) => (
            <div key={section.evidence_refs.join("-")} className="space-y-1">
              {section.quote ? <p>{section.quote}</p> : null}
              {surface.playable && section.offset_ms != null ? (
                <button
                  type="button"
                  onClick={() => requestBriefSectionPlay(surface.playable, section.offset_ms, onPlay)}
                >
                  Reproducir tramo
                </button>
              ) : null}
            </div>
          ))}
          {surface.audioNote ? <p>{surface.audioNote}</p> : null}
          {surface.missed.length > 0 ? (
            <div>
              <h3>{t.product.briefMissedHeading}</h3>
              <ul>
                {surface.missed.map((item) => (
                  <li key={item.id}>{item.label}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {surface.phrases.length > 0 ? (
            <div>
              <h3>{t.product.briefPhrasesHeading}</h3>
              <ul>
                {surface.phrases.map((phrase) => (
                  <li key={phrase}>{phrase}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {surface.highlights.length > 0 ? (
            <div>
              <h3>{t.product.briefHighlightsHeading}</h3>
              <ul>
                {surface.highlights.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {surface.progress.length > 0 ? (
            <div>
              <h3>{t.product.briefProgressHeading}</h3>
              <p>{surface.progress.map((value) => (value == null ? "—" : `${Math.round(value * 100)}%`)).join(" · ")}</p>
            </div>
          ) : null}
          {surface.flow === "sdr" && surface.meetingBooked != null ? (
            <p>{t.product.briefMeetingBooked} {surface.meetingBooked ? t.product.briefYes : t.product.briefNo}</p>
          ) : null}
          {surface.flow === "ae" && surface.nextStepAgreed != null ? (
            <p>{t.product.briefNextStep} {surface.nextStepAgreed ? t.product.briefYes : t.product.briefNo}</p>
          ) : null}
        </>
      )}
    </section>
  );
}
