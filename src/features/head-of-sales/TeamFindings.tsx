import { useCallback, useState } from "react";
import { Table } from "@/features/coaching/rep/ImproveTables";
import { CallPanel } from "@/features/coaching/rep/CallRecord";
import { useLanguage } from "@/lib/i18n";
import { objectionTable, type TableRow } from "@/lib/rep-coaching";
import type { TeamCoaching } from "@/lib/team-coaching";

/** The calls a row opens, and which of them is on screen. */
type Open = { ids: string[]; index: number };

/** What the team's calls themselves showed, with Coaching's tables: the objections the playbook has no answer for,
 * the opportunities let pass (doors and chances to dig deeper), the objections and
 * what followed each reply, the clients' questions (the playbook's gaps first), what worked off the playbook and
 * every concession. A row opens its calls in Coaching's side panel; ↑ / ↓ go through them. Empty tables are not shown:
 * they fill as new calls are read. */
export function TeamFindings({ data }: { data: TeamCoaching }) {
  const { t } = useLanguage();
  const p = t.product;
  const [open, setOpen] = useState<Open | null>(null);
  const calls = data.calls ?? {};
  const findings = data.findings;
  const show = (ids: string[]) => {
    const known = ids.filter((id) => calls[id]);
    if (known.length) setOpen({ ids: known, index: 0 });
  };
  const close = useCallback(() => setOpen(null), []);
  const move = useCallback((step: -1 | 1) => {
    setOpen((current) => (current && current.ids[current.index + step] ? { ...current, index: current.index + step } : current));
  }, []);

  const who = (reps: string[]) => reps.map((name) => name.split("@")[0]).join(" · ");
  const counted = (topic: { topic: string; count: number; reps: string[] }, index: number): TableRow => ({
    id: String(index), title: topic.topic, good: topic.count, half: 0, unknown: 0, bad: 0, note: who(topic.reps),
  });
  const newObjections = findings?.new_objections ?? [];
  const newObjectionRows: TableRow[] = newObjections.map((item, index) => ({
    id: String(index), title: item.topic, good: item.after.advanced, half: item.after.stalled, unknown: item.after.unknown, bad: item.after.ended,
    of: item.count, note: who(item.reps),
  }));
  const opportunities = findings?.opportunities ?? [];
  const questions = findings?.questions ?? [];
  const worked = findings?.worked ?? [];
  const concessions = findings?.concessions ?? [];
  const questionRows: TableRow[] = questions.map((question, index) => ({
    id: String(index),
    title: question.topic,
    good: question.answered.yes,
    half: question.answered.partly,
    unknown: question.answered.later,
    bad: question.answered.no,
    of: question.count,
    note: [question.covered ? null : p.teamNotInPlaybook, who(question.reps)].filter(Boolean).join(" · "),
  }));
  const categories = p.playbookObjectionCategories as Record<string, string>;
  const objections = objectionTable(data.objections ?? [], p.coachUnanswered, categories);
  // The objections with no prepared answer are the head of sales' to write: first here, not last.
  const objectionRows = newObjections.length
    ? objections.rows.filter((row) => !row.group)
    : [...objections.rows].sort((a, b) => Number(Boolean(b.group)) - Number(Boolean(a.group)));
  const concessionRows: TableRow[] = concessions.map((item, index) => ({
    id: String(index), title: item.what, good: 1, half: 0, unknown: 0, bad: 0, note: [item.rep.split("@")[0], item.normal].filter(Boolean).join(" · "),
  }));

  const tables = [
    newObjections.length ? (
      <Table key="new-objections" id="team-new-objections" title={p.teamNewObjections} column={p.coachColAdvanced} rows={newObjectionRows} empty=""
        onOpen={(id) => show(newObjections[Number(id)].memo_ids)} />
    ) : null,
    opportunities.length ? (
      <Table key="opportunities" id="team-opportunities" title={p.teamOpportunities} column={p.teamColTimes} rows={opportunities.map(counted)} empty=""
        onOpen={(id) => show(opportunities[Number(id)].memo_ids)} />
    ) : null,
    objectionRows.length ? (
      <Table key="objections" id="team-objections" title={p.teamObjections} column={objections.byAfter ? p.coachColAdvanced : p.coachColResolved} rows={objectionRows} empty=""
        onOpen={(key) => show((objections.listed.find((item) => item.key === key)?.occurrences ?? []).map((o) => o.memo_id))} />
    ) : null,
    questions.length ? (
      <Table key="questions" id="team-questions" title={p.teamQuestions} column={p.teamColAnswered} rows={questionRows} empty=""
        onOpen={(id) => show(questions[Number(id)].memo_ids)} />
    ) : null,
    worked.length ? (
      <Table key="worked" id="team-worked" title={p.teamWorked} column={p.teamColTimes} rows={worked.map(counted)} empty=""
        onOpen={(id) => show(worked[Number(id)].memo_ids)} />
    ) : null,
    concessions.length ? (
      <Table key="concessions" id="team-concessions" title={p.teamConcessions} column="" rows={concessionRows} empty=""
        onOpen={(id) => show([concessions[Number(id)].memo_id])} />
    ) : null,
  ].filter(Boolean);
  if (!tables.length) return null;

  const current = open ? calls[open.ids[open.index]] : null;
  return (
    <>
      <div className="grid gap-10 lg:grid-cols-2 lg:gap-8" data-testid="team-findings">
        {tables}
      </div>
      {open && current ? (
        <CallPanel
          call={current}
          type={data.type ?? ""}
          rep={current.rep.split("@")[0]}
          onClose={close}
          onMove={move}
          canMove={{ previous: open.index > 0, next: open.index < open.ids.length - 1 }}
        />
      ) : null}
    </>
  );
}
