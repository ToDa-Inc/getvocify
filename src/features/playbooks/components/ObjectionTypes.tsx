import { Layers } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useLanguage } from "@/lib/i18n";
import { joinNames } from "@/lib/objection-types";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

/**
 * Where else an objection also appears, beside the objection: an icon (with the number of types when
 * it is in more than one) that opens the list of types to tick. Each type keeps its own copy of the
 * objection; ticking adds or removes it there, and one action puts this answer on the ticked ones.
 */
export function ObjectionTypes({
  current,
  appearsIn,
  allTypes,
  names,
  canEdit,
  busy = false,
  onToggle,
  onCopyAnswer,
}: {
  current: string;
  /** Type keys that hold this objection, `current` included. */
  appearsIn: string[];
  allTypes: string[];
  names: Record<string, string>;
  canEdit: boolean;
  /** A change is being saved: nothing can be ticked or copied meanwhile. */
  busy?: boolean;
  onToggle: (type: string, on: boolean) => void;
  onCopyAnswer: (types: string[]) => void;
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const others = allTypes.filter((type) => type !== current && appearsIn.includes(type));
  const elsewhere = others.length > 0;
  if (!canEdit && !elsewhere) return null;

  const nameOf = (type: string) => names[type] ?? type;
  const label = elsewhere ? copy.objTypesAlsoIn.replace("{names}", joinNames(others.map(nameOf), copy.objTypesAnd)) : copy.objTypesUseElsewhere;

  return (
    <Popover>
      <Tooltip>
        <TooltipTrigger asChild>
          <PopoverTrigger asChild>
            <button
              type="button"
              aria-label={label}
              className={cn(THEME_TOKENS.interaction.iconButton, THEME_TOKENS.motion.tapScale, elsewhere && "w-auto gap-1 px-2.5")}
            >
              <Layers size={16} strokeWidth={1.5} />
              {elsewhere ? <span className="text-xs tabular-nums">{appearsIn.length}</span> : null}
            </button>
          </PopoverTrigger>
        </TooltipTrigger>
        <TooltipContent side="top">{label}</TooltipContent>
      </Tooltip>
      <PopoverContent align="end" className="w-64">
        {canEdit ? (
          <div className="space-y-3">
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">{copy.objTypesHint}</p>
              <p className="text-xs text-muted-foreground/70">{copy.objTypesDraftNote}</p>
            </div>
            <ul className="space-y-2">
              {allTypes.map((type) => (
                <li key={type}>
                  <label className={cn("flex items-center gap-2.5 text-sm", type === current ? "text-muted-foreground" : "cursor-pointer")}>
                    <Checkbox
                      checked={appearsIn.includes(type)}
                      disabled={type === current || busy}
                      onCheckedChange={(value) => onToggle(type, value === true)}
                    />
                    <span>{nameOf(type)}</span>
                  </label>
                </li>
              ))}
            </ul>
            <Button type="button" variant="quiet" size="text" className="-ml-2" disabled={!elsewhere || busy} onClick={() => onCopyAnswer(others)}>
              {copy.objTypesCopyAnswer}
            </Button>
          </div>
        ) : (
          <ul className="space-y-1.5 text-sm">
            {allTypes.filter((type) => appearsIn.includes(type)).map((type) => (
              <li key={type}>{nameOf(type)}</li>
            ))}
          </ul>
        )}
      </PopoverContent>
    </Popover>
  );
}
