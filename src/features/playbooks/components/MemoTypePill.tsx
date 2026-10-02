import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Sparkles } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { api } from "@/shared/lib/api-client";
import { errorCode, playbooksApi } from "@/features/playbooks/api";
import { useLanguage } from "@/lib/i18n";
import { motionLabel } from "@/lib/motion-label";
import { toast } from "sonner";

type MemoPlaybook = {
  sales_motion_key: string | null;
  playbook_version_id: string | null;
  can_change: boolean;
  /** Read from the conversation by Vocify, not confirmed by anyone yet. */
  suggested?: boolean;
  options: { key: string; label: string | null }[];
};

const PILL = "inline-flex h-7 items-center gap-1.5 rounded-full border border-border/50 bg-secondary/5 px-3 text-xs text-foreground";

/**
 * What kind of call this was (its playbook type), as a pill. Choosing another re-scores the
 * call against that playbook. A sparkle marks a type Vocify suggested that nobody has
 * confirmed; it goes once someone picks. Renders nothing without a type.
 */
export function MemoTypePill({ memoId }: { memoId: string }) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const queryClient = useQueryClient();
  const key = ["memo-playbook", memoId];
  const query = useQuery({
    queryKey: key,
    queryFn: () => api.get<MemoPlaybook>(`/memos/${encodeURIComponent(memoId)}/playbook`),
    retry: false,
  });
  const data = query.data;
  if (!data?.sales_motion_key) return null;

  const name = (motion: string, label?: string | null) => label || copy.typeLabels[motion] || motionLabel(motion, t.product.motions);
  const current = name(data.sales_motion_key, data.options.find((option) => option.key === data.sales_motion_key)?.label);
  const others = data.options.filter((option) => option.key !== data.sales_motion_key);
  const mark = data.suggested ? <Sparkles className="h-3 w-3 text-beige" aria-hidden /> : null;

  const change = async (next: { key: string; label: string | null }) => {
    try {
      await playbooksApi.changeMemoPlaybook(memoId, next.key);
      queryClient.setQueryData<MemoPlaybook>(key, { ...data, sales_motion_key: next.key, suggested: false });
      toast(copy.memoPlaybookRequeued.replace("{name}", name(next.key, next.label)));
    } catch (error) {
      toast.error(errorCode(error) === "not_published" ? copy.memoPlaybookNotPublished : copy.memoPlaybookFailed);
    }
  };

  if (!data.can_change || others.length === 0) {
    return (
      <span className={PILL} title={data.suggested ? copy.typeSuggested : undefined}>
        {mark}
        {current}
      </span>
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={`${PILL} transition-colors hover:bg-secondary/10`}
          title={data.suggested ? copy.typeSuggested : undefined}
        >
          {mark}
          {current}
          <ChevronDown className="h-3 w-3 text-muted-foreground" aria-hidden />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {others.map((option) => (
          <DropdownMenuItem key={option.key} onSelect={() => void change(option)}>
            {name(option.key, option.label)}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
