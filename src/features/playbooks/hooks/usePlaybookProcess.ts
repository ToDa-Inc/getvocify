import { useCallback, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useAuth } from "@/features/auth";
import { errorCode, playbooksApi, type PlaybookList } from "@/features/playbooks/api";
import type { Flush } from "@/features/playbooks/hooks/usePlaybookDraft";
import { CATALOG_KEY, COMPANY_KEY, DEAL_STAGES_KEY, DEFAULT_GOALS, PLAYBOOKS_KEY } from "@/features/playbooks/keys";
import { useLanguage } from "@/lib/i18n";
import { motionLabel } from "@/lib/motion-label";
import {
  nothingYet,
  optimisticStatus,
  pendingKeys,
  playbookRows,
  type AppliesTo,
} from "@/lib/playbook-doc";
import { newStepKey, templateSteps, type EditorStep } from "@/lib/playbook-editor";
import { isEmptyKnowledge, knowledgeSummary } from "@/lib/playbook-knowledge";
import type { MotionStatus } from "@/lib/playbook-setup";

/** A manager always sees the two base flows, even before anything was created. */
function withBaseFlows(motions: Record<string, MotionStatus>, canEdit: boolean): Record<string, MotionStatus> {
  return canEdit ? { discovery: "missing", closing: "missing", ...motions } : motions;
}

/**
 * Everything "Vuestro proceso" knows and does, without any markup: the data, how each call
 * type is named, and the actions that change the list (switch, delete/undo, rules, turning
 * pending changes on). The components only render what this returns.
 */
export function usePlaybookProcess() {
  const { t, language } = useLanguage();
  const copy = t.product.pb2;
  const lang = language === "EN" ? "en" : "es";
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const role = user?.company?.role;
  const canEdit = role === "owner" || role === "admin";
  const routing = (user?.company?.features ?? []).includes("PLAYBOOK_ROUTING_ENABLED");
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [activating, setActivating] = useState(false);
  // Bumped when the server changed a playbook under an open document, so it reloads.
  const [docVersion, setDocVersion] = useState(0);
  const flushes = useRef(new Map<string, Flush>());

  const list = useQuery({ queryKey: PLAYBOOKS_KEY, queryFn: playbooksApi.list, retry: false });
  const catalog = useQuery({
    queryKey: CATALOG_KEY,
    queryFn: playbooksApi.catalog,
    enabled: routing && canEdit,
    retry: false,
    staleTime: 60 * 60 * 1000,
  });
  const stages = useQuery({
    queryKey: DEAL_STAGES_KEY,
    queryFn: playbooksApi.dealStages,
    enabled: routing && canEdit,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
  const company = useQuery({ queryKey: COMPANY_KEY, queryFn: playbooksApi.company, retry: false });

  const motions = withBaseFlows(list.data?.motions ?? {}, canEdit);
  const details = list.data?.details ?? {};
  const types = catalog.data?.types ?? [];
  const typeOf = (key: string) => types.find((type) => type.key === key);
  const rows = playbookRows(motions, details, routing);
  const companySummary = knowledgeSummary(company.data?.knowledge, copy.summary);
  const empty =
    canEdit && list.isSuccess && nothingYet(motions, details) && !company.isLoading && isEmptyKnowledge(company.data?.knowledge);
  const pending = pendingKeys(motions, details);

  const name = (key: string) => {
    if (key === "closing" && "negotiation" in motions) return copy.closingDemoOnly;
    // A catalog type reads in the app's language; a company's own type keeps its name.
    const localized = copy.typeLabels[key] || typeOf(key)?.label?.[lang];
    if (localized && (details[key]?.catalog ?? true)) return localized;
    return details[key]?.label || localized || motionLabel(key, t.product.motions);
  };

  const template = (key: string) => (): EditorStep[] => {
    const fromCatalog = typeOf(key)?.template?.[lang];
    if (fromCatalog?.length) return fromCatalog.map((step) => ({ key: newStepKey(), ...step }));
    return templateSteps(key, lang);
  };

  const goalOf = (key: string): string | null =>
    details[key]?.goal ?? list.data?.goals?.[key] ?? typeOf(key)?.goal ?? DEFAULT_GOALS[key] ?? null;
  const ruleOf = (key: string): AppliesTo | null => details[key]?.applies_to ?? typeOf(key)?.applies_to ?? null;

  const refresh = () => queryClient.invalidateQueries({ queryKey: PLAYBOOKS_KEY });
  /** The server's answer to a pause/resume/delete/restore is the new list: take it as is. */
  const adoptList = (data: PlaybookList) => queryClient.setQueryData<PlaybookList>(PLAYBOOKS_KEY, data);
  const reloadDocuments = () => setDocVersion((version) => version + 1);

  const registerFlush = useCallback((key: string, flush: Flush | null) => {
    if (flush) flushes.current.set(key, flush);
    else flushes.current.delete(key);
  }, []);

  const saveRule = async (key: string, rule: AppliesTo) => {
    await playbooksApi.saveRule(key, rule);
    await refresh();
  };

  /** The row switch. Flips at once, confirms with the server, rolls back on failure; the toast
   * offers the opposite action, so a misclick costs one click. */
  const toggle = async (key: string, on: boolean): Promise<void> => {
    const action = on ? "resume" : "pause";
    const label = name(key);
    setBusyKey(key);
    queryClient.setQueryData<PlaybookList>(PLAYBOOKS_KEY, (old) => {
      if (!old) return old;
      const next = optimisticStatus(action, old.motions[key] ?? "missing");
      return next ? { ...old, motions: { ...old.motions, [key]: next } } : old;
    });
    try {
      adoptList(await (on ? playbooksApi.resume(key) : playbooksApi.pause(key)));
      reloadDocuments();
      toast((on ? copy.resumedToast : copy.pausedToast).replace("{name}", label), {
        action: { label: copy.undo, onClick: () => void toggle(key, !on) },
      });
    } catch {
      await refresh();
      toast.error(copy.actionFailed);
    } finally {
      setBusyKey(null);
    }
  };

  /** Delete is soft on the server (calls already scored keep their mark), so it can be undone. */
  const remove = async (key: string): Promise<boolean> => {
    const label = name(key);
    setBusyKey(key);
    try {
      adoptList(await playbooksApi.remove(key));
      flushes.current.delete(key);
      toast(copy.deletedToast.replace("{name}", label), {
        action: {
          label: copy.undo,
          onClick: () =>
            void playbooksApi
              .restore(key)
              .then((data) => {
                adoptList(data);
                reloadDocuments();
              })
              .catch(() => toast.error(copy.actionFailed)),
        },
      });
      return true;
    } catch {
      toast.error(copy.actionFailed);
      return false;
    } finally {
      setBusyKey(null);
    }
  };

  /** One action for the page: save what is being typed, then turn every pending change on. */
  const activate = async (): Promise<boolean> => {
    setActivating(true);
    try {
      const saved = await Promise.all([...flushes.current.values()].map((flush) => flush()));
      if (saved.some((ok) => !ok)) throw new Error("unsaved");
      const fresh = (await list.refetch()).data ?? list.data;
      const keys = pendingKeys(withBaseFlows(fresh?.motions ?? {}, canEdit), fresh?.details ?? {});
      for (const key of keys) {
        const result = await playbooksApi.publish(key);
        if (result.motions[key] !== "published") throw new Error("publish");
      }
      await refresh();
      reloadDocuments();
      toast.success(copy.activated);
      return true;
    } catch (error) {
      toast.error(errorCode(error) === "contradiction" ? t.product.playbookContradiction : copy.activateFailed);
      return false;
    } finally {
      setActivating(false);
    }
  };

  return {
    canEdit,
    routing,
    list,
    company,
    companySummary,
    stages: stages.data?.stages ?? [],
    types,
    motions,
    details,
    rows,
    empty,
    pending,
    busyKey,
    activating,
    docVersion,
    name,
    template,
    goalOf,
    ruleOf,
    refresh,
    registerFlush,
    saveRule,
    toggle,
    remove,
    activate,
    companySaved: () => void queryClient.invalidateQueries({ queryKey: COMPANY_KEY }),
  };
}

export type PlaybookProcess = ReturnType<typeof usePlaybookProcess>;
