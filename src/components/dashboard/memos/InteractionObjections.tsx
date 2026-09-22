import { useState } from "react";
import { Button } from "@/components/ui/button";
import { api } from "@/shared/lib/api-client";
import { noteFieldLabel, objectionReview, type ReviewNote, type ReviewPattern } from "@/lib/interaction-objections";

type SaveStatus = "idle" | "syncing" | "saved" | "error";

export function InteractionObjections({
  memoId,
  coverage,
  patterns,
  notes,
  canPlaySpan,
  offsetMs,
}: {
  memoId: string;
  coverage: "complete" | "partial" | "unavailable";
  patterns: ReviewPattern[];
  notes: ReviewNote[];
  canPlaySpan: boolean;
  offsetMs: number;
}) {
  const [localNotes, setLocalNotes] = useState<ReviewNote[]>(notes);
  const [text, setText] = useState("");
  const [status, setStatus] = useState<SaveStatus>("idle");
  const review = objectionReview({ coverage, patterns, notes: localNotes, canPlaySpan });
  const label = noteFieldLabel(status);

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
      setLocalNotes((current) => [
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
      <h2 id="objections-title" className="text-lg">Objeciones</h2>
      {review.title ? <p>{review.title}</p> : null}
      <ul className="space-y-3">
        {review.patterns.map((pattern) => (
          <li key={pattern.pattern_id}>
            <p>{pattern.category} · {pattern.kind} · {pattern.resolution}</p>
            {pattern.prospect_quotes.map((quote) => <p key={quote}>«{quote}»</p>)}
            {pattern.response ? <p>{pattern.response}</p> : null}
          </li>
        ))}
        {review.notes.map((note) => (
          <li key={note.annotation_id}>
            <p>{note.label}: {note.text}</p>
            <p>{note.offset_ms} ms · {note.author_id}</p>
            {note.playable ? <p>Tramo reproducible</p> : null}
          </li>
        ))}
      </ul>
      <label className="block space-y-2">
        <span>Nota</span>
        <textarea value={text} onChange={(event) => setText(event.target.value)} rows={2} className="w-full rounded-md border p-2" />
      </label>
      <Button type="button" variant="outline" onClick={() => void save()} disabled={status === "syncing"}>
        Guardar nota
      </Button>
      {label ? <p role="status">{label}</p> : null}
    </section>
  );
}
