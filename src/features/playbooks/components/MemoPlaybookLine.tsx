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
import { memoTypeLine, memoTypeName } from "@/lib/interactions";
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
 * wrong call type: re-pins the memo and scores it again. An internal memo reads "Interna · no se
 * puntúa" and can be moved back to a real type; Interna is offered like on the list chip.
 * Renders nothing without a pin.
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

  const names = { typeLabels: copy.typeLabels, motions: t.product.motions, internal: t.product.interactions.internal };
  const name = (motion: string, label?: string | null) => memoTypeName(motion, label, names);
  const current = name(data.sales_motion_key, data.options.find((option) => option.key === data.sales_motion_key)?.label);
  const others = data.options.filter((option) => option.key !== data.sales_motion_key);

  const change = async (next: { key: string; label: string | null }) => {
    try {
      await playbooksApi.changeMemoPlaybook(memoId, next.key);
      queryClient.setQueryData<MemoPlaybook>(key, { ...data, sales_motion_key: next.key });
      // The coaching card below reads the score again (Interna shows "not scored" at once).
      void queryClient.invalidateQueries({ queryKey: ["memo-score", memoId] });
      // Interna is not scored again, so it says so instead of "scoring again as".
      toast(memoTypeLine(next.key, name(next.key, next.label), { memoPlaybook: copy.memoPlaybookRequeued, memoPlaybookInternal: copy.memoPlaybookInternal }));
    } catch (error) {
      toast.error(errorCode(error) === "not_published" ? copy.memoPlaybookNotPublished : copy.memoPlaybookFailed);
    }
  };

  return (
    <p className={THEME_TOKENS.typography.capsLabel}>
      {memoTypeLine(data.sales_motion_key, current, copy)}
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
