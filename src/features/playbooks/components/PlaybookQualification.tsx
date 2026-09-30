import { useState } from "react";
import { Plus, Trash } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { ConfirmAction } from "@/components/ui/confirm-action";
import { IconAction } from "@/components/ui/icon-action";
import { playbooksApi } from "@/features/playbooks/api";
import { QUALIFICATION_TEMPLATES_KEY } from "@/features/playbooks/keys";
import { linkButton } from "@/features/playbooks/styles";
import { InlineTextarea } from "@/features/playbooks/components/InlineField";
import { useLanguage } from "@/lib/i18n";
import {
  MAX_CRITERIA,
  MAX_CRITERION_FIELD,
  MAX_CRITERION_LABEL,
  newStepKey,
  type EditorCriterion,
} from "@/lib/playbook-editor";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

type Patch = Partial<Omit<EditorCriterion, "key">>;

/**
 * "Qué tiene que salir de la llamada": what the rep has to find out, and how a good answer
 * sounds. Vocify looks for each one in every call. Empty, it offers BANT/MEDDIC/MEDDPICC as
 * a starting point; read-only and empty, it isn't shown at all.
 */
export function PlaybookQualification({
  criteria,
  editable,
  onChange,
}: {
  criteria: EditorCriterion[];
  editable: boolean;
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
    retry: false,
    staleTime: 60 * 60 * 1000,
  });

  if (!editable && criteria.length === 0) return null;

  const patch = (key: string, next: Patch) =>
    onChange(criteria.map((item) => (item.key === key ? { ...item, ...next } : item)));
  const add = () => {
    const key = newStepKey();
    setFocusKey(key);
    onChange([...criteria, { key, label: "", good: "", bad: "", why: "" }]);
  };
  const applyTemplate = (key: string) => {
    const template = templates.data?.templates.find((item) => item.key === key);
    const items = (template?.criteria[lang] ?? []).map((item) => ({ ...item, key: newStepKey() }));
    if (!items.length) return;
    if (criteria.some((item) => item.label.trim())) setPending(items);
    else onChange(items);
  };

  const chips = (templates.data?.templates ?? []).map((template) => (
    <button
      key={template.key}
      type="button"
      className="rounded-full border border-border px-3 py-1 text-[13px] text-foreground hover:bg-secondary/60"
      onClick={() => applyTemplate(template.key)}
    >
      {template.label}
    </button>
  ));

  return (
    <section className="space-y-1" aria-label={copy.qualHeading}>
      <h3 className={THEME_TOKENS.typography.capsLabel}>{copy.qualHeading}</h3>
      {criteria.length === 0 ? (
        <div className="space-y-2 py-1">
          <p className="text-sm text-muted-foreground">{copy.qualEmpty}</p>
          <div className="flex flex-wrap items-center gap-2">
            {chips}
            <button
              type="button"
              className={linkButton}
              onClick={add}
            >
              <Plus size={12} weight="light" />
              {copy.qualAdd}
            </button>
          </div>
        </div>
      ) : (
        <ul>
          {criteria.map((item) => (
            <CriterionItem
              key={item.key}
              item={item}
              editable={editable}
              autoFocus={focusKey === item.key}
              onChange={(next) => patch(item.key, next)}
              onRemove={() => onChange(criteria.filter((other) => other.key !== item.key))}
            />
          ))}
        </ul>
      )}
      {editable && criteria.length > 0 && criteria.length < MAX_CRITERIA ? (
        <button
          type="button"
          className={linkButton}
          onClick={add}
        >
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

function CriterionItem({
  item,
  editable,
  autoFocus,
  onChange,
  onRemove,
}: {
  item: EditorCriterion;
  editable: boolean;
  autoFocus: boolean;
  onChange: (patch: Patch) => void;
  onRemove: () => void;
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const [open, setOpen] = useState(false);
  const hasBad = Boolean(item.bad?.trim());
  const hasWhy = Boolean(item.why?.trim());

  if (!editable) {
    return (
      <li className="grid items-start gap-x-5 border-t border-border/40 py-3 first:border-t-0 md:grid-cols-[minmax(0,15rem)_minmax(0,1fr)]">
        <p className="text-[15px] text-foreground">{item.label}</p>
        <div className="space-y-0.5">
          {item.good ? <p className="text-sm text-muted-foreground">{item.good}</p> : null}
          {item.bad ? (
            <p className="text-xs text-muted-foreground">
              {copy.qualBad} {item.bad}
            </p>
          ) : null}
        </div>
      </li>
    );
  }

  return (
    <li className="group grid items-start gap-x-5 gap-y-0.5 border-t border-border/40 py-2 first:border-t-0 md:grid-cols-[minmax(0,15rem)_minmax(0,1fr)]">
      <InlineTextarea
        className="text-[15px]"
        value={item.label}
        maxLength={MAX_CRITERION_LABEL + 20}
        placeholder={copy.qualLabel}
        aria-label={copy.qualLabel}
        autoFocus={autoFocus}
        onKeyDown={(event) => {
          if (event.key === "Enter") event.preventDefault();
        }}
        onChange={(event) => onChange({ label: event.target.value.replace(/\n/g, " ") })}
      />
      <div className="min-w-0 space-y-0.5">
        <div className="flex items-start gap-1">
          <InlineTextarea
            className="flex-1 text-sm text-muted-foreground focus:text-foreground"
            value={item.good ?? ""}
            placeholder={copy.qualGood}
            aria-label={copy.qualGood}
            aria-invalid={(item.good ?? "").length > MAX_CRITERION_FIELD}
            onChange={(event) => onChange({ good: event.target.value })}
          />
          <span className="opacity-100 transition-opacity md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100">
            <IconAction label={t.product.playbookEditorRemove} tone="danger" onClick={onRemove}>
              <Trash size={14} weight="light" />
            </IconAction>
          </span>
        </div>
        {open || hasBad ? (
          <InlineTextarea
            className={cn("text-xs text-muted-foreground focus:text-foreground", THEME_TOKENS.motion.fadeIn)}
            value={item.bad ?? ""}
            placeholder={copy.qualBad}
            aria-label={copy.qualBad}
            onChange={(event) => onChange({ bad: event.target.value })}
          />
        ) : null}
        {open || hasWhy ? (
          <InlineTextarea
            className={cn("text-xs text-muted-foreground focus:text-foreground", THEME_TOKENS.motion.fadeIn)}
            value={item.why ?? ""}
            placeholder={copy.qualWhy}
            aria-label={copy.qualWhy}
            onChange={(event) => onChange({ why: event.target.value })}
          />
        ) : null}
        {!open && !(hasBad && hasWhy) ? (
          <button
            type="button"
            className="inline-flex items-center gap-0.5 text-xs text-muted-foreground hover:text-foreground"
            onClick={() => setOpen(true)}
          >
            <Plus size={10} weight="light" />
            {copy.objDetails}
          </button>
        ) : null}
      </div>
    </li>
  );
}
