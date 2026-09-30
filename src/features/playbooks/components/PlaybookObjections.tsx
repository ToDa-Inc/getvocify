import { useState } from "react";
import { Plus, Trash } from "@phosphor-icons/react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { IconAction } from "@/components/ui/icon-action";
import { linkButton } from "@/features/playbooks/styles";
import { InlineTextarea } from "@/features/playbooks/components/InlineField";
import { useLanguage } from "@/lib/i18n";
import { hasObjectionDetail, hiddenObjectionCategories, percent, type ObjectionRow } from "@/lib/playbook-doc";
import {
  MAX_GUIDANCE,
  MAX_MEANING,
  MAX_OBJECTION_LABEL,
  MAX_PROOF,
  MAX_QUESTION,
  MAX_TRIGGER,
  type EditorObjection,
  type ObjectionCategory,
} from "@/lib/playbook-editor";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

type Patch = Partial<Omit<EditorObjection, "category" | "id">>;
const DETAILS = [
  ["meaning", MAX_MEANING],
  ["question", MAX_QUESTION],
  ["proof", MAX_PROOF],
] as const;

/**
 * "Cuando el cliente dice… / El comercial ve": the company's own objections first, then the
 * ones the team hears, most frequent first. The answer is on screen; what the objection
 * usually means, the question to ask and the proof to use are one click away.
 */
export function PlaybookObjections({
  rows,
  editable,
  onChange,
  onAdd,
  onAddCustom,
  onRemove,
}: {
  rows: ObjectionRow[];
  editable: boolean;
  onChange: (key: string, patch: Patch) => void;
  onAdd: (category: ObjectionCategory) => void;
  onAddCustom: () => void;
  onRemove: (key: string) => void;
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const hidden = hiddenObjectionCategories(rows);
  const shown = editable
    ? rows
    : rows.filter((row) => row.objection.guidance.trim() || (row.objection.category === "custom" && row.objection.label?.trim()));

  if (!editable && shown.length === 0) return null;

  return (
    <section className="space-y-1" aria-label={copy.objections}>
      {/* The two columns say what the answers are for: what the prospect says, what the rep gets. */}
      <div className="grid gap-x-5 md:grid-cols-[minmax(0,15rem)_minmax(0,1fr)]">
        <h3 className={THEME_TOKENS.typography.capsLabel}>{copy.whenClientSays}</h3>
        <p className={cn(THEME_TOKENS.typography.capsLabel, "hidden md:block")} aria-hidden>
          {copy.repSees}
        </p>
      </div>
      {shown.length > 0 ? (
        <ul>
          {shown.map((row) => (
            <ObjectionItem key={row.key} row={row} editable={editable} onChange={onChange} onRemove={onRemove} />
          ))}
        </ul>
      ) : null}
      {editable ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className={cn(linkButton, "mt-1")}
            >
              <Plus size={12} weight="light" />
              {copy.addObjection}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            {hidden.map((category) => (
              <DropdownMenuItem key={category} onSelect={() => onAdd(category)}>
                {t.product.playbookObjectionCategories[category]}
              </DropdownMenuItem>
            ))}
            {hidden.length > 0 ? <DropdownMenuSeparator /> : null}
            <DropdownMenuItem onSelect={onAddCustom}>{copy.objNewCustom}</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
    </section>
  );
}

function ObjectionItem({
  row,
  editable,
  onChange,
  onRemove,
}: {
  row: ObjectionRow;
  editable: boolean;
  onChange: (key: string, patch: Patch) => void;
  onRemove: (key: string) => void;
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const item = row.objection;
  const custom = item.category === "custom";
  const [open, setOpen] = useState(false);
  const showDetails = open || hasObjectionDetail(item);
  const unanswered = !item.guidance.trim();
  const name = custom ? item.label ?? "" : t.product.playbookObjectionCategories[item.category as ObjectionCategory];
  const set = (patch: Patch) => onChange(row.key, patch);

  return (
    <li className="group grid items-start gap-x-5 gap-y-0.5 border-t border-border/40 py-2.5 first:border-t-0 md:grid-cols-[minmax(0,15rem)_minmax(0,1fr)]">
      <div className="min-w-0 space-y-0.5 pt-1">
        {custom && editable ? (
          <InlineTextarea
            className="text-[15px]"
            value={item.label ?? ""}
            maxLength={MAX_OBJECTION_LABEL + 20}
            placeholder={copy.objCustomName}
            aria-label={copy.objCustomName}
            autoFocus={!item.label}
            onKeyDown={(event) => {
              if (event.key === "Enter") event.preventDefault();
            }}
            onChange={(event) => set({ label: event.target.value.replace(/\n/g, " ") })}
          />
        ) : (
          <p className="text-[15px] text-foreground">{name}</p>
        )}
        {custom && editable ? (
          <InlineTextarea
            className="text-xs text-muted-foreground"
            value={item.trigger ?? ""}
            maxLength={MAX_TRIGGER + 20}
            placeholder={copy.objTriggerPlaceholder}
            aria-label={copy.objTrigger}
            onChange={(event) => set({ trigger: event.target.value })}
          />
        ) : custom && item.trigger ? (
          <p className="text-xs text-muted-foreground">
            {copy.objTrigger}: «{item.trigger}»
          </p>
        ) : null}
        {row.count > 0 && editable ? (
          <p className={cn("text-xs", unanswered ? "text-warning" : "text-muted-foreground")}>
            {(unanswered ? copy.heardUnanswered : copy.heard).replace("{share}", percent(row.share))}
          </p>
        ) : null}
      </div>

      <div className="min-w-0 space-y-1">
        <div className="flex items-start gap-1">
          {editable ? (
            <InlineTextarea
              className="flex-1 text-sm"
              value={item.guidance}
              placeholder={copy.objectionPlaceholder}
              aria-label={name || copy.objCustomName}
              aria-invalid={item.guidance.length > MAX_GUIDANCE}
              onChange={(event) => set({ guidance: event.target.value })}
            />
          ) : (
            <p className="flex-1 pt-1 text-sm leading-relaxed text-foreground">{item.guidance}</p>
          )}
          {editable && custom ? (
            <span className="opacity-100 transition-opacity md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100">
              <IconAction label={t.product.playbookEditorRemove} tone="danger" onClick={() => onRemove(row.key)}>
                <Trash size={14} weight="light" />
              </IconAction>
            </span>
          ) : null}
        </div>

        {editable && unanswered && row.bestExample ? (
          <button
            type="button"
            className="text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
            title={row.bestExample}
            onClick={() => set({ guidance: row.bestExample ?? "" })}
          >
            {copy.useTeamAnswer}
          </button>
        ) : null}

        {showDetails ? (
          <dl className={cn("space-y-0.5", THEME_TOKENS.motion.fadeIn)}>
            {DETAILS.map(([field, max]) => {
              const value = item[field] ?? "";
              const label = field === "meaning" ? copy.objMeaning : field === "question" ? copy.objQuestion : copy.objProof;
              // Only what is filled, unless the person asked for the rest ("+ detalles").
              if (!value.trim() && (!editable || !open)) return null;
              return (
                <div key={field} className="grid grid-cols-[minmax(0,9rem)_minmax(0,1fr)] items-start gap-x-3">
                  <dt className="pt-1 text-xs text-muted-foreground">{label}</dt>
                  <dd className="min-w-0">
                    {editable ? (
                      <InlineTextarea
                        className="text-sm text-muted-foreground focus:text-foreground"
                        value={value}
                        aria-label={label}
                        aria-invalid={value.length > max}
                        onChange={(event) => set({ [field]: event.target.value })}
                      />
                    ) : (
                      <p className="pt-1 text-sm text-muted-foreground">{value}</p>
                    )}
                  </dd>
                </div>
              );
            })}
          </dl>
        ) : null}
        {editable && !open && DETAILS.some(([field]) => !(item[field] ?? "").trim()) ? (
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
