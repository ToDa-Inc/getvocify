import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Minus, Plus } from "lucide-react";
import { toast } from "sonner";
import { adminApi, adminKeys } from "@/features/admin/api";

function apiErrorMessage(error: unknown, fallback: string) {
  if (error && typeof error === "object" && "data" in error) {
    const detail = (error as { data?: { detail?: unknown } }).data?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

type LicenseCellProps = {
  companyId: string;
  seatLimit: number;
  seatsUsed: number;
};

export const LicenseCell = ({ companyId, seatLimit, seatsUsed }: LicenseCellProps) => {
  const queryClient = useQueryClient();
  const [value, setValue] = useState(seatLimit);
  const min = Math.max(1, seatsUsed);

  useEffect(() => {
    setValue(seatLimit);
  }, [seatLimit]);

  const mutation = useMutation({
    mutationFn: (seatLimitNext: number) =>
      adminApi.updateCompany(companyId, { seat_limit: seatLimitNext }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminKeys.all });
    },
    onError: (error) => {
      setValue(seatLimit);
      toast.error(apiErrorMessage(error, "Could not update licenses"));
    },
  });

  const commit = (next: number) => {
    const clamped = Math.max(min, next);
    setValue(clamped);
    if (clamped === seatLimit) return;
    mutation.mutate(clamped);
  };

  return (
    <div className="inline-flex items-center gap-2.5">
      <div className="inline-flex items-center rounded-full border border-border/40 bg-secondary/5 p-0.5">
        <button
          type="button"
          aria-label="Decrease licenses"
          disabled={mutation.isPending || value <= min}
          onClick={() => commit(value - 1)}
          className="h-7 w-7 rounded-full text-muted-foreground hover:bg-secondary/40 hover:text-foreground disabled:pointer-events-none disabled:opacity-30"
        >
          <Minus className="h-3.5 w-3.5 mx-auto" />
        </button>
        <input
          type="number"
          min={min}
          aria-label="License count"
          disabled={mutation.isPending}
          value={value}
          onChange={(e) => setValue(Math.max(1, Number(e.target.value) || 1))}
          onBlur={() => commit(value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") e.currentTarget.blur();
            if (e.key === "Escape") {
              setValue(seatLimit);
              e.currentTarget.blur();
            }
          }}
          className="h-7 w-8 bg-transparent text-center text-[13px] tabular-nums text-foreground outline-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none disabled:opacity-50"
        />
        <button
          type="button"
          aria-label="Increase licenses"
          disabled={mutation.isPending}
          onClick={() => commit(value + 1)}
          className="h-7 w-7 rounded-full text-muted-foreground hover:bg-secondary/40 hover:text-foreground disabled:pointer-events-none disabled:opacity-30"
        >
          <Plus className="h-3.5 w-3.5 mx-auto" />
        </button>
      </div>
      <span className="text-[11px] text-muted-foreground whitespace-nowrap">
        {seatsUsed} used
      </span>
    </div>
  );
};
