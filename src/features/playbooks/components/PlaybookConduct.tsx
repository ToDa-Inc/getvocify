import { useEffect, useRef, useState } from "react";
import { CircleCheck, CircleSlash, Flag, Plus, type LucideIcon } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { errorCode, playbooksApi, type Conduct } from "@/features/playbooks/api";
import { DocRow, ItemMenu, NumberMark } from "@/features/playbooks/components/DocParts";
import { InlineTextarea } from "@/features/playbooks/components/InlineField";
import { SaveStatus } from "@/features/playbooks/components/SaveStatus";
import { conductKey } from "@/features/playbooks/keys";
import { itemBody, itemTitle, linkButton } from "@/features/playbooks/styles";
import { useLanguage } from "@/lib/i18n";
import { newStepKey } from "@/lib/playbook-editor";
import type { SaveState } from "@/lib/playbook-doc";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

/** The same limits as the API (services/playbooks/conduct.py). */
const MAX_CRITERIA = 8;
const LIMITS = { goal: 200, also_good: 300, stop_when: 300, criterion: 220 } as const;
/** Typing pauses this long before it saves. */
const SAVE_DELAY_MS = 800;

type Outcome = "goal" | "also_good" | "stop_when";
type Row = { key: string; text: string };
type Local = Omit<Conduct, "criteria"> & { criteria: Row[] };

const toLocal = (conduct: Conduct): Local => ({ ...conduct, criteria: conduct.criteria.map((text) => ({ key: newStepKey(), text })) });
const toConduct = (local: Local): Conduct => ({ ...local, criteria: local.criteria.map((row) => row.text) });

/**
 * «Cómo trabajamos»: what counts as a good call of this type (the goal, what else is a good outcome, when to stop
 * pursuing the goal) and how the company runs these calls, in a few lines of its own. The live assistant reads it to
 * decide what to suggest, never as facts. Unlike the other tabs it is not drafted and published: it saves as it is
 * typed and applies from the next call.
 */
export function PlaybookConduct({ motionKey }: { motionKey: string }) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const queryClient = useQueryClient();
  const key = conductKey(motionKey);
  const query = useQuery({
    queryKey: key,
    queryFn: () => playbooksApi.conduct(motionKey),
    retry: (count, error) => errorCode(error) !== "not_activated" && count < 1,
  });
  const [local, setLocal] = useState<Local | null>(null);
  const [state, setState] = useState<SaveState>("idle");
  const [dirty, setDirty] = useState(false);
  const [focusKey, setFocusKey] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
  const pending = useRef<Conduct | null>(null);

  useEffect(() => {
    if (query.data && local === null) setLocal(toLocal(query.data.conduct));
  }, [query.data, local]);

  const save = async (conduct: Conduct) => {
    setState("saving");
    try {
      await playbooksApi.saveConduct(motionKey, conduct);
      if (pending.current === conduct) {
        pending.current = null;
        setDirty(false);
      }
      setState("saved");
    } catch {
      setState("error");
    }
  };

  // Leaving the tab (or the playbook) with typing not yet saved: it is saved now.
  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
      if (pending.current) void playbooksApi.saveConduct(motionKey, pending.current).catch(() => undefined);
    },
    [motionKey],
  );

  const change = (next: Local) => {
    const conduct = toConduct(next);
    setLocal(next);
    setDirty(true);
    pending.current = conduct;
    // The cache follows what is typed, so coming back to the tab shows it while the save is on its way.
    queryClient.setQueryData(key, { conduct });
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      timer.current = null;
      void save(conduct);
    }, SAVE_DELAY_MS);
  };

  if (query.isError) {
    const unavailable = errorCode(query.error) === "not_activated";
    return <p className="py-6 text-sm text-muted-foreground">{unavailable ? copy.conductUnavailable : copy.conductLoadError}</p>;
  }
  if (!local) {
    return (
      <div className="flex justify-center py-10">
        <VocifySpinner size={16} />
      </div>
    );
  }

  const outcomes: { field: Outcome; icon: LucideIcon; label: string; placeholder: string }[] = [
    { field: "goal", icon: Flag, label: copy.conductGoal, placeholder: copy.conductGoalPlaceholder },
    { field: "also_good", icon: CircleCheck, label: copy.conductAlsoGood, placeholder: copy.conductAlsoGoodPlaceholder },
    { field: "stop_when", icon: CircleSlash, label: copy.conductStop, placeholder: copy.conductStopPlaceholder },
  ];
  const setCriterion = (rowKey: string, text: string) =>
    change({ ...local, criteria: local.criteria.map((row) => (row.key === rowKey ? { ...row, text } : row)) });
  const add = () => {
    const rowKey = newStepKey();
    setFocusKey(rowKey);
    change({ ...local, criteria: [...local.criteria, { key: rowKey, text: "" }] });
  };
  const retry = () => void save(toConduct(local));

  return (
    <section aria-label={copy.blocks.conduct} className="space-y-6">
      <div>
        <div className="flex items-center justify-between gap-3 pt-1">
          <p className={THEME_TOKENS.typography.capsLabel}>{copy.conductOutcome}</p>
          <SaveStatus state={state} dirty={dirty} onRetry={retry} onReload={retry} />
        </div>
        <p className="pt-1 text-xs text-muted-foreground">{copy.conductApplies}</p>
        <ul>
          {outcomes.map(({ field, icon: Icon, label, placeholder }) => (
            <DocRow
              key={field}
              lead={<Icon size={16} strokeWidth={1.5} className="mt-0.5 text-muted-foreground" />}
              title={<p className={itemTitle}>{label}</p>}
            >
              <InlineTextarea
                className={itemBody}
                value={local[field]}
                maxLength={LIMITS[field]}
                placeholder={placeholder}
                aria-label={label}
                onKeyDown={(event) => {
                  if (event.key === "Enter") event.preventDefault();
                }}
                onChange={(event) => change({ ...local, [field]: event.target.value.replace(/\n/g, " ") })}
              />
            </DocRow>
          ))}
        </ul>
      </div>

      <div>
        <p className={cn(THEME_TOKENS.typography.capsLabel, "pt-1")}>{copy.conductCriteria}</p>
        <p className="pt-1 text-xs text-muted-foreground">{copy.conductCriteriaHint}</p>
        {local.criteria.length > 0 ? (
          <ul className="pt-1">
            {local.criteria.map((row, index) => (
              <DocRow
                key={row.key}
                lead={<NumberMark n={index + 1} />}
                title={
                  <InlineTextarea
                    className={itemBody}
                    value={row.text}
                    maxLength={LIMITS.criterion}
                    placeholder={copy.conductCriterionPlaceholder}
                    aria-label={`${copy.conductAdd} ${index + 1}`}
                    autoFocus={focusKey === row.key}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") event.preventDefault();
                    }}
                    onChange={(event) => setCriterion(row.key, event.target.value.replace(/\n/g, " "))}
                  />
                }
                side={
                  <ItemMenu
                    label={copy.itemMenu.replace("{name}", row.text || `${copy.conductAdd} ${index + 1}`)}
                    actions={[
                      {
                        label: t.product.playbookEditorRemove,
                        danger: true,
                        onSelect: () => change({ ...local, criteria: local.criteria.filter((other) => other.key !== row.key) }),
                      },
                    ]}
                  />
                }
              />
            ))}
          </ul>
        ) : null}
        {local.criteria.length < MAX_CRITERIA ? (
          <button type="button" className={cn(linkButton, "mt-2")} onClick={add}>
            <Plus size={12} strokeWidth={1.5} />
            {copy.conductAdd}
          </button>
        ) : null}
      </div>
    </section>
  );
}
