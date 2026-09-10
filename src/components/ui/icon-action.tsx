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
  onClick: () => void;
  children: React.ReactNode;
};

/** Icon button with tooltip, press scale, and VocifySpinner while the action is in flight. */
export function IconAction({
  label,
  pendingLabel,
  pending = false,
  tone = "default",
  disabled = false,
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
            {pending ? <VocifySpinner size={12} /> : children}
          </button>
        </span>
      </TooltipTrigger>
      <TooltipContent side="top">{tip}</TooltipContent>
    </Tooltip>
  );
}
