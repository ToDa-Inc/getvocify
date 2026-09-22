import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { useLanguage } from "@/lib/i18n";
import { api } from "@/shared/lib/api-client";
import {
  mergeNotes,
  noteFieldLabel,
  objectionReview,
  patternCategoryLabel,
  patternKindLabel,
  patternResolutionLabel,
  type ReviewNote,
  type ReviewPattern,
} from "@/lib/interaction-objections";

type SaveStatus = "idle" | "syncing" | "saved" | "error";

export function InteractionObjections({
  memoId,
  canPlaySpan,
  offsetMs,
}: {
  memoId: string;
  canPlaySpan: boolean;
  offsetMs: number;
}) {
  const { t } = useLanguage();
  const p = t.product;
  const query = useQuery({
    queryKey: ["memo-objections", memoId],
    queryFn: () => api.get<{ coverage: "complete" | "partial" | "unavailable"; patterns: ReviewPattern[]; notes: ReviewNote[] }>(
      `/memos/${memoId}/objections`,
    ),
  });
  const [added, setAdded] = useState<ReviewNote[]>([]);
  const notes = mergeNotes(query.data?.notes ?? [], added);
  const [text, setText] = useState("");
  const [status, setStatus] = useState<SaveStatus>("idle");
  const review = objectionReview({
    coverage: query.data?.coverage ?? "unavailable",
    patterns: query.data?.patterns ?? [],
    notes,
    canPlaySpan,
    copy: p,
  });
  const label = noteFieldLabel(status, p);

  async function save() {
    const body = text.trim();
    if (!body) return;
    const annotationId = `note-${crypto.randomUUID()}`;
    setStatus("syncing");
    try {
      const saved = await api.put<{ annotation_id: string; text: string; offset_ms: number; author_id: string }>(
        `/memos/${memoId}/annotations/${annotationId}`,
        { text: body, offset_ms: offsetMs },
      );
      setAdded((current) => [
        ...current,
        {
          annotation_id: saved.annotation_id,
          text: saved.text,
          offset_ms: saved.offset_ms,
          author_id: saved.author_id,
          turn_id: null,
        },
      ]);
      setText("");
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  }

  return (
    <section aria-labelledby="objections-title" className="mb-6 space-y-3">
      <h2 id="objections-title" className="text-lg">{p.teamHeadingObjections}</h2>
      {review.title ? <p>{review.title}</p> : null}
      <ul className="space-y-3">
        {review.patterns.map((pattern) => (
          <li key={pattern.pattern_id}>
            <p>
              {patternCategoryLabel(pattern.category, p)} · {patternKindLabel(pattern.kind, p)} ·{" "}
              {patternResolutionLabel(pattern.resolution, p)}
            </p>
            {pattern.prospect_quotes.map((quote) => (
              <p key={quote}>{p.prospectQuote.replace("{quote}", quote)}</p>
            ))}
            {pattern.response ? <p>{pattern.response}</p> : null}
          </li>
        ))}
        {review.notes.map((note) => (
          <li key={note.annotation_id}>
            <p>{note.label}: {note.text}</p>
            <p>
              {p.noteOffsetMeta.replace("{offset}", String(note.offset_ms)).replace("{author}", note.author_id)}
            </p>
            {note.playable ? <p>{p.objectionPlayableSpan}</p> : null}
          </li>
        ))}
      </ul>
      <label className="block space-y-2">
        <span>{p.noteLabel}</span>
        <textarea value={text} onChange={(event) => setText(event.target.value)} rows={2} className="w-full rounded-md border p-2" />
      </label>
      <Button type="button" variant="outline" onClick={() => void save()} disabled={status === "syncing"}>
        {p.noteSaveButton}
      </Button>
      {label ? <p role="status">{label}</p> : null}
    </section>
  );
}
