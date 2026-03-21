import * as React from "react";
import { format, parseISO, isValid } from "date-fns";
import { CalendarIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import { parseFlexibleDateToIso } from "@/lib/crm-date";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

type Props = {
  value: string;
  onChange: (isoDate: string) => void;
  /** Called when the popover closes (blur-like for parent edit mode). */
  onClose?: () => void;
  className?: string;
};

/**
 * Calendar popover for CRM close / date fields; always emits YYYY-MM-DD.
 */
export function ExtractionDatePicker({ value, onChange, onClose, className }: Props) {
  const [open, setOpen] = React.useState(false);
  const iso = parseFlexibleDateToIso(value) || "";
  const selected = iso && isValid(parseISO(iso)) ? parseISO(iso) : undefined;
  const showRaw = value.trim() && !iso;

  const handleOpenChange = (next: boolean) => {
    setOpen(next);
    if (!next) onClose?.();
  };

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          className={cn(
            "w-full justify-start text-left font-normal h-10 rounded-xl",
            !iso && "text-muted-foreground",
            className,
          )}
        >
          <CalendarIcon className="mr-2 h-4 w-4 shrink-0 opacity-70" />
          <span className="truncate">
            {iso ? format(parseISO(iso), "PPP") : showRaw ? `Invalid: ${value}` : "Pick a date"}
          </span>
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar
          mode="single"
          selected={selected}
          onSelect={(d) => {
            if (d) {
              onChange(format(d, "yyyy-MM-dd"));
              setOpen(false);
              onClose?.();
            }
          }}
          initialFocus
        />
      </PopoverContent>
    </Popover>
  );
}
