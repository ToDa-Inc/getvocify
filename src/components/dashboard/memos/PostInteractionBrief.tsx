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
  const surface = query.data ? briefSurface(query.data) : null;
  const title = query.isError
    ? t.product.briefReadFailed
    : surface?.title ?? t.product.briefNotReady;
  return (
    <section aria-labelledby="post-brief-title" className="mb-6 min-h-24 space-y-2">
      <h2 id="post-brief-title" className="text-lg">{title}</h2>
      {!surface ? null : (
        <>
          {surface.highlightNote ? <p>{surface.highlightNote}</p> : null}
          {surface.waiting ? <p>Preparando…</p> : null}
          {surface.strength ? <p>Fortaleza: {surface.strength}</p> : null}
          {surface.improvement ? <p>Mejora: {surface.improvement}</p> : null}
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
        </>
      )}
    </section>
  );
}
