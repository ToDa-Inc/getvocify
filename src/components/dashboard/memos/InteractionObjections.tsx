import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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

  const resolutionTone: Record<ReviewPattern["resolution"], string> = {
    resolved: "bg-success/10 text-success",
    open: "bg-warning/15 text-warning",
    unknown: "bg-foreground/[0.05] text-muted-foreground",
  };
  const objections = review.patterns;

  return (
    <div className="space-y-4 text-[13px] text-foreground">
      {/* The rep's own note: one line, a real button, Enter saves. */}
      <div className="space-y-2">
        <form
          className="flex items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <Input
            aria-label={p.noteLabel}
            placeholder={p.notePlaceholder}
            value={text}
            onChange={(event) => setText(event.target.value)}
            className="h-8 flex-1 rounded-xl border-border/60 bg-card px-3 text-[13px] md:text-[13px]"
          />
          <Button
            type="submit"
            disabled={status === "syncing" || !text.trim()}
            className="h-8 shrink-0 rounded-full bg-beige px-3.5 text-[13px] font-normal text-cream hover:bg-beige/90"
          >
            {p.noteSaveButton}
          </Button>
        </form>
        {label ? <p role="status" className="px-1 text-[12px] text-muted-foreground">{label}</p> : null}
        {review.notes.length ? (
          <ul className="space-y-1 px-1">
            {review.notes.map((note) => (
              <li key={note.annotation_id} className="flex gap-2 text-[12.5px]">
                <span className="shrink-0 tabular-nums text-muted-foreground">{clock(note.offset_ms)}</span>
                <span className="min-w-0 break-words">{note.text}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      <section aria-labelledby="objections-title" className="space-y-2.5 rounded-xl border border-border/50 bg-secondary/5 px-3.5 py-3">
        <div className="flex items-center gap-2">
          <h2 id="objections-title" className="text-[13px] font-medium">{p.teamHeadingObjections}</h2>
          {objections.length ? (
            <span className="rounded-full bg-foreground/[0.06] px-1.5 text-[11px] tabular-nums text-muted-foreground">{objections.length}</span>
          ) : null}
        </div>
        {review.title ? <p className="text-[12.5px] text-muted-foreground">{review.title}</p> : null}
        {objections.length ? (
          <ul className="divide-y divide-border/50">
            {objections.map((pattern) => (
              <li key={pattern.pattern_id} className="space-y-1 py-2 first:pt-0 last:pb-0">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-medium">{patternCategoryLabel(pattern.category, p)}</span>
                  <span className={`rounded-full px-2 py-px text-[11px] ${resolutionTone[pattern.resolution]}`}>
                    {patternResolutionLabel(pattern.resolution, p)}
                  </span>
                  {pattern.kind !== "objection" ? (
                    <span className="text-[11px] text-muted-foreground">{patternKindLabel(pattern.kind, p)}</span>
                  ) : null}
                </div>
                {pattern.prospect_quotes.map((quote) => (
                  <p key={quote} className="text-[12.5px] italic text-muted-foreground">
                    {p.prospectQuote.replace("{quote}", quote)}
                  </p>
                ))}
                {pattern.response ? <p className="text-[12.5px]">{pattern.response}</p> : null}
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    </div>
  );
}

/** Where in the call a note was taken, as m:ss. */
function clock(offsetMs: number): string {
  const total = Math.max(0, Math.round((offsetMs || 0) / 1000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}
