/**
 * LiveTranscript Component
 * 
 * Displays real-time transcription with visual distinction between
 * final (confirmed) and interim (in-progress) text.
 * Includes auto-scrolling to keep the latest text in view.
 */

import { useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';

interface LiveTranscriptProps {
  /** Primary interim transcript */
  interimTranscript: string;
  /** Primary final transcript */
  finalTranscript: string;
  /** Whether transcription is active */
  isActive: boolean;
  /** Optional className for styling */
  className?: string;
}

export function LiveTranscript({
  finalTranscript,
  interimTranscript,
  isActive,
  className,
}: LiveTranscriptProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const hasContent = Boolean(finalTranscript || interimTranscript);

  // Auto-scroll logic
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  }, [finalTranscript, interimTranscript]);

  return (
    <div
      ref={scrollRef}
      className={cn(
        'relative min-h-[140px] max-h-[260px] overflow-y-auto rounded-2xl border bg-muted/20 p-5',
        'transition-all duration-300 ease-in-out scrollbar-thin scrollbar-thumb-muted-foreground/20',
        isActive && 'border-primary/30 ring-1 ring-primary/10 shadow-xs',
        className
      )}
    >
      {!hasContent ? (
        <div className="flex h-full min-h-[100px] flex-col items-center justify-center gap-2.5 animate-in fade-in duration-500 text-center">
          <div className="h-2 w-2 rounded-full bg-primary/40 animate-pulse" />
          <p className="text-xs font-medium text-muted-foreground/70">
            {isActive
              ? 'Listening... Start speaking to see live transcription'
              : 'Your transcript will appear here'}
          </p>
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
  );
}
