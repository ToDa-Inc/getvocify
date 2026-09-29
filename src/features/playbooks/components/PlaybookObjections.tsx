import { Plus } from "@phosphor-icons/react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { InlineTextarea } from "@/features/playbooks/components/InlineField";
import { useLanguage } from "@/lib/i18n";
import { hiddenObjectionCategories, percent, type ObjectionRow } from "@/lib/playbook-doc";
import { MAX_GUIDANCE, type ObjectionCategory } from "@/lib/playbook-editor";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

/**
 * Objection answers, second to the steps. Only the answered ones and the ones the team
 * actually hears are on screen, most frequent first; the rest are one click away.
 */
export function PlaybookObjections({
  rows,
  editable,
  onAnswer,
  onAdd,
}: {
  rows: ObjectionRow[];
  editable: boolean;
  onAnswer: (category: ObjectionCategory, guidance: string) => void;
  onAdd: (category: ObjectionCategory) => void;
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const names = t.product.playbookObjectionCategories;
  const hidden = hiddenObjectionCategories(rows);
  const shown = editable ? rows : rows.filter((row) => row.guidance.trim());

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
          {shown.map((row) => {
            const heard = row.count > 0;
            const unanswered = !row.guidance.trim();
            return (
              <li
                key={row.category}
                className="grid items-start gap-x-5 gap-y-0.5 border-t border-border/40 py-2.5 first:border-t-0 md:grid-cols-[minmax(0,15rem)_minmax(0,1fr)]"
              >
                <div className="pt-1">
                  <p className="text-[15px] text-foreground">{names[row.category]}</p>
                  {heard && editable ? (
                    <p className={cn("text-xs", unanswered ? "text-warning" : "text-muted-foreground")}>
                      {(unanswered ? copy.heardUnanswered : copy.heard).replace("{share}", percent(row.share))}
                    </p>
                  ) : null}
                </div>
                {editable ? (
                  <div className="space-y-1">
                    <InlineTextarea
                      className="text-sm"
                      value={row.guidance}
                      placeholder={copy.objectionPlaceholder}
                      aria-label={names[row.category]}
                      aria-invalid={row.guidance.length > MAX_GUIDANCE}
                      onChange={(event) => onAnswer(row.category, event.target.value)}
                    />
                    {unanswered && row.bestExample ? (
                      <button
                        type="button"
                        className="text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                        title={row.bestExample}
                        onClick={() => onAnswer(row.category, row.bestExample ?? "")}
                      >
                        {copy.useTeamAnswer}
                      </button>
                    ) : null}
                    {row.guidance.length > MAX_GUIDANCE * 0.9 ? (
                      <p className="text-xs text-muted-foreground">
                        {row.guidance.length}/{MAX_GUIDANCE}
                      </p>
                    ) : null}
                  </div>
                ) : (
                  <p className="pt-1 text-sm leading-relaxed text-foreground">{row.guidance}</p>
                )}
              </li>
            );
          })}
        </ul>
      ) : null}
      {editable && hidden.length > 0 ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="mt-1 inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-sm text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
            >
              <Plus size={12} weight="light" />
              {copy.addObjection}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            {hidden.map((category) => (
              <DropdownMenuItem key={category} onSelect={() => onAdd(category)}>
                {names[category]}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
    </section>
  );
}
