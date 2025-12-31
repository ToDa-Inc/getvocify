/**
 * LiveTranscript Component
 * 
 * Displays real-time transcription with visual distinction between
 * final (confirmed) and interim (in-progress) text.
 * Includes auto-scrolling to keep the latest text in view.
 */

import { useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';
import type { ProviderTranscript } from '../types';

interface LiveTranscriptProps {
  /** Primary interim transcript */
  interimTranscript: string;
  /** Primary final transcript */
  finalTranscript: string;
  /** Multi-provider transcripts for side-by-side view */
  providerTranscripts?: Record<string, ProviderTranscript>;
  /** Whether transcription is active */
  isActive: boolean;
  /** Optional className for styling */
  className?: string;
}

export function LiveTranscript({
  finalTranscript,
  interimTranscript,
  providerTranscripts,
  isActive,
  className,
}: LiveTranscriptProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const hasContent = finalTranscript || interimTranscript || (providerTranscripts && Object.values(providerTranscripts).some(p => p.full));

  // Auto-scroll logic
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  }, [finalTranscript, interimTranscript, providerTranscripts]);

  // If we have multi-provider data, show comparison mode
  const showComparison = providerTranscripts && Object.keys(providerTranscripts).length > 1;

  if (showComparison) {
    return (
      <div className={cn("grid grid-cols-1 md:grid-cols-2 gap-4", className)}>
        {Object.entries(providerTranscripts).map(([provider, data]) => (
          <div key={provider} className="flex flex-col gap-2">
            <div className="flex items-center justify-between px-2">
              <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/50">
                {provider}
              </span>
              {isActive && (
                <div className="h-1 w-1 rounded-full bg-primary animate-pulse" />
              )}
            </div>
            <div className={cn(
              "relative min-h-[140px] max-h-[240px] overflow-y-auto rounded-xl border bg-muted/10 p-4 text-sm leading-relaxed",
              isActive && "border-primary/20 bg-primary/[0.02]"
            )}>
              <span className="text-foreground">{data.final}</span>
              <span className="text-muted-foreground/50 italic"> {data.interim}</span>
              {isActive && (
                <span className="ml-1 inline-block h-3 w-0.5 bg-primary animate-pulse align-middle" />
              )}
            </div>
          </div>
        ))}
      </div>
    );
  }

  // Fallback to original single view if no comparison
  return (
    <div
      ref={scrollRef}
      className={cn(
        'relative min-h-[160px] max-h-[300px] overflow-y-auto rounded-2xl border bg-muted/20 p-6',
        'transition-all duration-500 ease-in-out scrollbar-thin scrollbar-thumb-muted-foreground/20',
        isActive && 'border-primary/30 ring-1 ring-primary/10 shadow-inner-sm',
        className
      )}
    >
      {!hasContent ? (
        <div className="flex h-full flex-col items-center justify-center gap-3 animate-in fade-in duration-700">
          <div className="h-1.5 w-1.5 rounded-full bg-primary/40 animate-pulse" />
          <p className="text-sm font-medium text-muted-foreground/60 tracking-tight">
            {isActive
              ? 'Start speaking to see the magic happen...'
              : 'Your transcript will appear here'}
          </p>
        </div>
      ) : (
        <div className="relative space-y-4 text-lg md:text-xl font-medium leading-relaxed tracking-tight">
          <div className="inline">
            <span className="text-foreground">{finalTranscript}</span>
            <span className="text-muted-foreground/50 transition-all duration-500">
              {finalTranscript ? ' ' : ''}
              {interimTranscript}
            </span>
            {isActive && (
              <span className="ml-1.5 inline-block h-6 w-1 rounded-full bg-primary align-middle animate-pulse" />
            )}
          </div>
        </div>
      )}
    </div>
  );
}


