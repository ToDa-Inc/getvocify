import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { errorCode, playbooksApi } from "@/features/playbooks/api";
import type { SourceInput } from "@/features/playbooks/components/PlaybookStart";
import { COMPANY_KEY } from "@/features/playbooks/keys";
import { useLanguage } from "@/lib/i18n";
import { editorFromStructure } from "@/lib/playbook-doc";
import { draftPayload, newStepKey } from "@/lib/playbook-editor";
import { knowledgeSummary } from "@/lib/playbook-knowledge";

type Fallback = { candidates: { key: string; label: string }[]; input: SourceInput };

/**
 * The one way in (plan §14–15): the whole document goes to Vocify, which splits it by call
 * type and into "Vuestra empresa". When it can't split it, the person says which call it is.
 * `onDone` receives the call type to open (the only one found), or null.
 */
export function useIntake({ refresh, onDone }: { refresh: () => Promise<unknown>; onDone: (openKey: string | null) => void }) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [found, setFound] = useState<number | null>(null);
  const [foundCompany, setFoundCompany] = useState<string | null>(null);
  const [fallback, setFallback] = useState<Fallback | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [picking, setPicking] = useState<string | null>(null);

  const close = () => {
    setOpen(false);
    setFallback(null);
    setNotice(null);
  };

  const finish = (count: number, companyLine: string | null, openKey: string | null) => {
    setFound(count);
    setFoundCompany(companyLine);
    close();
    onDone(openKey);
  };

  const submit = async (input: SourceInput) => {
    setNotice(null);
    setFallback(null);
    const result = await playbooksApi.intake(input.kind, input.payload, input.name);
    if (result.fallback) {
      setFallback({ candidates: result.candidates, input });
      return;
    }
    const companyFilled = (result.company?.filled.length ?? 0) > 0;
    if (result.types.length === 0 && !companyFilled) {
      setNotice(copy.reasonNoProcess);
      return;
    }
    if (result.company) queryClient.setQueryData(COMPANY_KEY, result.company);
    await refresh();
    finish(
      result.types.length,
      companyFilled ? knowledgeSummary(result.company?.knowledge, copy.summary) : null,
      result.types.length === 1 ? result.types[0].sales_motion_key : null,
    );
  };

  const pick = async (key: string) => {
    if (!fallback) return;
    setPicking(key);
    try {
      const { input } = fallback;
      const result = await playbooksApi.structure(key, input.kind, input.payload, input.name);
      const next = editorFromStructure(result, newStepKey);
      if (next.steps.length === 0) {
        setNotice(copy.reasonNoProcess);
        return;
      }
      await playbooksApi.saveDraft(key, {
        ...draftPayload(next.steps, next.objections, next.qualification),
        source_id: result.source?.id ?? null,
      });
      await refresh();
      finish(1, null, key);
    } catch (error) {
      const code = errorCode(error);
      setNotice((code && copy.readErrors[code]) || copy.structureFailed);
    } finally {
      setPicking(null);
    }
  };

  /** The "we found…" line goes once the changes it announced are on. */
  const clearFound = () => {
    setFound(null);
    setFoundCompany(null);
  };

  return { open, setOpen, close, found, foundCompany, clearFound, fallback, notice, picking, submit, pick };
}

export type Intake = ReturnType<typeof useIntake>;
