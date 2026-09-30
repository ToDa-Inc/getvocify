import { useState } from "react";
import { Plus } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { ConfirmAction } from "@/components/ui/confirm-action";
import { playbooksApi, type QualificationTemplate } from "@/features/playbooks/api";
import { CompleteButton, DocRow, ItemMenu, NumberMark } from "@/features/playbooks/components/DocParts";
import { InlineTextarea } from "@/features/playbooks/components/InlineField";
import { QUALIFICATION_TEMPLATES_KEY } from "@/features/playbooks/keys";
import { itemBody, itemTitle, linkButton } from "@/features/playbooks/styles";
import { useLanguage } from "@/lib/i18n";
import { matchedMethod } from "@/lib/playbook-doc";
import { MAX_CRITERIA, MAX_CRITERION_LABEL, newStepKey, type EditorCriterion } from "@/lib/playbook-editor";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

type Role = "sdr" | "ae";

/**
 * "Qué tiene que salir de la llamada": the usual methods for this call type's role (BANT, CHAMP,
 * ANUM, GPCT for an SDR call; MEDDIC, MEDDPICC, SPICED, BANT for an AE meeting) as one click, or
 * the company's own. Each criterion is what to find out, in bold, and how a good answer sounds.
 */
export function PlaybookQualification({
  criteria,
  editable,
  role,
  completingKey,
  busy,
  onComplete,
  onChange,
}: {
  criteria: EditorCriterion[];
  editable: boolean;
  /** The call type's role; null shows every method. */
  role: Role | null;
  /** The criterion Vocify is writing for; `busy` while it writes anything. */
  completingKey?: string | null;
  busy?: boolean;
  onComplete?: (item: EditorCriterion) => void;
  onChange: (next: EditorCriterion[]) => void;
}) {
  const { t, language } = useLanguage();
  const copy = t.product.pb2;
  const lang = language === "EN" ? "en" : "es";
  const [pending, setPending] = useState<EditorCriterion[] | null>(null);
  const [focusKey, setFocusKey] = useState<string | null>(null);
  const templates = useQuery({
    queryKey: QUALIFICATION_TEMPLATES_KEY,
    queryFn: playbooksApi.qualificationTemplates,
    enabled: editable,
    // Static data: one retry, so a network blip doesn't leave the methods off the screen.
    retry: 1,
    staleTime: 60 * 60 * 1000,
  });

  if (!editable && criteria.length === 0) return null;

  const all = templates.data?.templates ?? [];
  const methods = role ? all.filter((template) => template.roles.includes(role)) : all;
  const current = matchedMethod(criteria, all);
  const patch = (key: string, next: Partial<EditorCriterion>) =>
    onChange(criteria.map((item) => (item.key === key ? { ...item, ...next } : item)));
  const add = () => {
    const key = newStepKey();
    setFocusKey(key);
    onChange([...criteria, { key, label: "", good: "" }]);
  };
  const apply = (template: QualificationTemplate) => {
    const items = template.criteria[lang].map((item) => ({ ...item, key: newStepKey() }));
    if (criteria.some((item) => item.label.trim()) && current !== template.key) setPending(items);
    else onChange(items);
  };

  return (
    <section aria-label={copy.qualHeading}>
      {editable ? (
        <>
          <p className={cn(THEME_TOKENS.typography.capsLabel, "pt-1")}>{role ? copy.qualHint[role] : copy.qualHintAny}</p>
          <div className="flex flex-wrap gap-2 pb-2 pt-3">
            {methods.map((template) => {
              const on = current === template.key;
              return (
                <button
                  key={template.key}
                  type="button"
                  aria-pressed={on}
                  onClick={() => apply(template)}
                  className={cn(
                    "min-w-[9.5rem] rounded-xl border bg-card px-3.5 py-2.5 text-left transition-colors",
                    on ? "border-primary ring-1 ring-primary" : "border-border/70 hover:border-border",
                  )}
                >
                  <span className="block text-sm font-semibold text-foreground">{template.label}</span>
                  <span className="block text-xs text-muted-foreground">{template.summary[lang]}</span>
                </button>
              );
            })}
            <button
              type="button"
              onClick={add}
              className="min-w-[9.5rem] rounded-xl border border-dashed border-border px-3.5 py-2.5 text-left transition-colors hover:border-primary"
            >
              <span className="block text-sm font-semibold text-foreground">+ {copy.qualCustom}</span>
              <span className="block text-xs text-muted-foreground">{copy.qualCustomHint}</span>
            </button>
          </div>
        </>
      ) : null}

      <ul>
        {criteria.map((item) => (
          <DocRow
            key={item.key}
            lead={<NumberMark n="?" />}
            title={
              editable ? (
                <InlineTextarea
                  className={itemTitle}
                  value={item.label}
                  maxLength={MAX_CRITERION_LABEL + 20}
                  placeholder={copy.qualLabel}
                  aria-label={copy.qualLabel}
                  autoFocus={focusKey === item.key}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") event.preventDefault();
                  }}
                  onChange={(event) => patch(item.key, { label: event.target.value.replace(/\n/g, " ") })}
                />
              ) : (
                <p className={itemTitle}>{item.label}</p>
              )
            }
            side={
              editable ? (
                <ItemMenu
                  label={copy.itemMenu.replace("{name}", item.label || copy.qualLabel)}
                  actions={[
                    {
                      label: t.product.playbookEditorRemove,
                      danger: true,
                      onSelect: () => onChange(criteria.filter((other) => other.key !== item.key)),
                    },
                  ]}
                />
              ) : null
            }
          >
            {editable ? (
              <InlineTextarea
                className={itemBody}
                value={item.good ?? ""}
                placeholder={copy.qualGood}
                aria-label={copy.qualGood}
                onChange={(event) => patch(item.key, { good: event.target.value })}
              />
            ) : item.good ? (
              <p className={itemBody}>{item.good}</p>
            ) : null}
            {editable && item.label.trim() && !item.good?.trim() && onComplete ? (
              <div className="pt-1">
                <CompleteButton label={copy.complete} pending={completingKey === item.key} disabled={busy} onClick={() => onComplete(item)} />
              </div>
            ) : null}
          </DocRow>
        ))}
      </ul>
      {editable && criteria.length > 0 && criteria.length < MAX_CRITERIA ? (
        <button type="button" className={cn(linkButton, "mt-2")} onClick={add}>
          <Plus size={12} weight="light" />
          {copy.qualAdd}
        </button>
      ) : null}

      <ConfirmAction
        open={pending !== null}
        onOpenChange={(open) => {
          if (!open) setPending(null);
        }}
        title={copy.qualReplaceTitle}
        description={copy.qualReplaceConfirm}
        confirmLabel={t.product.playbookEditorReplaceAction}
        cancelLabel={t.product.cancelAction}
        tone="default"
        onConfirm={() => {
          if (pending) onChange(pending);
          setPending(null);
        }}
      />
    </section>
  );
}
