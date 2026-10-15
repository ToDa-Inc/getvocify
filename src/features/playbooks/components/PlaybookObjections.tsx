import { useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronDown, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { IconAction } from "@/components/ui/icon-action";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { CompleteButton, DocRow, ItemMenu, MetaLine, QuoteMark, TypeTag } from "@/features/playbooks/components/DocParts";
import { InlineTextarea } from "@/features/playbooks/components/InlineField";
import { itemBody, itemTitle, linkButton } from "@/features/playbooks/styles";
import { useLanguage } from "@/lib/i18n";
import { hiddenObjectionCategories, isSuggestion, newlyAddedKey, percent, toggleOpenKey, type ObjectionRow } from "@/lib/playbook-doc";
import { MAX_OBJECTION_LABEL, MAX_TRIGGER, type EditorObjection, type ObjectionCategory } from "@/lib/playbook-editor";
import { cn } from "@/lib/utils";

type Patch = Partial<Omit<EditorObjection, "category" | "id">>;
const STARTERS: ObjectionCategory[] = ["price", "timing", "authority"];

/**
 * "Cuando el cliente dice…": each objection is three things. What the prospect says, in bold;
 * its kind, as a tag; and the answer the rep sees. Objections the team hears without an answer
 * come as suggestions (the best rep's answer, or one Vocify writes); with nothing written or heard
 * yet, the three every team gets. Written ones are collapsed (the words and two lines of the answer)
 * and one opens at a time to be edited.
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
  onDismissAll,
  typesControl,
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
  /** Dismiss every suggestion at once, so the count on the tab can be cleared. */
  onDismissAll?: (keys: string[]) => void;
  /** The "also in other types" control of a written objection (by its key); none when there is nothing to offer. */
  typesControl?: (key: string) => ReactNode;
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const [openKey, setOpenKey] = useState<string | null>(null);
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
  // A custom objection just added has no name yet: it opens, with its name box focused.
  const keys = shown.map((row) => row.key);
  const seenKeys = useRef<string[] | null>(null);
  useEffect(() => {
    const added = newlyAddedKey(seenKeys.current, keys);
    seenKeys.current = keys;
    const row = added ? shown.find((candidate) => candidate.key === added) : undefined;
    if (editable && row?.objection.category === "custom" && !row.objection.label?.trim()) setOpenKey(row.key);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs when the set of rows changes
  }, [keys.join("|")]);

  if (!editable && shown.length === 0) return null;

  const kindOf = (item: EditorObjection) => (item.category === "custom" ? item.label ?? "" : kinds[item.category as ObjectionCategory]);
  const usual = (item: EditorObjection) =>
    item.category === "custom" ? copy.objTriggerPlaceholder : copy.objectionSays[item.category] ?? kindOf(item);

  return (
    <section aria-label={copy.objections}>
      {suggestions.length > 0 ? (
        <div className="mb-2 rounded-xl bg-secondary/40 px-3 pb-1 pt-3">
          <div className="flex items-center justify-between gap-3 pl-[2.5rem]">
            <p className="text-[13px] font-medium text-foreground">
              {copy.objSuggestedHeading} <span className="font-normal tabular-nums text-muted-foreground">· {suggestions.length}</span>
            </p>
            {onDismissAll ? (
              <button type="button" className="text-xs text-muted-foreground transition-colors hover:text-foreground" onClick={() => onDismissAll(suggestions.map((row) => row.key))}>
                {copy.dismissAll}
              </button>
            ) : null}
          </div>
          <ul>
        {suggestions.map((row) => (
          // A ghost of an objection: the same row as a written one, muted until it has an answer.
          <DocRow
            key={row.key}
            lead={<QuoteMark muted />}
            title={<p className={cn(itemTitle, "text-muted-foreground")}>{usual(row.objection)}</p>}
            side={kindOf(row.objection) ? <TypeTag>{kindOf(row.objection)}</TypeTag> : null}
          >
            {row.count > 0 ? <MetaLine>{copy.heardShare.replace("{share}", percent(row.share))} · {copy.noAnswerYet}</MetaLine> : null}
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
        </div>
      ) : null}
      <ul>
        {shown.map((row) => {
          const item = row.objection;
          const custom = item.category === "custom";
          const set = (patch: Patch) => onChange(row.key, patch);
          const open = openKey === row.key;
          const toggle = () => setOpenKey((current) => toggleOpenKey(current, row.key));
          const answer = item.guidance.trim();
          return (
            <DocRow
              key={row.key}
              lead={
                // One toggle, mounted open or closed, so keyboard focus stays on it.
                <span className="-my-2">
                  <IconAction label={open ? copy.objCollapse : copy.objExpand} expanded={open} onClick={toggle}>
                    <ChevronDown size={16} strokeWidth={1.5} className={cn("transition-transform duration-150 motion-reduce:transition-none", open && "rotate-180")} />
                  </IconAction>
                </span>
              }
              title={
                !(open && editable) ? (
                  // A click on the words or the answer toggles too; the lead button is the keyboard way in.
                  <button
                    type="button"
                    tabIndex={-1}
                    onClick={toggle}
                    className="block w-full rounded-md text-left"
                  >
                    <span className={cn(itemTitle, "block")}>{item.trigger?.trim() || usual(item)}</span>
                    {answer ? <span className={cn(itemBody, "mt-1 block whitespace-pre-wrap", !open && "line-clamp-2")}>{item.guidance}</span> : null}
                  </button>
                ) : (
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
                )
              }
              side={
                <>
                  {custom && editable ? (
                    <InlineTextarea
                      // The field's own negative side margins are off (they pulled the box under the title), there is room
                      // on its left inside, and it is as wide as the name, so a longer one stays on one line.
                      className="mx-0 w-auto rounded-full bg-secondary py-0.5 pl-3.5 pr-3 text-[11.5px] text-muted-foreground focus:text-foreground"
                      style={{ width: `calc(${Math.min(Math.max((item.label ?? "").length, 12), 30)}ch + 2.25rem)` }}
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
                  ) : kindOf(item) ? (
                    <TypeTag>{kindOf(item)}</TypeTag>
                  ) : null}
                  {row.count > 0 ? (
                    <span className="text-xs tabular-nums text-muted-foreground" title={copy.heardShare.replace("{share}", percent(row.share))}>
                      {percent(row.share)}
                    </span>
                  ) : null}
                  {editable && answer && (!custom || item.label?.trim()) ? typesControl?.(row.key) : null}
                  {editable ? (
                    <ItemMenu
                      label={copy.itemMenu.replace("{name}", kindOf(item) || copy.objCustomName)}
                      actions={[{ label: t.product.playbookEditorRemove, onSelect: () => onRemove(row.key), danger: true }]}
                    />
                  ) : null}
                </>
              }
            >
              {open && editable ? (
                <InlineTextarea
                  className={itemBody}
                  value={item.guidance}
                  placeholder={copy.objectionPlaceholder}
                  aria-label={copy.objAnswer}
                  onChange={(event) => set({ guidance: event.target.value })}
                />
              ) : null}
              {open && editable && !answer && onComplete && (!custom || item.label?.trim()) ? (
                <div className="pt-1">
                  <CompleteButton label={copy.writeAnswer} pending={completingKey === row.key} disabled={busy} onClick={() => onComplete(row)} />
                </div>
              ) : null}
            </DocRow>
          );
        })}

      </ul>

      {editable ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button type="button" className={cn(linkButton, "mt-2")}>
              <Plus size={12} strokeWidth={1.5} />
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
