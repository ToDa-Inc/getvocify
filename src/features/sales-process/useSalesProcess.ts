import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { errorCode } from "@/features/playbooks/api";
import { isNotActivated, salesProcessApi, type ProcessType } from "@/features/sales-process/api";
import { canSave, removedWithContent, toRequest, type DraftType } from "@/lib/sales-process";

export const PROCESS_QUERY = ["sales-process"] as const;
export type ProcessStatus = "loading" | "ready" | "error" | "not_activated";

const draftOf = (types: ProcessType[]): DraftType[] =>
  types.map((item) => ({ key: item.key, label: item.label, stage: item.stage, recognize: item.recognize ?? undefined }));

/**
 * The company's own sales process as the Head of Sales edits it: the list from the API becomes a draft they change freely
 * (add, rename, reorder, describe, remove) and one save sends the whole list. `problem` is the code of the last failure, for
 * the screen to word; the draft stays as it was typed until a save works.
 */
export function useSalesProcess({ onSaved }: { onSaved?: (types: ProcessType[]) => void } = {}) {
  const client = useQueryClient();
  const query = useQuery({ queryKey: PROCESS_QUERY, queryFn: salesProcessApi.get, retry: false, staleTime: 30_000 });
  const saved = query.data?.types ?? null;
  const [draft, setDraft] = useState<DraftType[] | null>(null);
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  // The draft starts from what the server has, once, and again after a save.
  useEffect(() => {
    if (saved && draft === null) setDraft(draftOf(saved));
  }, [saved, draft]);

  const status: ProcessStatus = query.isLoading ? "loading" : isNotActivated(query.error) ? "not_activated" : query.isError ? "error" : "ready";
  const list = useMemo(() => draft ?? [], [draft]);
  /** Names of types with steps written that this list would archive: ask before saving. */
  const removing = saved ? removedWithContent(saved, list) : [];

  const save = useCallback(async (): Promise<boolean> => {
    if (!canSave(list)) return false;
    setSaving(true);
    setProblem(null);
    try {
      const done = await salesProcessApi.put(toRequest(list));
      client.setQueryData(PROCESS_QUERY, done);
      void client.invalidateQueries({ queryKey: ["playbooks"] });
      setDraft(draftOf(done.types));
      onSaved?.(done.types);
      return true;
    } catch (error) {
      setProblem(errorCode(error) ?? "unknown");
      return false;
    } finally {
      setSaving(false);
    }
  }, [list, client, onSaved]);

  return { status, saved, list, setList: setDraft, saving, problem, removing, save, reload: () => void query.refetch() };
}

export type SalesProcessController = ReturnType<typeof useSalesProcess>;
