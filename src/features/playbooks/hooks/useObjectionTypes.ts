import { useMemo, useState } from "react";
import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { errorCode, playbooksApi } from "@/features/playbooks/api";
import { PLAYBOOKS_KEY } from "@/features/playbooks/keys";
import { useLanguage } from "@/lib/i18n";
import { draftBodyWithObjections, joinNames, objectionsAfter, typesWithObjection, typesWithPlaybook, type ObjectionAction, type ObjectionLibrary } from "@/lib/objection-types";
import { objectionsFromSnapshot, type EditorObjection } from "@/lib/playbook-editor";
import { typeName } from "@/lib/type-name";

const editorKey = (type: string) => ["objection-types", "editor", type] as const;

/**
 * One objection in several call types. The current type's objections are the live draft; the other
 * types' come from their editor snapshots. Ticking a type or copying an answer writes the OTHER
 * types' drafts (their steps and qualification unchanged), never the published versions and never the
 * current type. Only a manager who can edit loads anything.
 */
export function useObjectionTypes({ motionKey, enabled, objections }: { motionKey: string; enabled: boolean; objections: EditorObjection[] }) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const queryClient = useQueryClient();
  const [writing, setWriting] = useState(0);

  const list = useQuery({ queryKey: PLAYBOOKS_KEY, queryFn: playbooksApi.list, retry: false, enabled });
  const withPlaybook = typesWithPlaybook(list.data?.motions ?? {});
  const others = withPlaybook.filter((type) => type !== motionKey);
  const docs = useQueries({
    queries: others.map((type) => ({
      queryKey: editorKey(type),
      queryFn: () => playbooksApi.editor(type),
      enabled,
      staleTime: 60_000,
      retry: false,
    })),
  });

  const loaded = docs.map((doc) => doc.data);
  const library = useMemo<ObjectionLibrary>(() => {
    const out: ObjectionLibrary = {};
    for (const type of withPlaybook) {
      if (type === motionKey) out[type] = objections;
      else {
        const data = loaded[others.indexOf(type)];
        if (data && data.source !== "empty") out[type] = objectionsFromSnapshot(data);
      }
    }
    // The current type is always there, even before the list knows it.
    return motionKey in out ? out : { [motionKey]: objections, ...out };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `loaded` changes identity every render; its data is what matters
  }, [objections, motionKey, withPlaybook.join("|"), docs.map((doc) => doc.dataUpdatedAt).join("|")]);

  const allTypes = Object.keys(library);
  const details = list.data?.details ?? {};
  const names = Object.fromEntries(allTypes.map((type) => [type, typeName(type, copy.typeLabels, details, t.product.motions)]));

  /** Reads the type's fresh editor, applies the action to its objections and saves that as its draft. */
  const writeDraft = async (type: string, key: string, action: ObjectionAction, attempt = 0): Promise<boolean> => {
    const doc = await queryClient.fetchQuery({ queryKey: editorKey(type), queryFn: () => playbooksApi.editor(type), staleTime: 0 });
    const fresh: ObjectionLibrary = { [motionKey]: objections, [type]: objectionsFromSnapshot(doc) };
    const next = objectionsAfter(fresh, key, motionKey, type, action);
    if (!next) return false;
    const body = draftBodyWithObjections(doc, next);
    if (!body) throw new Error("invalid_draft");
    try {
      await playbooksApi.saveDraft(type, body);
    } catch (error) {
      // Someone saved this type's draft meanwhile: read it again and apply the action once more.
      if (errorCode(error) === "stale_draft" && attempt === 0) return writeDraft(type, key, action, 1);
      throw error;
    }
    await Promise.all([queryClient.invalidateQueries({ queryKey: PLAYBOOKS_KEY }), queryClient.invalidateQueries({ queryKey: editorKey(type) })]);
    return true;
  };

  const run = async (types: string[], key: string, action: ObjectionAction, done: (names: string) => string) => {
    setWriting((count) => count + 1);
    try {
      const results = await Promise.allSettled(types.map((type) => writeDraft(type, key, action)));
      const saved = types.filter((_, index) => {
        const result = results[index];
        return result.status === "fulfilled" && result.value;
      });
      if (saved.length > 0) toast(done(joinNames(saved.map((type) => names[type] ?? type), copy.objTypesAnd)));
      if (results.some((result) => result.status === "rejected")) toast.error(copy.actionFailed);
    } finally {
      setWriting((count) => count - 1);
    }
  };

  return {
    /** Manager, and the company has at least two types with a playbook. */
    available: enabled && allTypes.length >= 2,
    allTypes,
    names,
    busy: writing > 0,
    appearsIn: (key: string) => typesWithObjection(library, key),
    toggle: (key: string, type: string, on: boolean) =>
      run([type], key, { kind: "set", on }, (label) => (on ? copy.objTypesAdded : copy.objTypesRemoved).replace("{name}", label)),
    copyAnswer: (key: string, types: string[]) => run(types, key, { kind: "copy" }, (label) => copy.objTypesCopied.replace("{names}", label)),
  };
}
