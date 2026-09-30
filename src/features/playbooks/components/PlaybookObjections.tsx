import { Plus } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { CompleteButton, DocRow, ItemMenu, QuoteMark, TypeTag } from "@/features/playbooks/components/DocParts";
import { InlineTextarea } from "@/features/playbooks/components/InlineField";
import { itemBody, itemTitle, linkButton } from "@/features/playbooks/styles";
import { useLanguage } from "@/lib/i18n";
import { hiddenObjectionCategories, isSuggestion, percent, type ObjectionRow } from "@/lib/playbook-doc";
import { MAX_OBJECTION_LABEL, MAX_TRIGGER, type EditorObjection, type ObjectionCategory } from "@/lib/playbook-editor";
import { cn } from "@/lib/utils";

type Patch = Partial<Omit<EditorObjection, "category" | "id">>;
const STARTERS: ObjectionCategory[] = ["price", "timing", "authority"];

/**
 * "Cuando el cliente dice…": each objection is three things. What the prospect says, in bold;
 * its kind, as a tag; and the answer the rep sees. Objections the team hears without an answer
 * come as suggestions (the best rep's answer, or one Vocify writes); with nothing written or heard
 * yet, the three every team gets.
 */
export function PlaybookObjections({
  rows,
  added,
  dismissed,
  editable,
  completingKey,
  busy,
  onComplete,
  onChange,
  onAdd,
  onAddCustom,
  onRemove,
  onDismiss,
}: {
  rows: ObjectionRow[];
  /** Categories the manager added by hand: an entry to fill, not a suggestion. */
  added: readonly string[];
  dismissed: readonly string[];
  editable: boolean;
  /** The objection Vocify is writing for; `busy` while it writes anything. */
  completingKey?: string | null;
  busy?: boolean;
  onComplete?: (row: ObjectionRow) => void;
  onChange: (key: string, patch: Patch) => void;
  onAdd: (category: ObjectionCategory) => void;
  onAddCustom: () => void;
  onRemove: (key: string) => void;
  onDismiss: (key: string) => void;
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const kinds = t.product.playbookObjectionCategories;
  const hidden = hiddenObjectionCategories(rows);
  const answered = rows.filter((row) => !isSuggestion(row, added));
  const shown = editable
    ? answered
    : answered.filter((row) => row.objection.guidance.trim() || (row.objection.category === "custom" && row.objection.label?.trim()));
  const heard = editable ? rows.filter((row) => isSuggestion(row, added) && !dismissed.includes(row.key)) : [];
  // Nothing written and nothing heard yet: the objections every team gets, to answer in one click.
  const starters: ObjectionRow[] =
    editable && shown.length === 0 && heard.length === 0
      ? STARTERS.filter((category) => !dismissed.includes(category)).map((category) => ({
          key: category,
          objection: { category, guidance: "" },
          count: 0,
          share: 0,
          bestExample: null,
        }))
      : [];
  const suggestions = [...heard, ...starters];

  if (!editable && shown.length === 0) return null;

  const kindOf = (item: EditorObjection) => (item.category === "custom" ? item.label ?? "" : kinds[item.category as ObjectionCategory]);
  const usual = (item: EditorObjection) =>
    item.category === "custom" ? copy.objTriggerPlaceholder : copy.objectionSays[item.category] ?? kindOf(item);

  return (
    <section aria-label={copy.objections}>
      <ul>
        {shown.map((row) => {
          const item = row.objection;
          const custom = item.category === "custom";
          const set = (patch: Patch) => onChange(row.key, patch);
          return (
            <DocRow
              key={row.key}
              lead={<QuoteMark muted={!item.guidance.trim()} />}
              title={
                editable ? (
                  <InlineTextarea
                    // Until someone writes the prospect's words, how it usually sounds reads as text.
                    className={cn(itemTitle, "placeholder:text-foreground/70")}
                    value={item.trigger ?? ""}
                    maxLength={MAX_TRIGGER + 20}
                    placeholder={usual(item)}
                    aria-label={copy.objTriggerShort}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") event.preventDefault();
                    }}
                    onChange={(event) => set({ trigger: event.target.value.replace(/\n/g, " ") })}
                  />
                ) : (
                  <p className={itemTitle}>{item.trigger?.trim() || usual(item)}</p>
                )
              }
              side={
                <>
                  {custom && editable ? (
                    <InlineTextarea
                      className="w-36 rounded-full bg-secondary px-2.5 py-0.5 text-[11.5px] text-muted-foreground focus:text-foreground"
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
                    <TypeTag>{kindOf(item)}</TypeTag>
                  )}
                  {row.count > 0 ? (
                    <span className="text-xs tabular-nums text-muted-foreground" title={copy.heardShare.replace("{share}", percent(row.share))}>
                      {percent(row.share)}
                    </span>
                  ) : null}
                  {editable ? (
                    <ItemMenu
                      label={copy.itemMenu.replace("{name}", kindOf(item) || copy.objCustomName)}
                      actions={[{ label: t.product.playbookEditorRemove, onSelect: () => onRemove(row.key), danger: true }]}
                    />
                  ) : null}
                </>
              }
            >
              {editable ? (
                <InlineTextarea
                  className={itemBody}
                  value={item.guidance}
                  placeholder={copy.objectionPlaceholder}
                  aria-label={copy.objAnswer}
                  onChange={(event) => set({ guidance: event.target.value })}
                />
              ) : (
                <p className={itemBody}>{item.guidance}</p>
              )}
              {editable && !item.guidance.trim() && onComplete && (!custom || item.label?.trim()) ? (
                <div className="pt-1">
                  <CompleteButton label={copy.writeAnswer} pending={completingKey === row.key} disabled={busy} onClick={() => onComplete(row)} />
                </div>
              ) : null}
            </DocRow>
          );
        })}

        {suggestions.map((row) => (
          // A ghost of an objection: the same row as a written one, muted until it has an answer.
          <DocRow
            key={row.key}
            lead={<QuoteMark muted />}
            title={<p className={cn(itemTitle, "text-muted-foreground")}>{usual(row.objection)}</p>}
            side={<TypeTag>{kindOf(row.objection)}</TypeTag>}
          >
            {row.count > 0 ? (
              <p className="text-xs text-muted-foreground">
                {copy.heardShare.replace("{share}", percent(row.share))} · {copy.noAnswerYet}
              </p>
            ) : null}
            {row.bestExample ? (
              <p className={itemBody}>
                {copy.bestCall} «{row.bestExample}»
              </p>
            ) : null}
            <div className="flex flex-wrap items-center gap-1 pt-1">
              {row.bestExample ? (
                <Button type="button" size="sm" variant="outline" onClick={() => onChange(row.key, { guidance: row.bestExample ?? "" })}>
                  {copy.useSuggestion}
                </Button>
              ) : onComplete ? (
                <CompleteButton label={copy.writeAnswer} pending={completingKey === row.key} disabled={busy} onClick={() => onComplete(row)} />
              ) : null}
              <button
                type="button"
                className="rounded-full px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground"
                onClick={() => onDismiss(row.key)}
              >
                {copy.dismiss}
              </button>
            </div>
          </DocRow>
        ))}
      </ul>

      {editable ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button type="button" className={cn(linkButton, "mt-2")}>
              <Plus size={12} weight="light" />
              {copy.addObjection}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            {hidden.map((category) => (
              <DropdownMenuItem key={category} onSelect={() => onAdd(category)}>
                {kinds[category]}
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
