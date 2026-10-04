import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { VocifySpinner } from "@/components/ui/vocify-loader";

type IconActionProps = {
  label: string;
  pendingLabel?: string;
  pending?: boolean;
  /** `primary`: the filled beige action of a surface (send, record). One per block. */
  tone?: "default" | "danger" | "primary";
  /** A toggle ("mute"): shows the held state and sets `aria-pressed`. */
  pressed?: boolean;
  disabled?: boolean;
  /** Shown while pending instead of the spinner, e.g. `<AnimIcon name="refresh" state="busy" />`. */
  pendingIcon?: React.ReactNode;
  /** A keyboard shortcut shown in the tooltip only; the accessible name stays `label`. */
  shortcut?: string;
  onClick: () => void;
  children: React.ReactNode;
};

/** Icon button with tooltip, press scale, and VocifySpinner (or `pendingIcon`) while the action is in flight. */
export function IconAction({
  label,
  pendingLabel,
  pending = false,
  tone = "default",
  pressed,
  disabled = false,
  pendingIcon,
  shortcut,
  onClick,
  children,
}: IconActionProps) {
  const tip = pending ? (pendingLabel ?? label) : label;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex">
          <button
            type="button"
            aria-label={tip}
            aria-pressed={pressed}
            disabled={disabled || pending}
            onClick={onClick}
            className={cn(
              THEME_TOKENS.interaction.iconButton,
              THEME_TOKENS.motion.tapScale,
              tone === "danger" && THEME_TOKENS.interaction.iconDanger,
              tone === "primary" &&
                "btn-glow bg-beige text-cream hover:bg-beige/90 hover:text-cream disabled:bg-muted-foreground/20 disabled:text-muted-foreground disabled:opacity-100 disabled:shadow-none",
              pressed && "bg-foreground text-background hover:bg-foreground/90 hover:text-background",
            )}
          >
            {pending ? (pendingIcon ?? <VocifySpinner size={12} />) : children}
          </button>
        </span>
      </TooltipTrigger>
      <TooltipContent side="top">
        {tip}
        {shortcut && !pending ? <kbd className="ml-1.5 font-sans text-muted-foreground">{shortcut}</kbd> : null}
      </TooltipContent>
    </Tooltip>
  );
}
