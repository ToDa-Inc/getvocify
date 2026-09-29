import { PlaybookList } from "@/features/playbooks/components/PlaybookList";

/**
 * "Vuestro proceso" on the Sales process page: one place to give Vocify the playbook and
 * one row per call type (docs/superpowers/plans/2026-09-29-playbooks-v2.md §14). Setup is
 * the company's own document, file or voice note, which Vocify structures.
 */
export default function PlaybooksSection() {
  return <PlaybookList />;
}
