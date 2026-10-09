import { renderCopilotNoteHtml } from "@/lib/copilot-note";

/** `dense`: the memo review pane, where the note shares the screen with the transcript. */
export function CopilotNote({ markdown, dense = false }: { markdown?: string | null; dense?: boolean }) {
  const html = renderCopilotNoteHtml(markdown || "");
  if (!html) return null;
  return (
    <div
      className={`${dense ? "text-[13.5px] leading-[1.55] [&_h3]:mt-4" : "text-[15px] leading-[1.65] [&_h3]:mt-5"} font-normal tracking-[0.006em] text-foreground [&_h3]:mb-1.5 [&_h3]:text-[11px] [&_h3]:font-normal [&_h3]:tracking-[0.04em] [&_h3]:text-muted-foreground [&_h3]:first:mt-0 [&_ul]:my-0 [&_ul]:pl-4 [&_li]:mb-1 [&_strong]:font-medium`}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
