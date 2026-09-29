import { useQuery, useQueryClient } from "@tanstack/react-query";
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
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { toast } from "sonner";

type MemoPlaybook = {
  sales_motion_key: string | null;
  playbook_version_id: string | null;
  can_change: boolean;
  options: { key: string; label: string | null }[];
};

/**
 * "Scored as Demo · change" on a recording (plan T10). The way out when routing picked the
 * wrong call type: re-pins the memo and scores it again. Renders nothing without a pin.
 */
export function MemoPlaybookLine({ memoId }: { memoId: string }) {
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

  const change = async (next: { key: string; label: string | null }) => {
    try {
      await playbooksApi.changeMemoPlaybook(memoId, next.key);
      queryClient.setQueryData<MemoPlaybook>(key, { ...data, sales_motion_key: next.key });
      toast(copy.memoPlaybookRequeued.replace("{name}", name(next.key, next.label)));
    } catch (error) {
      toast.error(errorCode(error) === "not_published" ? copy.memoPlaybookNotPublished : copy.memoPlaybookFailed);
    }
  };

  return (
    <p className={THEME_TOKENS.typography.capsLabel}>
      {copy.memoPlaybook.replace("{name}", current)}
      {data.can_change && others.length > 0 ? (
        <>
          {" · "}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button type="button" className="text-foreground underline-offset-4 hover:underline">
                {copy.memoPlaybookChange}
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
        </>
      ) : null}
    </p>
  );
}
