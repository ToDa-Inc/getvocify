import type { ObjectionSuggestion } from "../types";

interface SuggestionCardProps {
  suggestion: ObjectionSuggestion | null;
  isLoading: boolean;
  rawStream?: string;
  lastTurn?: string | null;
  latencyMs?: number | null;
  model?: string | null;
}

export function SuggestionCard({
  suggestion,
  isLoading,
  rawStream,
  lastTurn,
  latencyMs,
  model,
}: SuggestionCardProps) {
  if (!suggestion && !isLoading) {
    return (
      <div className="rounded-3xl border border-dashed border-border/60 bg-white/60 p-8 text-center">
        <p className="text-sm font-bold text-muted-foreground">
          Waiting for the prospect to finish speaking…
        </p>
        <p className="mt-2 text-xs text-muted-foreground/80">
          After your pitch, keep the phone on speaker. When they object, coaching appears here.
        </p>
      </div>
    );
  }

  if (isLoading && !suggestion) {
    return (
      <div className="rounded-3xl border border-beige/30 bg-white p-8 shadow-soft">
        <div className="flex items-center gap-3">
          <div className="h-3 w-3 animate-pulse rounded-full bg-beige" />
          <p className="text-sm font-bold text-beige">Coaching in real time…</p>
        </div>
        {lastTurn && (
          <p className="mt-4 text-xs text-muted-foreground line-clamp-2">
            Heard: “{lastTurn}”
          </p>
        )}
        {rawStream && (
          <pre className="mt-4 max-h-24 overflow-hidden text-[10px] text-muted-foreground/60 whitespace-pre-wrap">
            {rawStream.slice(0, 400)}
          </pre>
        )}
      </div>
    );
  }

  if (!suggestion) return null;

  const badge = suggestion.is_objection
    ? suggestion.objection_type.replace(/_/g, " ")
    : "nudge";

  return (
    <div className="rounded-3xl border border-beige/20 bg-white p-6 md:p-8 shadow-medium space-y-5">
      <div className="flex flex-wrap items-center gap-2 justify-between">
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-beige/15 px-3 py-1 text-[10px] font-black uppercase tracking-widest text-beige">
            {badge}
          </span>
          {suggestion.is_objection && (
            <span className="rounded-full bg-foreground/5 px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              {suggestion.urgency}
            </span>
          )}
        </div>
        <div className="text-[10px] font-medium text-muted-foreground">
          {latencyMs != null && <span>{latencyMs}ms</span>}
          {model && <span className="ml-2 opacity-60">{model}</span>}
        </div>
      </div>

      {lastTurn && (
        <p className="text-xs text-muted-foreground">
          <span className="font-bold text-foreground/70">They said: </span>
          “{lastTurn}”
        </p>
      )}

      <div>
        <p className="text-[10px] font-black uppercase tracking-widest text-beige mb-2">
          Say this
        </p>
        <p className="text-xl md:text-2xl font-bold tracking-tight text-foreground leading-snug">
          {suggestion.say_this}
        </p>
      </div>

      {suggestion.next_question && (
        <div className="rounded-2xl bg-cream/80 px-4 py-3">
          <p className="text-[10px] font-black uppercase tracking-widest text-muted-foreground mb-1">
            Next question
          </p>
          <p className="text-sm font-semibold text-foreground">{suggestion.next_question}</p>
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        {suggestion.why_it_works && (
          <div>
            <p className="text-[10px] font-black uppercase tracking-widest text-muted-foreground mb-1">
              Why it works
            </p>
            <p className="text-xs text-muted-foreground leading-relaxed">{suggestion.why_it_works}</p>
          </div>
        )}
        {suggestion.dont_say && (
          <div>
            <p className="text-[10px] font-black uppercase tracking-widest text-red-500/80 mb-1">
              Don&apos;t say
            </p>
            <p className="text-xs text-muted-foreground leading-relaxed">{suggestion.dont_say}</p>
          </div>
        )}
      </div>
    </div>
  );
}
