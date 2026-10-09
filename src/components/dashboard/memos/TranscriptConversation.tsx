import { cn } from "@/lib/utils";
import {
  normalizeDiarizedTranscript,
  parseTranscriptTurns,
  reviewSpeakerLabels,
  speakerDisplayLabel,
  speakerSide,
  turnsForDisplay,
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
  const turns = turnsForDisplay(parseTranscriptTurns(normalized));
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

  // Same reading as the desktop meeting pill: you on the right in warm paper, them on the left
  // in grey, a name only where the speaker changes.
  return (
    <div className={cn("flex flex-col max-h-[500px] overflow-y-auto overflow-x-hidden pr-2 scrollbar-thin", className)}>
      {turns.map((turn, i) => {
        const side = speakerSide(turn.speaker);
        const isYou = side === "s1";
        const changed = i === 0 || speakerSide(turns[i - 1].speaker) !== side;
        return (
          <div
            key={`${turn.speaker}-${i}`}
            className={cn(
              "flex max-w-[82%] min-w-0 flex-col gap-1",
              isYou ? "self-end items-end" : "self-start items-start",
              changed && i > 0 ? "mt-3" : i > 0 ? "mt-1" : "",
            )}
          >
            {!isYou && changed && turn.speaker ? (
              <span className="px-1 text-[11px] font-medium leading-none text-beige">
                {speakerDisplayLabel(turn.speaker, labels)}
              </span>
            ) : null}
            <div
              className={cn(
                "whitespace-pre-wrap break-words [overflow-wrap:anywhere] rounded-[14px] px-3 py-1.5 text-[12.5px] leading-normal text-foreground",
                isYou ? "bg-beige/15 dark:bg-beige/20" : "bg-foreground/[0.05]",
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
