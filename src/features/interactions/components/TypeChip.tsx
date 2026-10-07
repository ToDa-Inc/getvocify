import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import { toast } from "sonner";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { memoKeys, memosApi } from "@/features/memos/api";
import type { Memo } from "@/features/memos/types";
import { errorCode, playbooksApi } from "@/features/playbooks/api";
import { PLAYBOOKS_KEY } from "@/features/playbooks/keys";
import { INTERNAL_KEY, retagOptions, type TypeOption } from "@/lib/interactions";
import { LIVE_CHANNELS, byChannel, channelTypeOptions, type LiveChannel } from "@/lib/type-channels";
import { useLanguage } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export const chipClass = "inline-flex h-6 items-center gap-1 rounded-full px-2.5 text-xs font-medium";

/**
 * The row's type, as a menu: one click retags the memo to another active type or to "Interna". The chip
 * changes at once and goes back if the server refuses (a type with no live playbook, a network error).
 * With types by channel the same menu also says the channel (call or meeting) and moves the memo to
 * the other one; the types offered are that channel's, with or without a playbook.
 */
export function TypeChip({
  memoId,
  chip,
  options,
  channel = null,
  untyped = false,
}: {
  memoId: string;
  chip: { key: string; label: string };
  options: TypeOption[];
  /** The memo's channel (`interactionKind`). */
  channel?: string | null;
  /** No type yet: the chip reads quieter and offers the types to tag it with. */
  untyped?: boolean;
}) {
  const { t } = useLanguage();
  const copy = t.product.interactions;
  const queryClient = useQueryClient();
  // The same cached GET /playbooks the options come from: it says whether types go by channel.
  const list = useQuery({ queryKey: PLAYBOOKS_KEY, queryFn: playbooksApi.list, retry: false });
  const channels = byChannel(list.data);
  const liveChannel = LIVE_CHANNELS.includes(channel as LiveChannel) ? (channel as LiveChannel) : null;

  const moveChannel = useMutation({
    mutationFn: (kind: LiveChannel) => memosApi.setChannel(memoId, kind),
    onMutate: async (kind) => {
      await queryClient.cancelQueries({ queryKey: memoKeys.lists() });
      const before = queryClient.getQueriesData<Memo[]>({ queryKey: memoKeys.lists() });
      const keep = channelTypeOptions(options, list.data, kind).some((option) => option.key === chip.key);
      queryClient.setQueriesData<Memo[]>({ queryKey: memoKeys.lists() }, (rows) =>
        rows?.map((row) => (row.id === memoId ? { ...row, interactionKind: kind, ...(keep ? {} : { salesMotionKey: null }) } : row)),
      );
      return { before };
    },
    onError: (_error, _kind, context) => {
      context?.before.forEach(([key, rows]) => queryClient.setQueryData(key, rows));
      toast.error(copy.retagFailed);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: memoKeys.lists() });
      void queryClient.invalidateQueries({ queryKey: memoKeys.detail(memoId) });
      void queryClient.invalidateQueries({ queryKey: ["memo-playbook", memoId] });
    },
  });

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

  // Only types that can score (a live playbook) and "Interna"; with types by channel, the memo's
  // channel types with or without a playbook. The chip itself still names whatever the memo carries,
  // even a paused or deleted type.
  const choices = channels ? channelTypeOptions(options, list.data, channel) : retagOptions(options);
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
              disabled={retag.isPending || moveChannel.isPending}
              className={cn(
                chipClass,
                "max-w-[12rem] transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none disabled:opacity-60",
                untyped
                  ? "border border-dashed border-border text-muted-foreground hover:text-foreground"
                  : "bg-beige/10 text-beige hover:bg-beige/20",
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
        {channels && liveChannel ? (
          <>
            <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">{copy.channelLabel}</DropdownMenuLabel>
            <DropdownMenuRadioGroup
              value={liveChannel}
              onValueChange={(kind) => {
                if (kind !== liveChannel) moveChannel.mutate(kind as LiveChannel);
              }}
            >
              {LIVE_CHANNELS.map((kind) => (
                <DropdownMenuRadioItem key={kind} value={kind}>
                  {copy.channel[kind]}
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">{copy.typeLabel}</DropdownMenuLabel>
          </>
        ) : null}
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
