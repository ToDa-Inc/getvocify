import { ApiError } from "@/shared/lib/api-client";
import { playbooksApi } from "@/features/playbooks/api";
import type { SourceInput } from "@/features/playbooks/components/PlaybookStart";
import { draftPayload } from "@/lib/playbook-editor";
import { editorFromStructure } from "@/lib/playbook-doc";

let counter = 0;
const newKey = () => `content-${Date.now()}-${counter++}`;

/**
 * Gives one interaction its content from a pasted text or a file: Vocify reads it as that interaction (with the company's
 * own name, goal and description) and the steps and objections become its draft. Throws an ApiError with `no_steps` when
 * nothing usable came out, so the box keeps the text and says why. Nothing is published.
 */
export async function saveTypeContent(key: string, source: SourceInput): Promise<void> {
  const result = await playbooksApi.structure(key, source.kind, source.payload, source.name);
  const next = editorFromStructure(result, newKey);
  if (!next.steps.length) throw new ApiError(422, { detail: { code: "no_steps" } });
  const doc = await playbooksApi.editor(key);
  await playbooksApi.saveDraft(key, {
    ...draftPayload(next.steps, next.objections, next.qualification),
    base_updated_at: doc.updated_at ?? null,
    source_id: result.source?.id ?? null,
  });
}
