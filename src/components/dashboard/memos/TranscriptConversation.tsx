import { cn } from "@/lib/utils";
import {
  normalizeDiarizedTranscript,
  parseTranscriptTurns,
  reviewSpeakerLabels,
  speakerDisplayLabel,
  speakerSide,
} from "@/lib/transcript-turns";

interface TranscriptConversationProps {
  transcript: string;
  contactName?: string | null;
  className?: string;
}

export function TranscriptConversation({
  transcript,
  contactName,
  className,
}: TranscriptConversationProps) {
  const normalized = normalizeDiarizedTranscript(transcript);
  const turns = parseTranscriptTurns(normalized);
  const labels = reviewSpeakerLabels(contactName);
  const hasSpeakers = turns.some((t) => t.speaker);

  if (!turns.length) {
    return <p className="text-sm text-muted-foreground">No transcript available.</p>;
  }

  if (!hasSpeakers) {
    return (
      <div className={cn("prose prose-sm text-muted-foreground max-h-[500px] overflow-y-auto pr-4 scrollbar-thin", className)}>
        {turns.map((turn, i) => (
          <p key={i} className="mb-4 leading-relaxed tracking-tight whitespace-pre-wrap">
            {turn.text}
          </p>
        ))}
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col gap-3 max-h-[500px] overflow-y-auto pr-2 scrollbar-thin", className)}>
      {turns.map((turn, i) => {
        const side = speakerSide(turn.speaker);
        const isYou = side === "s1";
        const isThem = side === "s2";
        return (
          <div
            key={`${turn.speaker}-${i}`}
            className={cn(
              "flex max-w-[92%] flex-col gap-1",
              isYou && "self-start",
              isThem && "self-end items-end",
              side === "other" && "self-stretch max-w-full",
            )}
          >
            {turn.speaker && (
              <span
                className={cn(
                  "px-1 text-[11px] font-normal text-muted-foreground",
                  isThem && "text-beige",
                )}
              >
                {speakerDisplayLabel(turn.speaker, labels)}
              </span>
            )}
            <div
              className={cn(
                "whitespace-pre-wrap break-words rounded-[14px] border px-3.5 py-2.5 text-[13.5px] leading-relaxed text-foreground",
                isYou && "rounded-bl-sm border-border/60 bg-[#f3f0eb]",
                isThem && "rounded-br-sm border-beige/20 bg-beige/10",
                side === "other" && "border-border bg-background",
              )}
            >
              {turn.text}
            </div>
          </div>
        );
      })}
    </div>
  );
}
