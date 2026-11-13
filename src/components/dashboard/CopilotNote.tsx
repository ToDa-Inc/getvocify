import { renderCopilotNoteHtml } from "@/lib/copilot-note";

const NOTE = [
  "font-normal tracking-[0.006em] text-foreground [&_strong]:font-medium",
  // The outcome: what a colleague reads first, apart from the facts under it.
  "[&_[data-note-lead]]:mb-3 [&_[data-note-lead]]:border-b [&_[data-note-lead]]:border-border/40 [&_[data-note-lead]]:pb-3",
  "[&_[data-note-lead]]:text-[15px] [&_[data-note-lead]]:font-medium [&_[data-note-lead]]:leading-snug",
  "[&_[data-note-lead]>span]:mb-1 [&_[data-note-lead]>span]:block [&_[data-note-lead]>span]:text-[11px] [&_[data-note-lead]>span]:font-normal [&_[data-note-lead]>span]:tracking-[0.04em] [&_[data-note-lead]>span]:text-muted-foreground",
  "[&_h3]:mb-1.5 [&_h3]:text-[11px] [&_h3]:font-normal [&_h3]:tracking-[0.04em] [&_h3]:text-muted-foreground [&_h3:first-child]:mt-0",
  "[&_p]:mb-2 [&_p:last-child]:mb-0",
  "[&_ul]:my-0 [&_ul]:list-disc [&_ul]:pl-[18px] [&_ul_ul]:mt-1.5 [&_li]:mb-1.5 [&_li]:pl-0.5 [&_li:last-child]:mb-0 [&_li]:marker:text-muted-foreground/50",
].join(" ");

/** `dense`: the memo review pane, where the note shares the screen with the transcript. */
export function CopilotNote({ markdown, dense = false }: { markdown?: string | null; dense?: boolean }) {
  const html = renderCopilotNoteHtml(markdown || "");
  if (!html) return null;
  return (
    <div
      className={`${dense ? "text-[13.5px] leading-[1.55] [&_h3]:mt-4" : "text-[15px] leading-[1.65] [&_h3]:mt-5"} ${NOTE}`}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
