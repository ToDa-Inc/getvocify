import { renderCopilotNoteHtml } from "@/lib/copilot-note";

export function CopilotNote({ markdown }: { markdown?: string | null }) {
  const html = renderCopilotNoteHtml(markdown || "");
  if (!html) return null;
  return (
    <div
      className="text-[15px] font-normal leading-[1.65] tracking-[0.006em] text-foreground [&_h3]:mt-5 [&_h3]:mb-1.5 [&_h3]:text-[11px] [&_h3]:font-normal [&_h3]:tracking-[0.04em] [&_h3]:text-muted-foreground [&_h3]:first:mt-0 [&_ul]:my-0 [&_ul]:pl-4 [&_li]:mb-1 [&_strong]:font-medium"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
