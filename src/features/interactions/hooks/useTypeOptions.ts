import { useQuery } from "@tanstack/react-query";
import { playbooksApi } from "@/features/playbooks/api";
import { PLAYBOOKS_KEY } from "@/features/playbooks/keys";
import { typeOptions } from "@/lib/interactions";
import { useLanguage } from "@/lib/i18n";
import { motionLabel } from "@/lib/motion-label";

/**
 * The company's interaction types (GET /playbooks, the same query the playbook screens use) plus
 * "Interna". Catalog types come back without a label, so `labelOf` names them from the copy.
 */
export function useTypeOptions() {
  const { t } = useLanguage();
  const list = useQuery({ queryKey: PLAYBOOKS_KEY, queryFn: playbooksApi.list, retry: false });
  const labelOf = (key: string): string => t.product.pb2.typeLabels[key] || motionLabel(key, t.product.motions);
  return { options: typeOptions(list.data, t.product.interactions.internal, labelOf), labelOf };
}
