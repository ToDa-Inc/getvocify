/**
 * LiveTranscript Component
 *
 * Displays real-time transcription with visual distinction between
 * final (confirmed) and interim (in-progress) text.
 * Follows the latest text only while the reader is at the bottom; scrolling up
 * to reread holds position and offers a way back to the live edge.
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { ArrowDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { MeetingDisplayTurn } from '@/lib/meeting-transcript';
import { cn } from '@/lib/utils';

/** Distance from the bottom that still counts as "reading live". */
const FOLLOW_SLACK_PX = 32;

interface LiveTranscriptProps {
  /** Primary interim transcript */
  interimTranscript: string;
  /** Primary final transcript */
  finalTranscript: string;
  /** Speaker-separated paragraphs; replaces final/interim text when given */
  turns?: MeetingDisplayTurn[];
  /** Whether transcription is active */
  isActive: boolean;
  /** Live STT error, if the socket or provider failed */
  error?: string | null;
  /** Empty-state copy while listening */
  listeningHint?: string;
  /** Optional className for styling */
  className?: string;
}

export function LiveTranscript({
  finalTranscript,
  interimTranscript,
  turns,
  isActive,
  error,
  listeningHint = 'Listening... Start speaking to see live transcription',
  className,
}: LiveTranscriptProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const followRef = useRef(true);
  const [following, setFollowing] = useState(true);
  const hasContent = turns ? turns.length > 0 : Boolean(finalTranscript || interimTranscript);

  const jumpToLive = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    followRef.current = true;
    setFollowing(true);
  }, []);

  // Before paint, so new text never flashes below the fold first.
  useLayoutEffect(() => {
    if (followRef.current) jumpToLive();
  }, [finalTranscript, interimTranscript, turns, jumpToLive]);

  useEffect(() => {
    if (!isActive) setFollowing(true);
  }, [isActive]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight <= FOLLOW_SLACK_PX;
    followRef.current = atBottom;
    setFollowing(atBottom);
  };

  return (
    <div className="relative">
      <div
        ref={scrollRef}
        onScroll={onScroll}
        className={cn(
          'relative min-h-[140px] max-h-[260px] overflow-y-auto rounded-2xl border bg-muted/20 p-5',
          'transition-[border-color,box-shadow] duration-300 ease-in-out scrollbar-thin scrollbar-thumb-muted-foreground/20',
          isActive && 'border-primary/30 ring-1 ring-primary/10 shadow-xs',
          className
        )}
      >
        {!hasContent ? (
          <div className="flex h-full min-h-[100px] flex-col items-center justify-center gap-2.5 animate-in fade-in duration-500 motion-reduce:animate-none text-center">
            <div className="h-2 w-2 rounded-full bg-primary/40 animate-pulse motion-reduce:animate-none" />
            <p className="text-xs font-medium text-muted-foreground/70">
              {error
                ? error
                : isActive
                  ? listeningHint
                  : 'Your transcript will appear here'}
            </p>
          </div>
        ) : turns ? (
          <div className="space-y-4 text-base md:text-lg font-normal leading-relaxed tracking-tight text-foreground">
            {turns.map((turn) => (
              <p key={turn.key} className="animate-in fade-in duration-300 motion-reduce:animate-none">
                {turn.label ? (
                  <span className="block mb-0.5 text-xs font-medium tracking-normal text-muted-foreground">
                    {turn.label}
                  </span>
                ) : null}
                <span>{turn.text}</span>
                {turn.pending ? (
                  <span className="text-muted-foreground/60 italic">
                    {turn.text ? ' ' : ''}
                    {turn.pending}
                  </span>
                ) : null}
              </p>
            ))}
          </div>
        ) : (
          <div className="relative space-y-2 text-base md:text-lg font-normal leading-relaxed tracking-tight text-foreground">
            <span className="text-foreground">{finalTranscript}</span>
            <span className="text-muted-foreground/60 italic transition-all duration-300">
              {finalTranscript ? ' ' : ''}
              {interimTranscript}
            </span>
            {isActive && (
              <span className="ml-1.5 inline-block h-4 w-1 rounded-full bg-primary align-middle animate-pulse" />
            )}
          </div>
        )}
      </div>
      {isActive && hasContent && !following ? (
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={jumpToLive}
          className="absolute bottom-3 left-1/2 -translate-x-1/2 h-7 gap-1.5 px-3 text-xs shadow-sm animate-in fade-in duration-200 motion-reduce:animate-none"
        >
          <ArrowDown className="h-3 w-3" />
          Back to live
        </Button>
      ) : null}
    </div>
  );
}
