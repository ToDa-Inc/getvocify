import { emptyAsk, type AskView } from "./ask-turn.ts";

export type AskChoice = { id: string; label: string };

export function askChoices(turn: { choices?: AskChoice[] | null }): AskChoice[] {
  const rows = turn.choices;
  if (!rows?.length) return [];
  return rows.filter((row) => Boolean(row.id?.trim() && row.label?.trim()));
}

export function showAskChoices(view: AskView, choices: AskChoice[]): boolean {
  return view.status === "completed" && askChoices({ choices }).length > 0;
}

export function viewForFollowUp(view: AskView): AskView {
  if (view.status === "completed" || view.status === "failed") {
    return { ...emptyAsk(), posts: view.posts };
  }
  return view;
}
