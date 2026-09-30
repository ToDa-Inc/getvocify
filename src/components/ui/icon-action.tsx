import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { VocifySpinner } from "@/components/ui/vocify-loader";

type IconActionProps = {
  label: string;
  pendingLabel?: string;
  pending?: boolean;
  tone?: "default" | "danger";
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
            disabled={disabled || pending}
            onClick={onClick}
            className={cn(
              THEME_TOKENS.interaction.iconButton,
              THEME_TOKENS.motion.tapScale,
              tone === "danger" && THEME_TOKENS.interaction.iconDanger,
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
