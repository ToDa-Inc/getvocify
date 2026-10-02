import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import type { AssistCard } from "@/lib/live-assist";
import { cn } from "@/lib/utils";

/** Side column during a meeting: quiet until they push back, then one card at a time. */
export function LiveAssistPanel({
  active,
  earlier,
  thinking,
  enabled,
  onEnabledChange,
}: {
  active: AssistCard | null;
  earlier: AssistCard[];
  thinking: boolean;
  enabled: boolean;
  onEnabledChange: (enabled: boolean) => void;
}) {
  return (
    <aside aria-label="Live assist" className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-[15px] tracking-tight text-foreground">Live assist</span>
          <span className="rounded-md bg-beige/10 px-1.5 py-px text-[10px] font-medium text-beige">Beta</span>
        </div>
        <Switch checked={enabled} onCheckedChange={onEnabledChange} aria-label="Live assist" />
      </div>
      <p className="-mt-3 text-[11px] text-muted-foreground/80">Not from your playbook yet. General objection help.</p>

      {/* Reserved line so the status never pushes the cards around. */}
      <p className="flex h-5 items-center gap-2 text-xs text-muted-foreground" aria-live="polite">
        {enabled ? (
          <>
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full bg-beige transition-opacity",
                thinking ? "animate-pulse motion-reduce:animate-none" : "opacity-40",
              )}
            />
            {thinking ? "Reading their answer…" : "Only shows when they push back."}
          </>
        ) : (
          "Off. Turn on for help when they push back."
        )}
      </p>

      {enabled && active ? <NewestCard key={active.id} card={active} /> : null}

      {enabled && earlier.length ? (
        <div className="space-y-2">
          <p className="text-[11px] font-medium text-muted-foreground">Earlier</p>
          {earlier.map((card) => (
            <EarlierCard key={card.id} card={card} />
          ))}
        </div>
      ) : null}
    </aside>
  );
}

/** Objections read in Vocify beige; product questions in a quiet neutral. */
function KindChip({ card }: { card: AssistCard }) {
  return (
    <span
      className={cn(
        "inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-medium",
        card.kind === "question" ? "bg-secondary text-foreground/70" : "bg-beige/10 text-beige",
      )}
    >
      {card.label}
    </span>
  );
}

function NewestCard({ card }: { card: AssistCard }) {
  const [details, setDetails] = useState(false);
  const hasDetails = Boolean(card.why || card.avoid);
  return (
    <div className="space-y-3 rounded-2xl border border-beige/20 bg-card p-4 shadow-[0_8px_24px_-16px_hsl(30_30%_12%/0.25)] animate-in fade-in slide-in-from-top-2 duration-300 motion-reduce:animate-none">
      <KindChip card={card} />
      {card.stage === "draft" ? (
        <div className="space-y-2">
          {card.bridge ? (
            // Something natural to say at once while the answer is written.
            <p className="text-[15px] italic leading-snug text-foreground/80">“{card.bridge}”</p>
          ) : null}
          <p className="flex items-center gap-2 text-xs text-muted-foreground" aria-live="polite">
            <span className="flex gap-1" aria-hidden>
              {[0, 160, 320].map((delay) => (
                <span
                  key={delay}
                  className="h-1 w-1 rounded-full bg-foreground/40 animate-pulse motion-reduce:animate-none"
                  style={{ animationDelay: `${delay}ms` }}
                />
              ))}
            </span>
            Preparing a reply…
          </p>
        </div>
      ) : (
        <div key="ready" className="animate-in fade-in duration-300 motion-reduce:animate-none">
          {card.bridge ? <p className="mb-1 text-[13px] italic leading-snug text-muted-foreground">“{card.bridge}”</p> : null}
          <p className="mb-1 text-[11px] font-medium text-muted-foreground">
            {card.kind === "question" ? "Answer" : "Say this"}
          </p>
          <p className="text-[15px] font-medium leading-snug text-foreground">{card.sayThis}</p>
        </div>
      )}
      {card.thenAsk ? (
        <div className="rounded-xl bg-cream/80 px-3 py-2">
          <p className="mb-0.5 text-[11px] font-medium text-muted-foreground">Next question</p>
          <p className="text-[13px] leading-snug text-foreground">{card.thenAsk}</p>
        </div>
      ) : null}
      {hasDetails ? (
        <>
          <button
            type="button"
            onClick={() => setDetails((open) => !open)}
            aria-expanded={details}
            className="flex items-center gap-1 text-[11px] font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            <ChevronDown className={cn("h-3 w-3 transition-transform", details && "rotate-180")} />
            Why it works
          </button>
          {details ? (
            <div className="space-y-2 text-xs leading-relaxed text-muted-foreground animate-in fade-in duration-200">
              {card.why ? <p>{card.why}</p> : null}
              {card.avoid ? (
                <p>
                  <span className="font-medium text-destructive/80">Don&apos;t say: </span>
                  {card.avoid}
                </p>
              ) : null}
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function EarlierCard({ card }: { card: AssistCard }) {
  const [open, setOpen] = useState(false);
  return (
    <button
      type="button"
      onClick={() => setOpen((value) => !value)}
      aria-expanded={open}
      className="block w-full rounded-xl border border-border/60 bg-card/60 px-3 py-2 text-left transition-colors hover:bg-card"
    >
      <span className={cn("text-[11px] font-medium", card.kind === "question" ? "text-foreground/60" : "text-beige")}>
        {card.label}
      </span>
      <p className={cn("text-[13px] leading-snug text-muted-foreground", !open && "line-clamp-2")}>{card.sayThis}</p>
      {open && card.thenAsk ? <p className="mt-1 text-xs text-muted-foreground">→ {card.thenAsk}</p> : null}
    </button>
  );
}
