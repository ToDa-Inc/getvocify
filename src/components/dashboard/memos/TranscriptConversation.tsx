import { cn } from "@/lib/utils";
import {
  normalizeDiarizedTranscript,
  parseTranscriptTurns,
  reviewSpeakerLabels,
  speakerDisplayLabel,
  speakerSide,
  turnsForDisplay,
} from "@/lib/transcript-turns";
import { bubblesForTurn } from "@/lib/transcript-bubbles";

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

  return (
    <div className={cn("flex flex-col gap-4 max-h-[500px] overflow-y-auto pr-2 scrollbar-thin", className)}>
      {turns.map((turn, i) => {
        const side = speakerSide(turn.speaker);
        const isYou = side === "s1";
        // Anyone who isn't the rep sits on the left, named once per group.
        const name = side === "other" && turn.speaker ? `Speaker ${turn.speaker.replace(/\D/g, "") || ""}`.trim() : speakerDisplayLabel(turn.speaker, labels);
        return (
          <div
            key={`${turn.speaker}-${i}`}
            className={cn("flex max-w-[85%] flex-col gap-1", isYou ? "self-end items-end" : "self-start items-start")}
          >
            {!isYou && turn.speaker ? (
              <span className="px-1 text-[11px] font-medium text-beige">{name}</span>
            ) : null}
            {bubblesForTurn(turn.text).map((bubble, j) => (
              <div
                key={j}
                className={cn(
                  "whitespace-pre-wrap break-words rounded-2xl px-3.5 py-2 text-[13.5px] leading-relaxed text-foreground",
                  isYou ? "bg-[hsl(36_52%_87%)]" : "bg-[#f3f0eb]",
                )}
              >
                {bubble}
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}
