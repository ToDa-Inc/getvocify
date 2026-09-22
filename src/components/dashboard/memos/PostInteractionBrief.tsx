import { briefSurface } from "@/lib/post-brief";
import { usePostInteractionBrief } from "@/features/coaching/hooks/usePostInteractionBrief";

export function PostInteractionBrief({ memoId }: { memoId: string }) {
  const query = usePostInteractionBrief(memoId);
  if (query.isError || !query.data) return null;
  const surface = briefSurface(query.data);
  return (
    <section aria-labelledby="post-brief-title" className="mb-6 min-h-24 space-y-2">
      <h2 id="post-brief-title" className="text-lg">{surface.title}</h2>
      {surface.waiting ? <p>Preparando…</p> : null}
      {surface.strength ? <p>Fortaleza: {surface.strength}</p> : null}
      {surface.improvement ? <p>Mejora: {surface.improvement}</p> : null}
      {surface.sections.map((section) => (
        <p key={section.evidence_refs.join("-")}>{section.quote}</p>
      ))}
      {surface.audioNote ? <p>{surface.audioNote}</p> : null}
      {surface.playable ? <button type="button">Reproducir tramo</button> : null}
    </section>
  );
}
