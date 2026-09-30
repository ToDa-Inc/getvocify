import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import { toast } from "sonner";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { memoKeys, memosApi } from "@/features/memos/api";
import type { Memo } from "@/features/memos/types";
import { errorCode } from "@/features/playbooks/api";
import { INTERNAL_KEY, retagOptions, type TypeOption } from "@/lib/interactions";
import { useLanguage } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export const chipClass = "inline-flex h-6 items-center gap-1 rounded-md px-2 text-xs font-medium";

/**
 * The row's type, as a menu: one click retags the memo to another active type or to "Interna". The chip
 * changes at once and goes back if the server refuses (a type with no live playbook, a network error).
 */
export function TypeChip({
  memoId,
  chip,
  options,
}: {
  memoId: string;
  chip: { key: string; label: string };
  options: TypeOption[];
}) {
  const { t } = useLanguage();
  const copy = t.product.interactions;
  const queryClient = useQueryClient();

  const retag = useMutation({
    mutationFn: (option: TypeOption) => memosApi.setType(memoId, option.key),
    onMutate: async (option) => {
      await queryClient.cancelQueries({ queryKey: memoKeys.lists() });
      const before = queryClient.getQueriesData<Memo[]>({ queryKey: memoKeys.lists() });
      queryClient.setQueriesData<Memo[]>({ queryKey: memoKeys.lists() }, (rows) =>
        rows?.map((row) => (row.id === memoId ? { ...row, salesMotionKey: option.key } : row)),
      );
      return { before };
    },
    onError: (error, _option, context) => {
      context?.before.forEach(([key, rows]) => queryClient.setQueryData(key, rows));
      toast.error(errorCode(error) === "not_published" ? copy.retagNotPublished : copy.retagFailed);
    },
    onSuccess: (_result, option) => {
      toast(copy.retagged.replace("{name}", option.label));
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: memoKeys.lists() });
      void queryClient.invalidateQueries({ queryKey: memoKeys.detail(memoId) });
      void queryClient.invalidateQueries({ queryKey: ["memo-playbook", memoId] });
    },
  });

  // Only types that can score (a live playbook) and "Interna". The chip itself still names whatever
  // the memo carries, even a paused or deleted type.
  const choices = retagOptions(options);
  const types = choices.filter((option) => option.key !== INTERNAL_KEY);
  const internal = choices.find((option) => option.key === INTERNAL_KEY);
  const pick = (key: string) => {
    const option = choices.find((candidate) => candidate.key === key);
    if (option && option.key !== chip.key) retag.mutate(option);
  };

  return (
    <DropdownMenu>
      <Tooltip>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              aria-label={`${copy.changeType}: ${chip.label}`}
              disabled={retag.isPending}
              className={cn(
                chipClass,
                "max-w-[12rem] bg-beige/10 text-beige transition-colors duration-150 hover:bg-beige/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none disabled:opacity-60",
              )}
            >
              <span className="truncate">{chip.label}</span>
              <ChevronDown aria-hidden className="h-3 w-3 shrink-0 opacity-60" />
            </button>
          </DropdownMenuTrigger>
        </TooltipTrigger>
        <TooltipContent side="top">{copy.changeType}</TooltipContent>
      </Tooltip>
      <DropdownMenuContent align="start" className="max-h-72 overflow-y-auto">
        <DropdownMenuRadioGroup value={chip.key} onValueChange={pick}>
          {types.map((option) => (
            <DropdownMenuRadioItem key={option.key} value={option.key}>
              {option.label}
            </DropdownMenuRadioItem>
          ))}
          {internal ? (
            <>
              {types.length ? <DropdownMenuSeparator /> : null}
              <DropdownMenuRadioItem value={internal.key}>{internal.label}</DropdownMenuRadioItem>
            </>
          ) : null}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
